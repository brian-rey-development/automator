"""History toolbar: undo, clear, retry and table refresh."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

from automator.config import ConfigStore
from automator.services.engine import ProcessingEngine
from automator.services.ledger import Ledger, LedgerRecord
from automator.services.undo import UndoOutcome, perform_undo
from automator.ui import system_utils
from automator.ui.presentation import history_row, history_tag
from automator.ui.strings import CLEAR_HISTORY_CONFIRM
from automator.ui.views.history import HistoryView

logger = logging.getLogger(__name__)


class HistoryActions:
    def __init__(
        self,
        ledger: Ledger | None,
        engine: ProcessingEngine,
        store: ConfigStore,
        view: HistoryView,
        widget: tk.Misc,
    ) -> None:
        self._ledger = ledger
        self._engine = engine
        self._store = store
        self._view = view
        self._widget = widget
        self._pending = 0
        self.on_cleared: Callable[[], None] = lambda: None

    def set_pending(self, count: int) -> None:
        self._pending = count
        self.update_actions()

    def refresh(self) -> None:
        if self._ledger is None:
            return
        rows = [(history_row(record), history_tag(record)) for record in self._ledger.recent()]
        self._view.set_rows(rows)
        self.update_actions()

    def update_actions(self) -> None:
        running = self._engine.is_running
        has_history = self._ledger is not None and bool(self._ledger.recent(1))
        can_undo = not running and self._ledger is not None and self._ledger.last_undoable() is not None
        self._view.set_actions(can_undo=can_undo, can_clear=not running and has_history, can_retry=self._pending > 0)

    def undo_last(self) -> None:
        if self._ledger is None:
            return
        if self._engine.is_running:
            messagebox.showinfo("Deshacer", "Deten el monitor antes de deshacer, asi no se reprocesa al instante.")
            return
        record = self._ledger.last_undoable()
        if record is None or record.destination is None:
            messagebox.showinfo("Deshacer", "No hay movimientos para deshacer.")
            return
        self._apply_undo(record)

    def clear_history(self) -> None:
        if self._ledger is None:
            messagebox.showerror("Vaciar historial", "No se pudo abrir el historial.")
            return
        if self._engine.is_running:
            messagebox.showinfo("Vaciar historial", "Deten el monitor antes de vaciar el historial.")
            return
        if not messagebox.askyesno("Vaciar historial", CLEAR_HISTORY_CONFIRM, icon="warning"):
            return
        self._ledger.clear()
        self.on_cleared()
        self.refresh()
        messagebox.showinfo("Vaciar historial", "Historial vaciado. Los archivos siguen donde estaban.")

    def reprocess_pending(self) -> None:
        def run() -> None:
            if not self._engine.is_running:
                self._engine.start()
            count = self._engine.reprocess_pending()
            logger.info("Reintentando %d archivos pendientes", count)

        system_utils.run_async(run)

    def _apply_undo(self, record: LedgerRecord) -> None:
        if self._ledger is None:
            return
        result = perform_undo(record, self._store.get().input_folder, self._ledger)
        _show_undo_result(result.outcome, result.filename, result.error)
        self.refresh()


def _show_undo_result(outcome: UndoOutcome, filename: str, error: str) -> None:
    if outcome is UndoOutcome.MISSING:
        messagebox.showwarning("Deshacer", "El archivo ya no esta en su destino; se marco como deshecho.")
        return
    if outcome is UndoOutcome.FAILED:
        messagebox.showerror("Deshacer", f"No se pudo devolver el archivo: {error}")
        return
    messagebox.showinfo("Deshacer", f"Se devolvio {filename} a la carpeta de entrada.")
