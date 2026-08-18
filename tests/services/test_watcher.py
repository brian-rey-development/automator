"""Tests for the PDF folder watcher adapter."""

from __future__ import annotations

from pathlib import Path

from watchdog.events import FileCreatedEvent, FileMovedEvent

from automator.services.watcher import FolderWatcher, _PdfEventHandler


def test_created_pdf_is_notified() -> None:
    seen: list[Path] = []
    handler = _PdfEventHandler(seen.append)
    handler.on_created(FileCreatedEvent(src_path="/tmp/factura.pdf"))
    assert seen == [Path("/tmp/factura.pdf")]


def test_created_non_pdf_is_ignored() -> None:
    seen: list[Path] = []
    handler = _PdfEventHandler(seen.append)
    handler.on_created(FileCreatedEvent(src_path="/tmp/nota.txt"))
    assert seen == []


def test_moved_crdownload_to_pdf_is_notified() -> None:
    seen: list[Path] = []
    handler = _PdfEventHandler(seen.append)
    handler.on_moved(
        FileMovedEvent(src_path="/tmp/factura.pdf.crdownload", dest_path="/tmp/factura.pdf"),
    )
    assert seen == [Path("/tmp/factura.pdf")]


def test_folder_watcher_start_stop(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path, lambda _path: None)
    watcher.start()
    watcher.stop()
