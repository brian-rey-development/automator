"""Start/stop lifecycle for the processing engine."""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import replace
from pathlib import Path

from automator.config import AppConfig, ConfigProvider
from automator.domain.models import ParsedInvoice, ProcessResult
from automator.services.engine.events import EngineEvent, EngineEventType, EventSink, emit
from automator.services.engine.inbox import Inbox
from automator.services.engine.runtime import (
    WatcherFactory,
    halt,
    join_threads,
    start_rescanner,
    start_watcher,
    start_worker,
)
from automator.services.engine.source_memory import SourceMemory
from automator.services.engine.worker import RESCAN_INTERVAL_S, Worker, is_archived_duplicate
from automator.services.folders import ensure_folders
from automator.services.ledger import Ledger
from automator.services.pdf_reader import extract_text
from automator.services.processing import InvoiceProcessor, RegistryProvider, TextExtractor, empty_registry
from automator.services.watcher import FolderWatcher

logger = logging.getLogger(__name__)

_STOP_TIMEOUT_MSG = "El monitor no pudo detenerse a tiempo."


class ProcessingEngine:
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
        ensure_folders(config)
        self._generation_id += 1
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._inbox.clear()
        self._memory.clear()
        self._watcher = start_watcher(self._watcher_factory, config.input_folder, self._inbox.enqueue)
        self._worker = start_worker(self._loop, self._queue)
        self._rescanner = start_rescanner(self._rescan_loop)

    def _cleanup_failed_start(self) -> None:
        halt(self._watcher, self._queue, self._stop_event)
        self._clear_if_stopped()

    def _clear_if_stopped(self) -> bool:
        if join_threads(self._worker, self._rescanner):
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
            halt(watcher, work_queue, self._stop_event)
            if self._clear_if_stopped():
                self._emit(EngineEvent(EngineEventType.STOPPED, "Monitor detenido."))

    def process_existing(self) -> int:
        return self._inbox.process_existing()

    def reprocess_pending(self) -> int:
        return self._inbox.reprocess_pending()

    def _rescan_loop(self) -> None:
        while not self._stop_event.wait(RESCAN_INTERVAL_S):
            self._inbox.rescan()

    def process_now(self, path: Path) -> ProcessResult:
        self._inbox.reserve(path)
        try:
            return self._loop.process_now(path)
        finally:
            self._inbox.release(path)

    def _duplicate_check(self, invoice: ParsedInvoice) -> bool:
        return is_archived_duplicate(self._ledger, invoice)

    def _emit(self, event: EngineEvent) -> None:
        if event.generation_id == 0:
            event = replace(event, generation_id=self._generation_id)
        emit(self._sink, event)
