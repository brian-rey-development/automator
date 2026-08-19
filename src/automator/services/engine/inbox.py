"""Discovery and enqueueing of PDFs waiting to be processed."""

from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Callable
from pathlib import Path

from automator.config import ConfigProvider
from automator.services.engine.events import EngineEvent, EngineEventType, EventSink
from automator.services.engine.source_memory import SourceMemory
from automator.services.file_ops import list_pdfs

__all__ = ["Inbox", "list_pdfs", "path_key"]

logger = logging.getLogger(__name__)

QueueGetter = Callable[[], queue.Queue[object]]


def path_key(path: Path) -> Path:
    return Path(os.path.abspath(path))


class Inbox:
    def __init__(
        self,
        lock: threading.Lock,
        memory: SourceMemory,
        emit: EventSink,
        config_provider: ConfigProvider,
        get_queue: QueueGetter,
    ) -> None:
        self._lock = lock
        self._memory = memory
        self._emit = emit
        self._config_provider = config_provider
        self._get_queue = get_queue
        self._inflight: set[Path] = set()
        self._input_unreadable = False

    def clear(self) -> None:
        self._inflight = set()
        self._input_unreadable = False

    def enqueue(self, path: Path) -> None:
        if self._memory.already_processed(path) or not self.reserve(path):
            return
        self._emit(EngineEvent(EngineEventType.DETECTED, path.name, path))
        self._get_queue().put(path)

    def requeue(self, path: Path) -> None:
        if not self._memory.already_processed(path) and self.reserve(path):
            self._get_queue().put(path)

    def reserve(self, path: Path) -> bool:
        key = path_key(path)
        with self._lock:
            if key in self._inflight:
                return False
            self._inflight.add(key)
        return True

    def release(self, path: Path) -> None:
        with self._lock:
            self._inflight.discard(path_key(path))

    def process_existing(self) -> int:
        try:
            pdfs = list_pdfs(self._config_provider().input_folder)
        except OSError as exc:
            self._emit(EngineEvent(EngineEventType.ERROR, f"No se puede leer la carpeta de entrada: {exc}"))
            return 0
        for path in pdfs:
            self.enqueue(path)
        return len(pdfs)

    def reprocess_pending(self) -> int:
        config = self._config_provider()
        total = 0
        for folder in (config.review_folder, config.quarantine_folder):
            total += self._requeue_folder(folder)
        return total

    def _requeue_folder(self, folder: Path) -> int:
        try:
            pdfs = list_pdfs(folder, recursive=True)
        except OSError:
            logger.warning("No se pudo listar %s para reintentar", folder)
            return 0
        for path in pdfs:
            self.requeue(path)
        return len(pdfs)

    def rescan(self) -> None:
        try:
            paths = list_pdfs(self._config_provider().input_folder)
        except OSError as exc:
            if not self._input_unreadable:
                self._input_unreadable = True
                self._emit(EngineEvent(EngineEventType.ERROR, f"No se puede leer la carpeta de entrada: {exc}"))
            return
        self._input_unreadable = False
        for path in paths:
            self.requeue(path)
