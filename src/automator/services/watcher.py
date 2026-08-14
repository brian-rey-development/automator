"""Monitoreo de una carpeta en tiempo real para detectar PDFs nuevos."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from automator.services.file_ops import is_pdf

PdfCallback = Callable[[Path], None]

_OBSERVER_JOIN_TIMEOUT_S = 5.0


class _PdfEventHandler(FileSystemEventHandler):
    """Filtra eventos y notifica solo cuando aparece un PDF."""

    def __init__(self, on_pdf: PdfCallback) -> None:
        self._on_pdf = on_pdf

    def on_created(self, event: FileSystemEvent) -> None:
        self._notify_if_pdf(event, event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Muchos navegadores descargan a un temporal y renombran al PDF final.
        if isinstance(event, FileMovedEvent):
            self._notify_if_pdf(event, event.dest_path)

    def _notify_if_pdf(self, event: FileSystemEvent, raw_path: str | bytes) -> None:
        # watchdog puede entregar la ruta como bytes; se normaliza a str.
        path = Path(os.fsdecode(raw_path))
        if not event.is_directory and is_pdf(path):
            self._on_pdf(path)


class FolderWatcher:
    """Envuelve el Observer de watchdog con una interfaz simple de start/stop."""

    def __init__(self, folder: Path, on_pdf: PdfCallback) -> None:
        self._observer = Observer()
        self._observer.schedule(_PdfEventHandler(on_pdf), str(folder), recursive=False)

    def start(self) -> None:
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=_OBSERVER_JOIN_TIMEOUT_S)
