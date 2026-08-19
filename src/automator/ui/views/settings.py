"""Configuration view. Callbacks only, no SQLite or engine."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial

import customtkinter as ctk

from automator.config import SocietyMapping
from automator.domain.suppliers import Supplier
from automator.ui.theme import CORNER_RADIUS, Fonts, Palette
from automator.ui.views.settings_entities import build_societies, build_suppliers, fill_societies, fill_suppliers
from automator.ui.widgets import card_body, checkbox, folder_field, ghost_button, hint, primary_button, template_field


@dataclass(frozen=True)
class SettingsHooks:
    on_save: Callable[[], None]
    on_add_society: Callable[[], None]
    on_import_societies: Callable[[], None]
    on_edit_society: Callable[[int], None]
    on_remove_society: Callable[[int], None]
    on_import_suppliers: Callable[[], None]
    on_clear_suppliers: Callable[[], None]
    on_remove_supplier: Callable[[str], None]
    on_search_suppliers: Callable[[], None]
    on_open_logs: Callable[[], None]
    on_pick: Callable[[tk.StringVar], None]
    on_open: Callable[[tk.StringVar], None]


class SettingsView(ctk.CTkScrollableFrame):
    def __init__(self, master: tk.Misc, fonts: Fonts, hooks: SettingsHooks) -> None:
        super().__init__(master, fg_color=Palette.BG, corner_radius=0)
        self._fonts = fonts
        self._hooks = hooks
        self._init_vars()
        self._advanced_open = False
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self.advanced_body.grid()
            self._advanced_btn.configure(text="Avanzado  ▾")
            return
        self.advanced_body.grid_remove()
        self._advanced_btn.configure(text="Avanzado  ▸")

    def render_societies(self, societies: Sequence[SocietyMapping]) -> None:
        fill_societies(self.societies_list, societies, self._fonts, self._hooks)

    def render_suppliers(self, suppliers: Sequence[Supplier], total: int) -> None:
        shown = len(suppliers)
        self.supplier_count_var.set(f"Mostrando {shown} de {total}" if total else "0 proveedores")
        self.clear_suppliers_btn.configure(state="normal" if total > 0 else "disabled")
        fill_suppliers(self.suppliers_list, suppliers, self._fonts, self._hooks)

    def _init_vars(self) -> None:
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.unknown_var = tk.StringVar()
        self.quarantine_var = tk.StringVar()
        self.orders_var = tk.StringVar()
        self.dry_run_var = tk.BooleanVar()
        self.stability_var = tk.BooleanVar()
        self.notify_var = tk.BooleanVar()
        self.copy_var = tk.BooleanVar()
        self.timeout_var = tk.StringVar()
        self.template_var = tk.StringVar()
        self.supplier_count_var = tk.StringVar(value="0 proveedores")
        self.supplier_search_var = tk.StringVar()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Configuracion", font=self._fonts.h1, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        hint(self, "Lo esencial aca. El resto esta en Avanzado.", self._fonts.hint).grid(
            row=1, column=0, sticky="w", pady=(0, 18)
        )
        self._build_folders()
        self._build_societies()
        self._build_suppliers()
        self._build_options()
        self._build_advanced()
        self._build_actions()

    def _build_folders(self) -> None:
        body = card_body(self, "Carpetas", "", 2, self._fonts)
        pick = self._hooks.on_pick
        open_folder = self._hooks.on_open
        folder_field(
            body,
            "Entrada",
            self.input_var,
            0,
            self._fonts,
            lambda: pick(self.input_var),
            lambda: open_folder(self.input_var),
        )
        folder_field(
            body,
            "Salida",
            self.output_var,
            1,
            self._fonts,
            lambda: pick(self.output_var),
            lambda: open_folder(self.output_var),
        )

    def _build_societies(self) -> None:
        self.societies_list = build_societies(self, self._fonts, self._hooks)

    def _build_suppliers(self) -> None:
        self.suppliers_list, self.clear_suppliers_btn = build_suppliers(
            self, self._fonts, self._hooks, self.supplier_count_var, self.supplier_search_var
        )

    def _build_options(self) -> None:
        body = card_body(self, "Comportamiento", "", 5, self._fonts)
        checkbox(body, "Simular (no mueve archivos)", self.dry_run_var, 0, self._fonts.body)
        checkbox(body, "Copiar en vez de mover", self.copy_var, 1, self._fonts.body)
        hint(
            body,
            "El original queda en Entrada. Deshacer devuelve la copia archivada.",
            self._fonts.hint,
        ).grid(row=2, column=0, sticky="w", pady=(0, 8))
        checkbox(body, "Notificar cuando hay pendientes", self.notify_var, 3, self._fonts.body)

    def _build_advanced(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        wrap.grid_columnconfigure(0, weight=1)
        self._advanced_btn = ghost_button(wrap, "Avanzado  ▸", self.toggle_advanced, font=self._fonts.body)
        self._advanced_btn.grid(row=0, column=0, sticky="w")
        self.advanced_body = ctk.CTkFrame(wrap, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        self.advanced_body.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.advanced_body.grid_columnconfigure(0, weight=1)
        self.advanced_body.grid_remove()
        self._fill_advanced()

    def _fill_advanced(self) -> None:
        body = ctk.CTkFrame(self.advanced_body, fg_color="transparent")
        body.grid(row=0, column=0, sticky="ew", padx=20, pady=16)
        body.grid_columnconfigure(0, weight=1)
        checkbox(body, "Esperar a que termine la descarga", self.stability_var, 0, self._fonts.body)
        timeout = ctk.CTkFrame(body, fg_color="transparent")
        timeout.grid(row=1, column=0, sticky="w", pady=(0, 12))
        ctk.CTkLabel(timeout, text="Espera maxima (segundos)", font=self._fonts.body, text_color=Palette.TEXT).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkEntry(timeout, textvariable=self.timeout_var, width=80, height=36).pack(side="left")
        template_field(body, self.template_var, 2, self._fonts)
        self._adv_folder(body, "Sin clasificar", self.unknown_var, 3)
        self._adv_folder(body, "Cuarentena", self.quarantine_var, 4)
        self._adv_folder(body, "Ordenes de compra", self.orders_var, 5)
        ghost_button(body, "Abrir carpeta de logs", self._hooks.on_open_logs, font=self._fonts.body).grid(
            row=6, column=0, sticky="w", pady=(8, 0)
        )

    def _adv_folder(self, parent: tk.Misc, label: str, var: tk.StringVar, row: int) -> None:
        folder_field(
            parent,
            label,
            var,
            row,
            self._fonts,
            partial(self._hooks.on_pick, var),
            partial(self._hooks.on_open, var),
        )

    def _build_actions(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=7, column=0, sticky="ew", pady=(4, 24))
        bar.grid_columnconfigure(0, weight=1)
        primary_button(bar, "Guardar", self._hooks.on_save, font=self._fonts.h2).grid(row=0, column=0, sticky="e")
