"""Thread start/stop helpers for one engine generation."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from pathlib import Path

from automator.services.engine.worker import SENTINEL, WORKER_JOIN_TIMEOUT_S, Worker
from automator.services.watcher import FolderWatcher

logger = logging.getLogger(__name__)

WatcherFactory = Callable[[Path, Callable[[Path], None]], FolderWatcher]


def start_watcher(
    watcher_factory: WatcherFactory, input_folder: Path, enqueue: Callable[[Path], None]
) -> FolderWatcher:
    watcher = watcher_factory(input_folder, enqueue)
    watcher.start()
    return watcher


def start_worker(loop: Worker, work_queue: queue.Queue[object]) -> threading.Thread:
    worker = threading.Thread(target=loop.run, args=(work_queue,), name="automator-worker", daemon=True)
    worker.start()
    return worker


def start_rescanner(rescan: Callable[[], None]) -> threading.Thread:
    rescanner = threading.Thread(target=rescan, name="automator-rescan", daemon=True)
    rescanner.start()
    return rescanner


def halt(watcher: FolderWatcher | None, work_queue: queue.Queue[object], stop_event: threading.Event) -> None:
    stop_event.set()
    try:
        if watcher is not None:
            watcher.stop()
    except Exception:
        logger.exception("Fallo al detener el watcher")
    finally:
        work_queue.put(SENTINEL)


def join_threads(worker: threading.Thread | None, rescanner: threading.Thread | None) -> bool:
    if worker is not None:
        worker.join(timeout=WORKER_JOIN_TIMEOUT_S)
    if rescanner is not None:
        rescanner.join(timeout=WORKER_JOIN_TIMEOUT_S)
    worker_alive = worker is not None and worker.is_alive()
    rescanner_alive = rescanner is not None and rescanner.is_alive()
    return not worker_alive and not rescanner_alive
