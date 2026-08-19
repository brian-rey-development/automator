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
from openpyxl import Workbook

from automator.config import AppConfig, ConfigStore, SocietyMapping
from automator.domain.models import ProcessOutcome, ProcessResult
from automator.domain.suppliers import Supplier
from automator.services.engine import EngineEvent, EngineEventType
from automator.ui import shell, system_utils
from automator.ui.controllers import history_actions as history_actions_mod
from automator.ui.controllers import settings_form as settings_form_mod
from automator.ui.controllers import suppliers as suppliers_mod
from automator.ui.shell import MainWindow


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
    monkeypatch.setattr(shell, "ledger_path", lambda: tmp_path / "history.db")
    monkeypatch.setattr(system_utils, "run_async", lambda fn: fn())
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
    if win._supplier_store is not None:
        win._supplier_store.close()
    root.destroy()


def test_window_builds_and_switches_views(window: MainWindow) -> None:
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
    window._settings_form.societies = [SocietyMapping(cuit="30111111118", name="EMPRESA UNA")]
    window._settings_form.refresh_societies()
    window.update_idletasks()
    assert window._config_view.societies_list.winfo_children()
    window._settings_form.remove_society(0)
    window.update_idletasks()
    assert not window._settings_form.societies


def test_suppliers_search_lists_matches(window: MainWindow) -> None:
    assert window._supplier_store is not None
    assert window._registry_store is not None
    window._supplier_store.bulk_upsert([Supplier(cuit="30999999995", legal_name="Distribuidora Nordica SA")])
    window._registry_store.reload()
    window._config_view.supplier_search_var.set("nord")
    window._suppliers.refresh()
    window.update_idletasks()
    assert window._config_view.suppliers_list.winfo_children()


def test_clear_suppliers_button_disabled_when_registry_is_empty(window: MainWindow) -> None:
    assert window._supplier_store is not None
    assert window._registry_store is not None
    window._suppliers.refresh()
    assert window._config_view.clear_suppliers_btn.cget("state") == "disabled"

    window._supplier_store.bulk_upsert([Supplier(cuit="30999999995", legal_name="Nordica SA")])
    window._registry_store.reload()
    window._suppliers.refresh()
    assert window._config_view.clear_suppliers_btn.cget("state") == "normal"


def test_import_suppliers_updates_registry(window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert window._supplier_store is not None
    assert window._registry_store is not None
    path = tmp_path / "prov.xlsx"
    workbook = Workbook()
    workbook.active.append(["CUIT", "Razón Social"])
    workbook.active.append(["30-99999999-5", "Nordica SA"])
    workbook.save(path)
    monkeypatch.setattr(suppliers_mod.filedialog, "askopenfilename", lambda **_kwargs: str(path))
    monkeypatch.setattr(suppliers_mod, "ImportReportDialog", lambda *_args, **_kwargs: None)

    window._suppliers.import_suppliers()
    window._mailbox.drain()
    window.update()

    assert window._supplier_store.count() == 1
    assert len(window._registry_store.get()) == 1


def test_import_societies_adds_to_list(window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "empresas.xlsx"
    workbook = Workbook()
    workbook.active.append(["CUIT", "Razón Social"])
    workbook.active.append(["30-11111111-8", "Compradora Uno SA"])
    workbook.save(path)
    monkeypatch.setattr(settings_form_mod.filedialog, "askopenfilename", lambda **_kwargs: str(path))
    monkeypatch.setattr(settings_form_mod, "ImportReportDialog", lambda *_args, **_kwargs: None)

    window._settings_form.import_societies()
    window._mailbox.drain()
    window.update()

    assert [society.cuit for society in window._settings_form.societies] == ["30111111118"]


def test_advanced_config_starts_collapsed(window: MainWindow) -> None:
    window._show("config")
    window.update_idletasks()
    assert window._config_view.advanced_body.winfo_manager() == ""
    window._config_view.toggle_advanced()
    window.update_idletasks()
    assert window._config_view.advanced_body.winfo_manager() == "grid"


def test_collect_config_roundtrips_widget_values(window: MainWindow, tmp_path: Path) -> None:
    window._config_view.input_var.set(str(tmp_path / "entrada"))
    window._config_view.output_var.set(str(tmp_path / "salida"))
    window._config_view.unknown_var.set(str(tmp_path / "salida" / "_sin"))
    window._config_view.quarantine_var.set(str(tmp_path / "salida" / "_err"))
    window._config_view.timeout_var.set("15")
    window._config_view.template_var.set("{year}/{supplier}")
    window._config_view.copy_var.set(True)
    config = window._settings_form.collect_config()
    assert config is not None
    assert config.stability_timeout_s == 15.0
    assert config.destination_template == "{year}/{supplier}"
    assert config.copy_files is True


def test_toggle_button_reflects_state(window: MainWindow) -> None:
    assert window._monitor_view.toggle_btn.cget("text") == "Iniciar"
    window._engine_bridge.set_running(True)
    assert window._monitor_view.toggle_btn.cget("text") == "Detener"
    window._engine_bridge.set_running(False)
    assert window._monitor_view.toggle_btn.cget("text") == "Iniciar"


def test_poll_events_applies_a_result(window: MainWindow) -> None:
    result = ProcessResult(
        source=Path("a.pdf"),
        outcome=ProcessOutcome.MOVED,
        destination=Path("/out/a.pdf"),
        invoice=None,
        message="ok",
    )
    window._events.put(EngineEvent(EngineEventType.RESULT, "ok", Path("a.pdf"), result))
    window._engine_bridge.poll_events()
    assert window._engine_bridge.counts["archived"] == 1


def test_clear_history_clears_ledger_without_touching_files(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert window._ledger is not None
    pdf = tmp_path / "archivada.pdf"
    pdf.write_bytes(b"%PDF")
    window._ledger.record(
        ProcessResult(
            source=Path("descarga.pdf"),
            outcome=ProcessOutcome.MOVED,
            destination=pdf,
            invoice=None,
            message="ok",
        )
    )
    window._history_actions.refresh()
    assert window._history_view.tree.get_children()
    monkeypatch.setattr(history_actions_mod.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(history_actions_mod.messagebox, "showinfo", lambda *args, **kwargs: None)
    window._history_actions.clear_history()
    assert window._ledger.recent() == []
    assert not window._history_view.tree.get_children()
    assert pdf.exists()


def test_clear_history_resets_session_counters(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    window._engine_bridge.increment("detected")
    window._engine_bridge.increment("archived")
    assert window._engine_bridge.counts["detected"] == 1
    monkeypatch.setattr(history_actions_mod.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(history_actions_mod.messagebox, "showinfo", lambda *args, **kwargs: None)

    window._history_actions.clear_history()

    assert window._engine_bridge.counts == {"detected": 0, "archived": 0, "review": 0, "error": 0}
