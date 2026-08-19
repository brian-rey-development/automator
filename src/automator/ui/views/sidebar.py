"""Brand sidebar with navigation and a status pill."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from automator import __version__
from automator.ui.theme import Fonts, Palette, create_brand_mark


class SidebarView(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, fonts: Fonts, on_navigate: Callable[[str], None]) -> None:
        super().__init__(master, width=224, fg_color=Palette.SIDEBAR, corner_radius=0)
        self._fonts = fonts
        self._on_navigate = on_navigate
        self._nav_items: dict[str, tuple[ctk.CTkFrame, ctk.CTkButton]] = {}
        self.state_var = tk.StringVar(value="Detenido")
        self.grid_propagate(False)
        self.grid_rowconfigure(4, weight=1)
        self._build_brand()
        self._nav_item("monitor", "Monitor", row=1)
        self._nav_item("history", "Historial", row=2)
        self._nav_item("config", "Configuracion", row=3)
        self._build_status_pill()

    def highlight(self, key: str) -> None:
        for name, (strip, button) in self._nav_items.items():
            active = name == key
            strip.configure(fg_color=Palette.ACCENT if active else "transparent")
            button.configure(
                fg_color=Palette.SIDEBAR_HOVER if active else "transparent",
                text_color="#ffffff" if active else Palette.MUTED_ON_DARK,
            )

    def set_running(self, running: bool) -> None:
        self._status_dot.configure(text_color=Palette.SUCCESS if running else Palette.MUTED_ON_DARK)
        self.state_var.set("En ejecucion" if running else "Detenido")

    def _build_brand(self) -> None:
        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 28))
        create_brand_mark(brand).pack(side="left", padx=(0, 12))
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Automator", font=self._fonts.h2, text_color="#ffffff").pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text=f"Facturas AFIP  ·  v{__version__}",
            font=self._fonts.hint,
            text_color=Palette.MUTED_ON_DARK,
        ).pack(anchor="w")

    def _nav_item(self, key: str, text: str, row: int) -> None:
        item = ctk.CTkFrame(self, fg_color="transparent", height=40)
        item.grid(row=row, column=0, sticky="ew", padx=12, pady=2)
        item.grid_columnconfigure(1, weight=1)
        item.grid_rowconfigure(0, weight=1)
        item.grid_propagate(False)
        strip = ctk.CTkFrame(item, width=4, fg_color="transparent", corner_radius=2)
        strip.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        button = ctk.CTkButton(
            item,
            text=text,
            anchor="w",
            height=40,
            corner_radius=8,
            font=self._fonts.body,
            fg_color="transparent",
            hover_color=Palette.SIDEBAR_HOVER,
            text_color=Palette.MUTED_ON_DARK,
            command=lambda: self._on_navigate(key),
        )
        button.grid(row=0, column=1, sticky="nsew")
        self._nav_items[key] = (strip, button)

    def _build_status_pill(self) -> None:
        pill = ctk.CTkFrame(self, fg_color=Palette.SIDEBAR_HOVER, corner_radius=10)
        pill.grid(row=5, column=0, sticky="ew", padx=14, pady=20)
        self._status_dot = ctk.CTkLabel(pill, text="●", font=self._fonts.body, text_color=Palette.MUTED_ON_DARK)
        self._status_dot.pack(side="left", padx=(12, 6), pady=10)
        ctk.CTkLabel(pill, textvariable=self.state_var, font=self._fonts.small, text_color=Palette.TEXT_ON_DARK).pack(
            side="left", padx=(0, 12), pady=10
        )
