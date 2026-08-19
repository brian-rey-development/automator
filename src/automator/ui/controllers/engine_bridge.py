"""Engine start/stop and event pumping on the Tk thread."""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

from automator.domain.models import ProcessOutcome, ProcessResult
from automator.services.engine import EngineEvent, EngineEventType, ProcessingEngine
from automator.ui import system_utils
from automator.ui.controllers.settings_form import SettingsForm
from automator.ui.presentation import count_key, status_label
from automator.ui.strings import OUTCOME_ROW_TAG
from automator.ui.system_utils import UiMailbox
from automator.ui.views.monitor import MonitorView
from automator.ui.views.sidebar import SidebarView

logger = logging.getLogger(__name__)

_POLL_MS = 150
_COUNTS = ("detected", "archived", "review", "error")


class EngineBridge:
    def __init__(
        self,
        engine: ProcessingEngine,
        events: queue.Queue[EngineEvent],
        monitor: MonitorView,
        sidebar: SidebarView,
        settings: SettingsForm,
        widget: tk.Misc,
        mailbox: UiMailbox,
    ) -> None:
        self._engine = engine
        self._events = events
        self._monitor = monitor
        self._sidebar = sidebar
        self._settings = settings
        self._widget = widget
        self._mailbox = mailbox
        self.counts = dict.fromkeys(_COUNTS, 0)
        self.on_running_changed: Callable[[], None] = lambda: None
        self.on_result: Callable[[], None] = lambda: None
        self.on_started: Callable[[], None] = lambda: None
        self._active = True
        self._generation = 0
        self._ledger_ok = True

    def require_ledger(self, available: bool) -> None:
        self._ledger_ok = available

    def toggle(self) -> None:
        if self._engine.is_running:
            self.stop()
            return
        self.start()

    def start(self) -> None:
        if not self._ledger_ok:
            messagebox.showerror(
                "Historial",
                "No se pudo abrir el historial. No se detectan duplicados ni se puede deshacer.",
            )
            return
        if not self._settings.collect_and_save():
            return
        self._monitor.toggle_btn.configure(state="disabled")
        self._sidebar.state_var.set("Iniciando...")
        self._monitor.detail_var.set("Iniciando el monitoreo...")
        system_utils.run_async(self._engine.start)

    def stop(self) -> None:
        self._monitor.toggle_btn.configure(state="disabled")
        self._sidebar.state_var.set("Deteniendo...")
        system_utils.run_async(self._engine.stop)

    def set_running(self, running: bool) -> None:
        self._monitor.set_running(running)
        self._sidebar.set_running(running)
        if not running:
            self._monitor.detail_var.set("Monitoreo detenido")
        self.on_running_changed()

    def suspend(self) -> None:
        self._active = False

    def poll_events(self) -> None:
        if not self._active:
            return
        try:
            self._drain()
            self._mailbox.drain()
        finally:
            if self._active:
                self._widget.after(_POLL_MS, self.poll_events)

    def reset_session_stats(self) -> None:
        self.counts = dict.fromkeys(_COUNTS, 0)
        self._monitor.reset_stats()

    def increment(self, key: str) -> None:
        self.counts[key] += 1
        self._monitor.set_stat(key, self.counts[key])

    def _drain(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return
            self._safe_handle(event)

    def _safe_handle(self, event: EngineEvent) -> None:
        try:
            self._handle_event(event)
        except Exception:
            logger.exception("Error procesando un evento del motor en la interfaz")

    def _handle_event(self, event: EngineEvent) -> None:
        if event.type is EngineEventType.STARTED:
            self._generation = event.generation_id
            self.reset_session_stats()
            self.set_running(True)
            self._monitor.detail_var.set(event.message)
            self.on_started()
            return
        if event.generation_id and event.generation_id != self._generation:
            return
        if event.type is EngineEventType.STOPPED:
            self.set_running(False)
            if self._settings.consume_restart():
                self.start()
        elif event.type is EngineEventType.DETECTED:
            self.increment("detected")
        elif event.type is EngineEventType.RESULT and event.result is not None:
            self._on_result(event.result)
        elif event.type is EngineEventType.ERROR:
            self._on_error(event)

    def _on_error(self, event: EngineEvent) -> None:
        if event.path is None:
            self._settings.consume_restart()
            self.set_running(self._engine.is_running)
            messagebox.showerror("Automator", event.message)
            return
        self.increment("error")
        self._monitor.append_log(event.path.name, "", "Error", "error", event.message)

    def _on_result(self, result: ProcessResult) -> None:
        if result.outcome is ProcessOutcome.SKIPPED_MISSING:
            return
        self.increment(count_key(result))
        voucher = result.invoice.voucher.label if result.invoice else ""
        destination = str(result.destination) if result.destination else result.message
        self._monitor.append_log(
            result.source.name,
            voucher,
            status_label(result),
            OUTCOME_ROW_TAG[result.counted_outcome],
            destination,
        )
        self.on_result()
