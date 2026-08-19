"""History view: toolbar and ledger table. Callbacks only."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

import customtkinter as ctk

from automator.ui.theme import CORNER_RADIUS, Fonts, Palette
from automator.ui.widgets import ghost_button, hint, primary_button, secondary_button

_ICON_RETRY = "↻"
_ICON_UNDO = "↶"
_ICON_REFRESH = "⟳"


class HistoryView(ctk.CTkFrame):
    def __init__(
        self,
        master: tk.Misc,
        fonts: Fonts,
        on_retry: Callable[[], None],
        on_undo: Callable[[], None],
        on_refresh: Callable[[], None],
        on_clear: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color=Palette.BG, corner_radius=0)
        self._fonts = fonts
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_toolbar(on_retry, on_undo, on_refresh, on_clear)
        self._build_table()

    def set_rows(self, rows: Sequence[tuple[tuple[str, str, str, str, str], str]]) -> None:
        self.tree.delete(*self.tree.get_children())
        for values, tag in rows:
            self.tree.insert("", "end", values=values, tags=(tag,))

    def set_actions(self, *, can_undo: bool, can_clear: bool, can_retry: bool) -> None:
        self.undo_btn.configure(state="normal" if can_undo else "disabled")
        self.clear_btn.configure(state="normal" if can_clear else "disabled")
        self.retry_btn.configure(state="normal" if can_retry else "disabled")

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(header, text="Historial", font=self._fonts.h1, text_color=Palette.TEXT).pack(anchor="w")
        hint(header, "Todo lo procesado queda registrado, incluso tras cerrar la app.", self._fonts.hint).pack(
            anchor="w", pady=(4, 0)
        )

    def _build_toolbar(
        self,
        on_retry: Callable[[], None],
        on_undo: Callable[[], None],
        on_refresh: Callable[[], None],
        on_clear: Callable[[], None],
    ) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.retry_btn = primary_button(bar, f"{_ICON_RETRY}  Reintentar pendientes", on_retry, font=self._fonts.h2)
        self.retry_btn.configure(height=40)
        self.retry_btn.pack(side="left", padx=(0, 10))
        self.undo_btn = secondary_button(
            bar, f"{_ICON_UNDO}  Deshacer ultimo movimiento", on_undo, font=self._fonts.body
        )
        self.undo_btn.pack(side="left")
        ghost_button(bar, f"{_ICON_REFRESH}  Actualizar", on_refresh, font=self._fonts.body).pack(side="right")
        self.clear_btn = ghost_button(bar, "Vaciar historial", on_clear, font=self._fonts.body)
        self.clear_btn.pack(side="right", padx=(0, 10))

    def _build_table(self) -> None:
        card = ctk.CTkFrame(self, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        columns = ("fecha", "archivo", "comprobante", "estado", "destino")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="browse", style="Activity.Treeview")
        _configure_history_columns(tree)
        for tag, color in (("ok", Palette.ROW_SUCCESS), ("warn", Palette.ROW_WARNING), ("error", Palette.ROW_ERROR)):
            tree.tag_configure(tag, background=color)
        scroll = ctk.CTkScrollbar(card, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(18, 0), pady=18)
        scroll.grid(row=0, column=1, sticky="ns", padx=(6, 12), pady=18)
        self.tree = tree


def _configure_history_columns(tree: ttk.Treeview) -> None:
    headings = {
        "fecha": ("Fecha", 150),
        "archivo": ("Archivo", 200),
        "comprobante": ("Comprobante", 110),
        "estado": ("Estado", 130),
        "destino": ("Destino", 320),
    }
    for column, (text, width) in headings.items():
        tree.heading(column, text=text)
        tree.column(column, width=width, anchor="w", stretch=(column == "destino"))
