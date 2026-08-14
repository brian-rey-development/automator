"""Functional smoke tests for the interface.

They require a display; they skip themselves if there is none (for example, an environment without X).
In CI they run under xvfb. They verify that the window builds, switches views and
collects configuration without exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import customtkinter as ctk
import pytest

from automator.config import AppConfig, ConfigStore, SocietyMapping
from automator.domain.models import ProcessOutcome
from automator.services.ledger import LedgerRecord
from automator.ui import main_window
from automator.ui.main_window import MainWindow, _count_pdfs, _history_row


def _config(tmp_path: Path) -> AppConfig:
    base = tmp_path / "out"
    return AppConfig(
        input_folder=tmp_path / "in",
        base_output_folder=base,
        unknown_folder=base / "_sin",
        quarantine_folder=base / "_err",
    )


@pytest.fixture
def window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr(main_window, "ledger_path", lambda: tmp_path / "history.db")
    try:
        root = ctk.CTk()
    except Exception as exc:  # noqa: BLE001 -- no display: the test is skipped, it is not a failure
        pytest.skip(f"sin display para Tk: {exc}")
    root.withdraw()
    win = MainWindow(root, ConfigStore(_config(tmp_path)))
    win.pack()
    root.update_idletasks()
    root.update()
    yield win
    win._engine.stop()
    if win._ledger is not None:
        win._ledger.close()
    root.destroy()


def test_window_builds_and_switches_views(window: MainWindow) -> None:
    # winfo_manager() does not depend on the toplevel being visible: "grid" if it is
    # mounted, "" if grid_remove was called. It is checked with the flat frames; the
    # config view (scrollable) is only exercised to make sure it does not break.
    window._show("history")
    window.update_idletasks()
    assert window._history_view.winfo_manager() == "grid"
    assert window._monitor_view.winfo_manager() == ""

    window._show("config")
    window.update_idletasks()
    assert window._history_view.winfo_manager() == ""

    window._show("monitor")
    window.update_idletasks()
    assert window._monitor_view.winfo_manager() == "grid"
    assert window._history_view.winfo_manager() == ""


def test_society_rows_add_and_remove(window: MainWindow) -> None:
    window._societies = [SocietyMapping(cuit="30111111118", name="EMPRESA UNA", folder=Path("/x/una"))]
    window._refresh_societies_list()
    window.update_idletasks()
    assert window._societies_list.winfo_children()
    window._remove_society(0)
    window.update_idletasks()
    assert not window._societies


def test_collect_config_roundtrips_widget_values(window: MainWindow, tmp_path: Path) -> None:
    window._input_var.set(str(tmp_path / "entrada"))
    window._output_var.set(str(tmp_path / "salida"))
    window._unknown_var.set(str(tmp_path / "salida" / "_sin"))
    window._quarantine_var.set(str(tmp_path / "salida" / "_err"))
    window._timeout_var.set("15")
    window._template_var.set("{year}/{supplier}")
    window._copy_var.set(True)
    config = window._collect_config()
    assert config is not None
    assert config.stability_timeout_s == 15.0
    assert config.destination_template == "{year}/{supplier}"
    assert config.copy_files is True


def test_toggle_button_reflects_state(window: MainWindow) -> None:
    assert window._toggle_btn.cget("text") == "Iniciar"
    window._set_running(True)
    assert window._toggle_btn.cget("text") == "Detener"
    window._set_running(False)
    assert window._toggle_btn.cget("text") == "Iniciar"


def test_history_row_formats_record() -> None:
    record = LedgerRecord(
        id=1,
        ts="2026-08-14T10:00:00",
        source_name="factura.pdf",
        identity=None,
        supplier="PROVEEDOR X",
        voucher="FC A",
        outcome=ProcessOutcome.MOVED,
        destination="/salida/x/factura.pdf",
        message="ok",
        reverted=False,
    )
    row = _history_row(record)
    assert row[1] == "factura.pdf"
    assert row[3] == "Archivado"


def test_count_pdfs_is_case_insensitive_and_recursive(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "sub" / "b.PDF").write_bytes(b"%PDF")
    (tmp_path / "sub" / "c.txt").write_bytes(b"x")
    assert _count_pdfs(tmp_path) == 2
    assert _count_pdfs(tmp_path / "no-existe") == 0
