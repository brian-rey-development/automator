"""Modal dialog that summarizes the result of an Excel import."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from automator.ui.theme import CORNER_RADIUS, Palette

_MAX_INVALID_SHOWN = 30


class ImportReportDialog(ctk.CTkToplevel):
    """Shows how many rows were imported and lists the ones that were rejected."""

    def __init__(self, master: tk.Misc, title: str, summary: str, invalid: list[tuple[int, str]]) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(fg_color=Palette.BG)
        self.resizable(False, False)
        self._build(summary, invalid)
        self._make_modal(master)

    def _build(self, summary: str, invalid: list[tuple[int, str]]) -> None:
        card = ctk.CTkFrame(self, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(card, text=summary, font=ctk.CTkFont(size=15, weight="bold"), text_color=Palette.TEXT).pack(
            anchor="w", padx=20, pady=(20, 8)
        )
        if invalid:
            self._invalid_list(card, invalid)
        ctk.CTkButton(
            card,
            text="Entendido",
            width=120,
            fg_color=Palette.PRIMARY,
            hover_color=Palette.PRIMARY_HOVER,
            command=self.destroy,
        ).pack(anchor="e", padx=20, pady=(4, 20))

    def _invalid_list(self, parent: ctk.CTkFrame, invalid: list[tuple[int, str]]) -> None:
        ctk.CTkLabel(parent, text="Filas con errores (no importadas):", text_color=Palette.MUTED).pack(
            anchor="w", padx=20, pady=(4, 4)
        )
        box = ctk.CTkScrollableFrame(parent, fg_color=Palette.SURFACE_ALT, corner_radius=CORNER_RADIUS, height=180)
        box.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        for row, reason in invalid[:_MAX_INVALID_SHOWN]:
            ctk.CTkLabel(box, text=f"Fila {row}: {reason}", text_color=Palette.TEXT, anchor="w").pack(
                anchor="w", padx=10, pady=2
            )
        hidden = len(invalid) - _MAX_INVALID_SHOWN
        if hidden > 0:
            ctk.CTkLabel(box, text=f"... y {hidden} mas", text_color=Palette.MUTED, anchor="w").pack(
                anchor="w", padx=10, pady=2
            )

    def _make_modal(self, master: tk.Misc) -> None:
        self.transient(master.winfo_toplevel())
        self.bind("<Return>", lambda _event: self.destroy())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.wait_visibility()
        self.grab_set()
        self.focus_set()
