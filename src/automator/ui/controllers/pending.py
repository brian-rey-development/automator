"""Pending-review counts, polled off the Tk thread."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from automator.config import ConfigStore
from automator.ui import system_utils
from automator.ui.presentation import count_pdfs
from automator.ui.system_utils import notify, open_folder
from automator.ui.views.monitor import MonitorView

_PENDING_POLL_MS = 5000


class PendingController:
    def __init__(self, store: ConfigStore, monitor: MonitorView, widget: tk.Misc) -> None:
        self._store = store
        self._monitor = monitor
        self._widget = widget
        self.count = 0
        self._last = 0
        self._active = False
        self.on_count: Callable[[int], None] = lambda _count: None

    def start(self) -> None:
        self._active = True
        self._poll()

    def suspend(self) -> None:
        self._active = False

    def open_review(self) -> None:
        open_folder(self._store.get().review_folder)

    def _poll(self) -> None:
        if not self._active:
            return
        system_utils.run_async(self._count_and_apply)
        self._widget.after(_PENDING_POLL_MS, self._poll)

    def _count_and_apply(self) -> None:
        config = self._store.get()
        total = count_pdfs(config.review_folder) + count_pdfs(config.quarantine_folder)
        self._widget.after(0, lambda: self._apply(total))

    def _apply(self, count: int) -> None:
        if not self._active:
            return
        self.count = count
        self._monitor.set_pending(count)
        self._maybe_notify(count)
        self.on_count(count)

    def _maybe_notify(self, count: int) -> None:
        if count > self._last and self._store.get().notify:
            system_utils.run_async(lambda: notify("Automator", f"{count} factura(s) necesitan tu revision"))
        self._last = count
