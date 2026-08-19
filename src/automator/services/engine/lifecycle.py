"""Start/stop lifecycle for the processing engine."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from automator.config import AppConfig
from automator.domain.models import ParsedInvoice, ProcessResult
from automator.services.engine.events import ConfigProvider, EngineEvent, EngineEventType, EventSink, emit
from automator.services.engine.inbox import Inbox, list_pdfs
from automator.services.engine.source_memory import SourceMemory
from automator.services.engine.worker import (
    RESCAN_INTERVAL_S,
    SENTINEL,
    WORKER_JOIN_TIMEOUT_S,
    Worker,
    is_archived_duplicate,
    record_result,
)
from automator.services.ledger import Ledger
from automator.services.pdf_reader import extract_text
from automator.services.processing import InvoiceProcessor, RegistryProvider, TextExtractor, empty_registry
from automator.services.watcher import FolderWatcher

logger = logging.getLogger(__name__)

WatcherFactory = Callable[[Path, Callable[[Path], None]], FolderWatcher]
_STOP_TIMEOUT_MSG = "El monitor no pudo detenerse a tiempo."


class ProcessingEngine:
    """Coordinates the watcher, a queue and a worker that processes the PDFs.

    The queue and the stop signal are recreated on each start (a "generation"), so
    an old worker that takes long to finish never shares a queue with a new one. A
    start is rejected while the previous generation still owns its threads.
    """

    def __init__(
        self,
        config_provider: ConfigProvider,
        sink: EventSink,
        extractor: TextExtractor = extract_text,
        ledger: Ledger | None = None,
        registry_provider: RegistryProvider | None = None,
        watcher_factory: WatcherFactory = FolderWatcher,
    ) -> None:
        self._config_provider = config_provider
        self._sink = sink
        self._ledger = ledger
        self._watcher_factory = watcher_factory
        self._generation_id = 0
        self._starting = False
        self._lifecycle_lock = threading.Lock()
        self._wire(config_provider, extractor, ledger, registry_provider)

    def _wire(
        self,
        config_provider: ConfigProvider,
        extractor: TextExtractor,
        ledger: Ledger | None,
        registry_provider: RegistryProvider | None,
    ) -> None:
        self._processor = InvoiceProcessor(
            config_provider, extractor, self._duplicate_check, registry_provider or empty_registry
        )
        self._queue: queue.Queue[object] = queue.Queue()
        self._watcher: FolderWatcher | None = None
        self._worker: threading.Thread | None = None
        self._rescanner: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._input_unreadable = False
        self._memory = SourceMemory(self._lock, config_provider, ledger)
        self._inbox = Inbox(self._lock, self._memory, self._emit, config_provider, self._get_queue)
        self._loop = Worker(self._processor, self._inbox, self._memory, self._emit, ledger)

    def _get_queue(self) -> queue.Queue[object]:
        return self._queue

    @property
    def is_running(self) -> bool:
        return self._worker is not None or self._rescanner is not None

    def _claim_start(self) -> bool:
        with self._lock:
            if self._starting or self._worker is not None or self._rescanner is not None:
                return False
            self._starting = True
            return True

    def _release_start(self) -> None:
        with self._lock:
            self._starting = False

    def start(self) -> None:
        if not self._claim_start():
            return
        try:
            config = self._try_launch()
            if config is None:
                return
            self._emit(EngineEvent(EngineEventType.STARTED, f"Monitoreando: {config.input_folder}"))
            self.process_existing()
        finally:
            self._release_start()

    def _try_launch(self) -> AppConfig | None:
        with self._lifecycle_lock:
            try:
                config = self._config_provider()
                self._launch(config)
            except Exception as exc:
                logger.exception("No se pudo iniciar el motor")
                self._cleanup_failed_start()
                self._emit(EngineEvent(EngineEventType.ERROR, f"No se pudo iniciar el monitor: {exc}"))
                return None
            return config

    def _launch(self, config: AppConfig) -> None:
        config.ensure_folders()
        self._generation_id += 1
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._inbox.clear()
        self._memory.clear()
        self._input_unreadable = False
        self._start_threads(config)

    def _start_threads(self, config: AppConfig) -> None:
        self._watcher = self._watcher_factory(config.input_folder, self._inbox.enqueue)
        self._watcher.start()
        self._worker = threading.Thread(
            target=self._loop.run, args=(self._queue,), name="automator-worker", daemon=True
        )
        self._worker.start()
        self._rescanner = threading.Thread(target=self._rescan_loop, name="automator-rescan", daemon=True)
        self._rescanner.start()

    def _halt_generation(self, watcher: FolderWatcher | None, work_queue: queue.Queue[object]) -> None:
        self._stop_event.set()
        try:
            if watcher is not None:
                watcher.stop()
        except Exception:
            logger.exception("Fallo al detener el watcher")
        finally:
            work_queue.put(SENTINEL)

    def _cleanup_failed_start(self) -> None:
        self._halt_generation(self._watcher, self._queue)
        self._clear_if_stopped()

    def _join_threads(self) -> bool:
        worker = self._worker
        rescanner = self._rescanner
        if worker is not None:
            worker.join(timeout=WORKER_JOIN_TIMEOUT_S)
        if rescanner is not None:
            rescanner.join(timeout=WORKER_JOIN_TIMEOUT_S)
        worker_alive = worker is not None and worker.is_alive()
        rescanner_alive = rescanner is not None and rescanner.is_alive()
        return not worker_alive and not rescanner_alive

    def _clear_if_stopped(self) -> bool:
        if self._join_threads():
            with self._lock:
                self._watcher = None
                self._worker = None
                self._rescanner = None
            return True
        logger.warning("El worker o el rescanner no termino dentro del timeout")
        self._emit(EngineEvent(EngineEventType.ERROR, _STOP_TIMEOUT_MSG))
        return False

    def stop(self) -> None:
        with self._lifecycle_lock:
            with self._lock:
                if self._worker is None and self._rescanner is None:
                    return
                watcher = self._watcher
                work_queue = self._queue
            self._halt_generation(watcher, work_queue)
            if self._clear_if_stopped():
                self._emit(EngineEvent(EngineEventType.STOPPED, "Monitor detenido."))

    def process_existing(self) -> int:
        """Enqueues all the PDFs already present in the input folder."""
        return self._inbox.process_existing()

    def reprocess_pending(self) -> int:
        """Retries what was left in review and quarantine (useful after adjusting the config).

        Does not include archived nor unclassified: those are already in the history and
        would be detected as duplicates of themselves.
        """
        return self._inbox.reprocess_pending()

    def _rescan_loop(self) -> None:
        while not self._stop_event.wait(RESCAN_INTERVAL_S):
            try:
                paths = list_pdfs(self._config_provider().input_folder)
            except OSError as exc:
                if not self._input_unreadable:
                    self._input_unreadable = True
                    self._emit(EngineEvent(EngineEventType.ERROR, f"No se puede leer la carpeta de entrada: {exc}"))
                continue
            self._input_unreadable = False
            for path in paths:
                self._inbox.requeue(path)

    def process_now(self, path: Path) -> ProcessResult:
        """Processes a file synchronously (useful for tests and CLI)."""
        result = self._processor.process(path)
        record_result(self._ledger, result)
        self._memory.remember(path, result.outcome)
        self._emit(EngineEvent(EngineEventType.RESULT, result.message, path, result))
        return result

    def _duplicate_check(self, invoice: ParsedInvoice) -> bool:
        return is_archived_duplicate(self._ledger, invoice)

    def _safe_process(self, path: Path) -> None:
        self._loop.safe_process(path)

    def _emit(self, event: EngineEvent) -> None:
        if event.generation_id == 0:
            event = replace(event, generation_id=self._generation_id)
        emit(self._sink, event)
