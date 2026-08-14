"""Motor de procesamiento: monitorea la carpeta y procesa PDFs en segundo plano.

Es agnostico a la interfaz grafica: comunica eventos a traves de un callback
(EventSink), de modo que la UI (o los tests) decide como reaccionar.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from automator.config import AppConfig
from automator.domain.models import ProcessResult
from automator.services.file_ops import is_pdf
from automator.services.pdf_reader import extract_text
from automator.services.processor import InvoiceProcessor, TextExtractor
from automator.services.watcher import FolderWatcher

logger = logging.getLogger(__name__)

_WORKER_JOIN_TIMEOUT_S = 10.0
_RESCAN_INTERVAL_S = 60.0  # Red de seguridad: reintenta archivos que el watcher pudo perderse.
_SENTINEL = object()  # Marca de fin de cola para detener el worker.


def _list_pdfs(folder: Path) -> list[Path]:
    """Lista los PDFs de una carpeta sin distinguir mayusculas en la extension.

    Propaga OSError a proposito: si la carpeta de entrada no se puede leer, el
    motor debe avisarle al usuario, no quedarse mudo procesando una lista vacia.
    """
    return sorted(path for path in folder.iterdir() if path.is_file() and is_pdf(path))


class EngineEventType(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"
    DETECTED = "detected"
    RESULT = "result"
    ERROR = "error"


@dataclass(frozen=True)
class EngineEvent:
    """Evento emitido por el motor hacia la interfaz."""

    type: EngineEventType
    message: str = ""
    path: Path | None = None
    result: ProcessResult | None = None


EventSink = Callable[[EngineEvent], None]
ConfigProvider = Callable[[], AppConfig]


class ProcessingEngine:
    """Coordina el watcher, una cola y un worker que procesa los PDFs.

    La cola y la señal de parada se recrean en cada arranque (una "generacion"),
    de modo que un worker viejo que tarde en terminar nunca comparte cola con uno
    nuevo. Un arranque se rechaza mientras el worker anterior siga vivo.
    """

    def __init__(
        self,
        config_provider: ConfigProvider,
        sink: EventSink,
        extractor: TextExtractor = extract_text,
    ) -> None:
        self._config_provider = config_provider
        self._sink = sink
        self._processor = InvoiceProcessor(config_provider, extractor)
        self._queue: queue.Queue[object] = queue.Queue()
        self._watcher: FolderWatcher | None = None
        self._worker: threading.Thread | None = None
        self._rescanner: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._inflight: set[Path] = set()  # Evita encolar dos veces el mismo archivo.
        self._input_unreadable = False  # Evita repetir el aviso de carpeta ilegible cada rescan.

    @property
    def is_running(self) -> bool:
        worker = self._worker  # Lectura unica: el worker puede pasar a None en paralelo.
        return worker is not None and worker.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            config = self._config_provider()
            try:
                self._launch(config)
            except Exception as exc:
                logger.exception("No se pudo iniciar el motor")
                self._cleanup_failed_start()
                self._emit(EngineEvent(EngineEventType.ERROR, f"No se pudo iniciar el monitor: {exc}"))
                return
        self._emit(EngineEvent(EngineEventType.STARTED, f"Monitoreando: {config.input_folder}"))
        self.process_existing()  # Procesa lo que ya estaba en la carpeta, sin que el usuario haga nada.

    def _launch(self, config: AppConfig) -> None:
        # Estado fresco por generacion antes de arrancar los hilos: cola y señal
        # propias para no cruzarse con un worker anterior que siga vivo.
        config.ensure_folders()
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._inflight = set()
        self._input_unreadable = False
        self._watcher = FolderWatcher(config.input_folder, self._enqueue)
        self._watcher.start()
        self._worker = threading.Thread(target=self._run, name="automator-worker", daemon=True)
        self._worker.start()
        self._rescanner = threading.Thread(target=self._rescan_loop, name="automator-rescan", daemon=True)
        self._rescanner.start()

    def _cleanup_failed_start(self) -> None:
        self._stop_event.set()
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                logger.exception("Fallo al limpiar el watcher tras un arranque fallido")
        self._watcher = None
        self._worker = None
        self._rescanner = None

    def stop(self) -> None:
        with self._lock:
            worker = self._worker
            watcher = self._watcher
            if worker is None:
                return
            self._stop_event.set()
            work_queue = self._queue
        if watcher is not None:
            watcher.stop()
        work_queue.put(_SENTINEL)
        worker.join(timeout=_WORKER_JOIN_TIMEOUT_S)
        with self._lock:
            if worker.is_alive():
                # Se conservan las referencias para que is_running siga en True y un
                # nuevo start no arranque un segundo worker mientras este no muere.
                logger.warning("El worker no termino dentro del timeout; puede seguir vivo en segundo plano")
            else:
                self._watcher = None
                self._worker = None
                self._rescanner = None
        self._emit(EngineEvent(EngineEventType.STOPPED, "Monitor detenido."))

    def process_existing(self) -> int:
        """Encola todos los PDFs ya presentes en la carpeta de entrada."""
        try:
            pdfs = _list_pdfs(self._config_provider().input_folder)
        except OSError as exc:
            self._emit(EngineEvent(EngineEventType.ERROR, f"No se puede leer la carpeta de entrada: {exc}"))
            return 0
        for path in pdfs:
            self._enqueue(path)
        return len(pdfs)

    def _rescan_loop(self) -> None:
        # Reintenta periodicamente los archivos que sigan en la carpeta (por si el
        # watcher perdio un evento o una cuarentena fallo de forma transitoria).
        while not self._stop_event.wait(_RESCAN_INTERVAL_S):
            try:
                paths = _list_pdfs(self._config_provider().input_folder)
            except OSError as exc:
                if not self._input_unreadable:
                    self._input_unreadable = True
                    self._emit(EngineEvent(EngineEventType.ERROR, f"No se puede leer la carpeta de entrada: {exc}"))
                continue
            self._input_unreadable = False
            for path in paths:
                self._requeue(path)

    def process_now(self, path: Path) -> ProcessResult:
        """Procesa un archivo de forma sincronica (util para tests y CLI)."""
        result = self._processor.process(path)
        self._emit(EngineEvent(EngineEventType.RESULT, result.message, path, result))
        return result

    def _enqueue(self, path: Path) -> None:
        # Camino del watcher y del backlog inicial: cuenta como "detectado".
        if not self._reserve(path):
            return
        self._emit(EngineEvent(EngineEventType.DETECTED, path.name, path))
        self._queue.put(path)

    def _requeue(self, path: Path) -> None:
        # Camino del rescan: reintenta sin volver a contar como "detectado".
        if self._reserve(path):
            self._queue.put(path)

    def _reserve(self, path: Path) -> bool:
        with self._lock:
            if path in self._inflight:
                return False
            self._inflight.add(path)
        return True

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            self._safe_process(item)  # type: ignore[arg-type]

    def _safe_process(self, path: Path) -> None:
        try:
            result = self._processor.process(path)
            self._emit(EngineEvent(EngineEventType.RESULT, result.message, path, result))
        except Exception as exc:
            logger.exception("Error inesperado procesando %s", path)
            self._emit(EngineEvent(EngineEventType.ERROR, str(exc), path))
        finally:
            with self._lock:
                self._inflight.discard(path)

    def _emit(self, event: EngineEvent) -> None:
        try:
            self._sink(event)
        except Exception:
            logger.exception("Fallo el sink de eventos")
