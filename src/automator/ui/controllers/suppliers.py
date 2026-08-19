"""Supplier registry import, search and edits."""

from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox

from automator.services.excel_import import ExcelReadError, MissingColumnError, parse_suppliers, read_rows
from automator.services.supplier_store import SupplierRegistryStore, SupplierStore
from automator.ui import system_utils
from automator.ui.dialogs.import_report_dialog import ImportReportDialog
from automator.ui.pickers import ask_excel
from automator.ui.system_utils import UiMailbox
from automator.ui.views.settings import SettingsView

logger = logging.getLogger(__name__)

_MAX_SUPPLIER_RESULTS = 20


class SuppliersController:
    def __init__(
        self,
        store: SupplierStore | None,
        registry: SupplierRegistryStore | None,
        view: SettingsView,
        widget: tk.Misc,
        mailbox: UiMailbox,
    ) -> None:
        self._store = store
        self._registry = registry
        self._view = view
        self._widget = widget
        self._mailbox = mailbox

    def refresh(self) -> None:
        if self._registry is None or self._store is None:
            return
        query = self._view.supplier_search_var.get().strip()
        results = self._registry.get().search(query, limit=_MAX_SUPPLIER_RESULTS)
        self._view.render_suppliers(results, self._store.count())

    def import_suppliers(self) -> None:
        if self._store is None or self._registry is None:
            messagebox.showerror("Proveedores", "El registro de proveedores no esta disponible.")
            return
        path = ask_excel(self._widget)
        if path is None:
            return
        system_utils.run_async(lambda: self._import_from(path))

    def clear_suppliers(self) -> None:
        if self._store is None or self._registry is None:
            return
        if not messagebox.askyesno("Vaciar proveedores", "Se borra todo el registro de proveedores. Continuar?"):
            return
        self._store.clear()
        self._registry.reload()
        self.refresh()

    def remove_supplier(self, cuit: str) -> None:
        if self._store is None or self._registry is None:
            return
        if not messagebox.askyesno("Eliminar proveedor", f"Se elimina el CUIT {cuit} del registro. Continuar?"):
            return
        self._store.delete(cuit)
        self._registry.reload()
        self.refresh()

    def _import_from(self, path: Path) -> None:
        try:
            report = parse_suppliers(read_rows(path))
        except ExcelReadError as exc:
            logger.exception("No se pudo leer el Excel %s", path)
            self._ui_error("Error al leer", f"No se pudo leer el Excel: {exc}")
            return
        except MissingColumnError as exc:
            self._ui_error("Excel invalido", str(exc))
            return
        if self._store is None or self._registry is None:
            return
        try:
            created, updated = self._store.bulk_upsert(report.created)
            self._registry.reload()
        except (OSError, sqlite3.Error) as exc:
            logger.exception("No se pudo guardar el registro de proveedores")
            self._ui_error("Error al guardar", f"No se pudo guardar el registro: {exc}")
            return
        self._on_ui(lambda: self._finish_import(created, updated, report.invalid))

    def _finish_import(self, created: int, updated: int, invalid: list[tuple[int, str]]) -> None:
        self.refresh()
        summary = f"{created} nuevos, {updated} actualizados, {len(invalid)} con errores."
        ImportReportDialog(self._widget, "Importar proveedores", summary, invalid)

    def _on_ui(self, fn: Callable[[], object]) -> None:
        self._mailbox.post(lambda: fn())

    def _ui_error(self, title: str, message: str) -> None:
        self._on_ui(lambda: messagebox.showerror(title, message))
