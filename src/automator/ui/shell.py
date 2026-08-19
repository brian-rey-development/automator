"""Main window: compose views, navigation and shutdown."""

from __future__ import annotations

import logging
import queue
import sqlite3

import customtkinter as ctk

from automator.config import ConfigStore, ledger_path
from automator.services.engine import EngineEvent, ProcessingEngine
from automator.services.ledger import Ledger
from automator.services.supplier_store import SupplierRegistryStore, SupplierStore
from automator.ui import system_utils
from automator.ui.controllers.engine_bridge import EngineBridge
from automator.ui.controllers.history_actions import HistoryActions
from automator.ui.controllers.pending import PendingController
from automator.ui.controllers.settings_form import SettingsForm
from automator.ui.controllers.suppliers import SuppliersController
from automator.ui.dialogs.onboarding import OnboardingDialog
from automator.ui.theme import Fonts, Palette, configure_table_style, font_family, make_fonts
from automator.ui.views.history import HistoryView
from automator.ui.views.monitor import MonitorView
from automator.ui.views.settings import SettingsHooks, SettingsView
from automator.ui.views.sidebar import SidebarView

logger = logging.getLogger(__name__)

_ONBOARDING_MS = 250
_CLOSE_POLL_MS = 50
_CLOSE_LIMIT_MS = 12_000
_EVENT_POLL_MS = 150


class MainWindow(ctk.CTkFrame):
    def __init__(self, master: ctk.CTk, store: ConfigStore, first_run: bool = False) -> None:
        super().__init__(master, fg_color=Palette.BG, corner_radius=0)
        self._store = store
        self._closing = False
        self._close_wait_ms = 0
        self._init_backend()
        family = font_family(self)
        configure_table_style(self, family)
        self._fonts = make_fonts(family)
        self._build()
        self._wire()
        self._boot(first_run)

    def _show(self, key: str) -> None:
        for name, view in self._views.items():
            if name == key:
                view.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
            else:
                view.grid_remove()
        if key == "history":
            self._history_actions.refresh()
        self._sidebar.highlight(key)

    def on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._engine_bridge.suspend()
        self._pending.suspend()
        system_utils.run_async(self._engine.stop)
        self._await_close()

    def _init_backend(self) -> None:
        self._mailbox = system_utils.UiMailbox()
        self._events: queue.Queue[EngineEvent] = queue.Queue()
        self._ledger = _open_ledger()
        self._supplier_store = _open_supplier_store()
        registry = SupplierRegistryStore(self._supplier_store) if self._supplier_store else None
        self._registry_store = registry
        provider = registry.get if registry else None
        self._engine = ProcessingEngine(
            self._store.get, self._events.put, ledger=self._ledger, registry_provider=provider
        )

    def _boot(self, first_run: bool) -> None:
        self._settings_form.load()
        self._suppliers.refresh()
        self._engine_bridge.set_running(False)
        self._show("monitor")
        self.after(_EVENT_POLL_MS, self._engine_bridge.poll_events)
        self._pending.start()
        if first_run:
            self.after(_ONBOARDING_MS, self._run_onboarding)

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        fonts = self._fonts
        self._sidebar = SidebarView(self, fonts, on_navigate=self._show)
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        content = ctk.CTkFrame(self, fg_color=Palette.BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self._add_views(content, fonts)

    def _add_views(self, content: ctk.CTkFrame, fonts: Fonts) -> None:
        self._monitor_view = MonitorView(
            content, fonts, lambda: self._engine_bridge.toggle(), lambda: self._pending.open_review()
        )
        self._history_view = HistoryView(
            content,
            fonts,
            lambda: self._history_actions.reprocess_pending(),
            lambda: self._history_actions.undo_last(),
            lambda: self._history_actions.refresh(),
            lambda: self._history_actions.clear_history(),
        )
        self._config_view = SettingsView(content, fonts, self._settings_hooks())
        self._views: dict[str, MonitorView | HistoryView | SettingsView] = {
            "monitor": self._monitor_view,
            "history": self._history_view,
            "config": self._config_view,
        }

    def _settings_hooks(self) -> SettingsHooks:
        return SettingsHooks(
            on_save=lambda: self._settings_form.save_config(),
            on_add_society=lambda: self._settings_form.add_society(),
            on_import_societies=lambda: self._settings_form.import_societies(),
            on_edit_society=lambda index: self._settings_form.edit_society(index),
            on_remove_society=lambda index: self._settings_form.remove_society(index),
            on_import_suppliers=lambda: self._suppliers.import_suppliers(),
            on_clear_suppliers=lambda: self._suppliers.clear_suppliers(),
            on_remove_supplier=lambda cuit: self._suppliers.remove_supplier(cuit),
            on_search_suppliers=lambda: self._suppliers.refresh(),
            on_open_logs=lambda: self._settings_form.open_logs(),
            on_pick=lambda var: self._settings_form.pick_folder(var),
            on_open_input=lambda: self._settings_form.open_input(),
            on_open_output=lambda: self._settings_form.open_output(),
            on_open=lambda var: self._settings_form.open_folder_var(var),
        )

    def _wire(self) -> None:
        mailbox = self._mailbox
        self._settings_form = SettingsForm(self._store, self._config_view, self, mailbox)
        self._suppliers = SuppliersController(
            self._supplier_store, self._registry_store, self._config_view, self, mailbox
        )
        self._history_actions = HistoryActions(self._ledger, self._engine, self._store, self._history_view, self)
        self._engine_bridge = EngineBridge(
            self._engine, self._events, self._monitor_view, self._sidebar, self._settings_form, self, mailbox
        )
        self._pending = PendingController(self._store, self._monitor_view, self)
        self._settings_form.bind_monitor(
            lambda: self._engine.is_running, self._engine_bridge.start, self._engine_bridge.stop
        )
        self._engine_bridge.on_running_changed = self._history_actions.update_actions
        self._history_actions.on_cleared = self._engine_bridge.reset_session_stats
        self._pending.on_count = self._history_actions.set_pending

    def _run_onboarding(self) -> None:
        dialog = OnboardingDialog(self, self._store.get())
        self.wait_window(dialog)
        if dialog.result is not None and self._settings_form.persist(dialog.result):
            self._settings_form.load()

    def _await_close(self) -> None:
        self._close_wait_ms += _CLOSE_POLL_MS
        if self._engine.is_running and self._close_wait_ms < _CLOSE_LIMIT_MS:
            self.after(_CLOSE_POLL_MS, self._await_close)
            return
        self._finish_close()

    def _finish_close(self) -> None:
        if self._engine.is_running:
            logger.warning("El motor sigue activo; se cierra la ventana sin cerrar el historial")
        else:
            self._close_stores()
        self.winfo_toplevel().destroy()

    def _close_stores(self) -> None:
        if self._ledger is not None:
            self._ledger.close()
        if self._supplier_store is not None:
            self._supplier_store.close()


def _open_ledger() -> Ledger | None:
    try:
        return Ledger(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el historial; se continua sin el")
        return None


def _open_supplier_store() -> SupplierStore | None:
    try:
        return SupplierStore(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el registro de proveedores; se continua sin el")
        return None
