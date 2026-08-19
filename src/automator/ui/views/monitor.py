"""Monitor view: session stats, pending banner and activity log."""

from __future__ import annotations

import datetime as dt
import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from automator.ui.theme import CORNER_RADIUS, Fonts, Palette
from automator.ui.widgets import hint, path_button, primary_button, status_tree

_MAX_LOG_ROWS = 500
_STAT_CARDS = (
    ("detected", "Detectados", Palette.TEXT),
    ("archived", "Archivados", Palette.SUCCESS),
    ("review", "Para revisar", Palette.WARNING),
    ("error", "Errores", Palette.ERROR),
)


class MonitorView(ctk.CTkFrame):
    def __init__(
        self,
        master: tk.Misc,
        fonts: Fonts,
        on_toggle: Callable[[], None],
        on_open_review: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color=Palette.BG, corner_radius=0)
        self._fonts = fonts
        self.detail_var = tk.StringVar(value="Listo para empezar")
        self.pending_var = tk.StringVar()
        self.stat_values: dict[str, tk.StringVar] = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._build_header(on_toggle)
        self._build_stats()
        self._build_pending_banner(on_open_review)
        self._build_activity_log()

    def set_running(self, running: bool) -> None:
        self.toggle_btn.configure(
            state="normal",
            text="Detener" if running else "Iniciar",
            fg_color=Palette.ERROR if running else Palette.ACCENT,
            hover_color=Palette.ERROR_HOVER if running else Palette.ACCENT_HOVER,
            text_color=Palette.ON_PRIMARY if running else Palette.ACCENT_TEXT,
        )

    def set_pending(self, review: int, quarantine: int = 0) -> None:
        total = review + quarantine
        if total <= 0:
            self.pending_banner.grid_remove()
            return
        self.pending_var.set(_pending_copy(review, quarantine))
        self.pending_banner.grid(row=2, column=0, sticky="ew", pady=(0, 20))

    def set_stat(self, key: str, value: int) -> None:
        self.stat_values[key].set(str(value))

    def reset_stats(self) -> None:
        for var in self.stat_values.values():
            var.set("0")
        self.log.delete(*self.log.get_children())
        self.empty_state.grid(row=0, column=0, sticky="nsew")

    def append_log(self, filename: str, voucher: str, status: str, tag: str, destination: str) -> None:
        self.empty_state.grid_remove()
        now = dt.datetime.now().strftime("%H:%M:%S")
        self.log.insert("", 0, values=(now, filename, voucher, status, destination), tags=(tag,))
        children = self.log.get_children()
        if len(children) > _MAX_LOG_ROWS:
            self.log.delete(children[-1])

    def _build_header(self, on_toggle: Callable[[], None]) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header.grid_columnconfigure(0, weight=1)
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(titles, text="Monitor de facturas", font=self._fonts.h1, text_color=Palette.TEXT).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            textvariable=self.detail_var,
            font=self._fonts.body,
            text_color=Palette.MUTED,
            wraplength=520,
            justify="left",
        ).pack(anchor="w")
        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="e")
        self.toggle_btn = primary_button(controls, "Iniciar", on_toggle, font=self._fonts.h2)
        self.toggle_btn.configure(width=150)
        self.toggle_btn.pack(side="left")

    def _build_stats(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        for index, (key, label, color) in enumerate(_STAT_CARDS):
            row.grid_columnconfigure(index, weight=1)
            self._stat_card(row, index, key, label, color)

    def _stat_card(self, parent: ctk.CTkFrame, column: int, key: str, label: str, color: str) -> None:
        card = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 14, 0))
        var = tk.StringVar(value="0")
        self.stat_values[key] = var
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(anchor="w", padx=20, pady=(18, 0))
        ctk.CTkLabel(header, text="●", font=self._fonts.hint, text_color=color).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(header, text=label.upper(), font=self._fonts.hint, text_color=Palette.MUTED).pack(side="left")
        ctk.CTkLabel(card, textvariable=var, font=self._fonts.stat, text_color=Palette.TEXT).pack(
            anchor="w", padx=20, pady=(2, 18)
        )

    def _build_pending_banner(self, on_open_review: Callable[[], None]) -> None:
        banner = ctk.CTkFrame(self, fg_color=Palette.ROW_WARNING, corner_radius=CORNER_RADIUS)
        banner.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(banner, textvariable=self.pending_var, font=self._fonts.body, text_color=Palette.WARNING).grid(
            row=0, column=0, sticky="w", padx=18, pady=12
        )
        open_btn = path_button(banner, "Abrir pendientes", on_open_review)
        open_btn.configure(width=190, height=34, font=self._fonts.small)
        open_btn.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=8)
        self.pending_banner = banner

    def _build_activity_log(self) -> None:
        card = ctk.CTkFrame(self, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=3, column=0, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="Actividad reciente", font=self._fonts.h2, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", padx=22, pady=(18, 8)
        )
        self._build_log_table(card)

    def _build_log_table(self, parent: ctk.CTkFrame) -> None:
        container = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=0)
        container.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self.log = status_tree(
            container,
            {
                "when": ("Hora", 70),
                "file": ("Archivo", 220),
                "voucher": ("Comprobante", 110),
                "status": ("Estado", 110),
                "destination": ("Destino", 340),
            },
            "destination",
        )
        self.empty_state = _empty_state(container, self._fonts)


def _pending_copy(review: int, quarantine: int) -> str:
    parts: list[str] = []
    if review:
        parts.append(f"{review} para revisar")
    if quarantine:
        parts.append(f"{quarantine} en cuarentena")
    return ", ".join(parts) or "Pendientes"


def _empty_state(parent: ctk.CTkFrame, fonts: Fonts) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=0)
    frame.grid(row=0, column=0, sticky="nsew")
    inner = ctk.CTkFrame(frame, fg_color="transparent")
    inner.place(relx=0.5, rely=0.42, anchor="center")
    ctk.CTkLabel(inner, text="Todavia no hay actividad", font=fonts.h2, text_color=Palette.TEXT).pack()
    hint(inner, 'Apreta "Iniciar" y las facturas procesadas van a aparecer aca.', fonts.body).pack(pady=(4, 0))
    return frame
