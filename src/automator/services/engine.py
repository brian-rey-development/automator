"""Processing engine: watches the folder and processes PDFs in the background.

It is agnostic to the graphical interface: it communicates events through a
callback (EventSink), so the UI (or the tests) decides how to react.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from automator.config import AppConfig
from automator.domain.models import ParsedInvoice, ProcessOutcome, ProcessResult
from automator.services.file_ops import is_pdf
from automator.services.ledger import Ledger
from automator.services.pdf_reader import extract_text
from automator.services.processor import InvoiceProcessor, RegistryProvider, TextExtractor, _empty_registry
from automator.services.watcher import FolderWatcher

logger = logging.getLogger(__name__)

_WORKER_JOIN_TIMEOUT_S = 10.0
_RESCAN_INTERVAL_S = 60.0  # Safety net: retries files the watcher may have missed.
_SENTINEL = object()  # End-of-queue marker to stop the worker.

# Outcomes that left a placed copy: in copy mode they are marked as seen so the
# original that stays in the input folder is not reprocessed.
_COPY_PLACED = frozenset(
    {
        ProcessOutcome.MOVED,
        ProcessOutcome.UNCLASSIFIED,
        ProcessOutcome.DUPLICATE,
        ProcessOutcome.NEEDS_REVIEW,
        ProcessOutcome.QUARANTINED,
    }
)


def _source_signature(path: Path) -> str | None:
    """Stable signature of a source file (path, size and date) or None if it cannot be read."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return f"{os.path.abspath(path)}|{stat.st_size}|{int(stat.st_mtime)}"


def _list_pdfs(folder: Path, *, recursive: bool = False) -> list[Path]:
    """Lists the PDFs in a folder, case-insensitive on the extension.

    Recurses when asked: review and quarantine files are filed under a per-supplier
    subfolder, so retrying them requires descending into those subfolders.
    Propagates OSError on purpose: if the folder cannot be read, the engine must
    notify the user, not stay silent processing an empty list.
    """
    paths = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(path for path in paths if path.is_file() and is_pdf(path))


class EngineEventType(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"
    DETECTED = "detected"
    RESULT = "result"
    ERROR = "error"


@dataclass(frozen=True)
class EngineEvent:
    """Event emitted by the engine toward the interface."""

    type: EngineEventType
    message: str = ""
    path: Path | None = None
    result: ProcessResult | None = None


EventSink = Callable[[EngineEvent], None]
ConfigProvider = Callable[[], AppConfig]


class ProcessingEngine:
    """Coordinates the watcher, a queue and a worker that processes the PDFs.

    The queue and the stop signal are recreated on each start (a "generation"), so
    an old worker that takes long to finish never shares a queue with a new one. A
    start is rejected while the previous worker is still alive.
    """

    def __init__(
        self,
        config_provider: ConfigProvider,
        sink: EventSink,
        extractor: TextExtractor = extract_text,
        ledger: Ledger | None = None,
        registry_provider: RegistryProvider | None = None,
    ) -> None:
        self._config_provider = config_provider
        self._sink = sink
        self._ledger = ledger
        self._processor = InvoiceProcessor(
            config_provider, extractor, self._duplicate_check, registry_provider or _empty_registry
        )
        self._queue: queue.Queue[object] = queue.Queue()
        self._watcher: FolderWatcher | None = None
        self._worker: threading.Thread | None = None
        self._rescanner: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._inflight: set[Path] = set()  # Avoids enqueuing the same file twice.
        self._seen_signatures: set[str] = set()
        self._input_unreadable = False  # Avoids repeating the unreadable-folder warning on each rescan.

    @property
    def is_running(self) -> bool:
        worker = self._worker  # Single read: the worker may become None in parallel.
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
        self.process_existing()  # Processes what was already in the folder, without the user doing anything.

    def _launch(self, config: AppConfig) -> None:
        # Fresh state per generation before starting the threads: own queue and
        # signal so it does not cross with a previous worker that is still alive.
        config.ensure_folders()
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._inflight = set()
        self._seen_signatures = set()
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
                # The references are kept so is_running stays True and a new start
                # does not launch a second worker while this one does not die.
                logger.warning("El worker no termino dentro del timeout; puede seguir vivo en segundo plano")
            else:
                self._watcher = None
                self._worker = None
                self._rescanner = None
        self._emit(EngineEvent(EngineEventType.STOPPED, "Monitor detenido."))

    def process_existing(self) -> int:
        """Enqueues all the PDFs already present in the input folder."""
        try:
            pdfs = _list_pdfs(self._config_provider().input_folder)
        except OSError as exc:
            self._emit(EngineEvent(EngineEventType.ERROR, f"No se puede leer la carpeta de entrada: {exc}"))
            return 0
        for path in pdfs:
            self._enqueue(path)
        return len(pdfs)

    def reprocess_pending(self) -> int:
        """Retries what was left in review and quarantine (useful after adjusting the config).

        Does not include archived nor unclassified: those are already in the history and
        would be detected as duplicates of themselves.
        """
        config = self._config_provider()
        total = 0
        for folder in (config.review_folder, config.quarantine_folder):
            try:
                pdfs = _list_pdfs(folder, recursive=True)
            except OSError:
                logger.warning("No se pudo listar %s para reintentar", folder)
                continue
            for path in pdfs:
                self._requeue(path)
                total += 1
        return total

    def _rescan_loop(self) -> None:
        # Periodically retries the files still in the folder (in case the watcher
        # missed an event or a quarantine failed transiently).
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
        """Processes a file synchronously (useful for tests and CLI)."""
        result = self._processor.process(path)
        self._record(result)
        self._remember_source(path, result.outcome)
        self._emit(EngineEvent(EngineEventType.RESULT, result.message, path, result))
        return result

    def _duplicate_check(self, invoice: ParsedInvoice) -> bool:
        if self._ledger is None or invoice.identity is None:
            return False
        destination = self._ledger.archived_destination(invoice.identity)
        # A real duplicate only if the previously archived file is still there. If the
        # original was removed, this copy must be filed, never lost as a phantom duplicate.
        return destination is not None and Path(destination).exists()

    def _record(self, result: ProcessResult) -> None:
        # What no longer exists is not recorded (noise); everything else stays in the history.
        if self._ledger is None or result.outcome is ProcessOutcome.SKIPPED_MISSING:
            return
        try:
            self._ledger.record(result)
        except Exception:
            logger.exception("No se pudo registrar en el historial")

    def _enqueue(self, path: Path) -> None:
        # Watcher and initial backlog path: counts as "detected".
        if self._already_processed(path) or not self._reserve(path):
            return
        self._emit(EngineEvent(EngineEventType.DETECTED, path.name, path))
        self._queue.put(path)

    def _requeue(self, path: Path) -> None:
        # Rescan path: retries without counting again as "detected".
        if not self._already_processed(path) and self._reserve(path):
            self._queue.put(path)

    def _already_processed(self, path: Path) -> bool:
        signature = _source_signature(path)
        if signature is not None and signature in self._seen_signatures:
            return True
        if self._ledger is None or not self._config_provider().copy_files:
            return False
        return signature is not None and self._ledger.source_seen(signature)

    def _remember_source(self, path: Path, outcome: ProcessOutcome) -> None:
        if outcome is ProcessOutcome.SKIPPED_MISSING:
            return
        config = self._config_provider()
        signature = _source_signature(path)
        if signature is not None and (config.dry_run or config.copy_files):
            self._seen_signatures.add(signature)
        self._mark_copied_in_ledger(path, outcome, config.copy_files)

    def _mark_copied_in_ledger(self, path: Path, outcome: ProcessOutcome, copy_files: bool) -> None:
        if self._ledger is None or not copy_files or outcome not in _COPY_PLACED:
            return
        signature = _source_signature(path)
        if signature is None:
            return
        try:
            self._ledger.mark_source_seen(signature)
        except Exception:
            logger.exception("No se pudo marcar %s como procesado", path)

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
            self._record(result)
            self._remember_source(path, result.outcome)
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
