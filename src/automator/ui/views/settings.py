"""Configuration view. Callbacks only, no SQLite or engine."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial

import customtkinter as ctk

from automator.config import SocietyMapping
from automator.domain.suppliers import Supplier
from automator.ui.presentation import format_cuit
from automator.ui.theme import CORNER_RADIUS, Fonts, Palette
from automator.ui.widgets import (
    card_body,
    checkbox,
    entity_row,
    folder_field,
    ghost_button,
    hint,
    path_button,
    primary_button,
    template_field,
)


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
    on_open_input: Callable[[], None]
    on_open_output: Callable[[], None]
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
        for child in self.societies_list.winfo_children():
            child.destroy()
        if not societies:
            hint(self.societies_list, "Todavia no agregaste ninguna empresa.", self._fonts.hint).grid(
                row=0, column=0, sticky="w", pady=6
            )
            return
        for index, society in enumerate(societies):
            self._society_row(index, society)

    def render_suppliers(self, suppliers: Sequence[Supplier], total: int) -> None:
        for child in self.suppliers_list.winfo_children():
            child.destroy()
        self.supplier_count_var.set(f"{total} proveedores")
        self.clear_suppliers_btn.configure(state="normal" if total > 0 else "disabled")
        for index, supplier in enumerate(suppliers):
            self._supplier_row(index, supplier)

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
        folder_field(
            body, "Entrada", self.input_var, 0, self._fonts, lambda: pick(self.input_var), self._hooks.on_open_input
        )
        folder_field(
            body, "Salida", self.output_var, 1, self._fonts, lambda: pick(self.output_var), self._hooks.on_open_output
        )

    def _build_societies(self) -> None:
        body = card_body(self, "Empresas", "Se archiva segun el CUIT de la compradora.", 3, self._fonts)
        self.societies_list = ctk.CTkFrame(body, fg_color="transparent")
        self.societies_list.grid(row=0, column=0, sticky="ew")
        self.societies_list.grid_columnconfigure(0, weight=1)
        self._society_buttons(body)

    def _society_buttons(self, body: ctk.CTkFrame) -> None:
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        buttons.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            buttons,
            text="+  Agregar empresa",
            height=40,
            corner_radius=CORNER_RADIUS,
            font=self._fonts.body,
            fg_color=Palette.PRIMARY,
            hover_color=Palette.PRIMARY_HOVER,
            text_color="#ffffff",
            command=self._hooks.on_add_society,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        import_button = path_button(buttons, "Importar Excel", self._hooks.on_import_societies)
        import_button.configure(height=40)
        import_button.grid(row=0, column=1, sticky="ew")

    def _society_row(self, index: int, society: SocietyMapping) -> None:
        subtitle = f"CUIT {format_cuit(society.cuit)}"
        if society.nombre_fantasia:
            subtitle = f"{subtitle}   -   {society.nombre_fantasia}"
        entity_row(
            self.societies_list,
            index,
            society.name,
            subtitle,
            self._fonts,
            self._fonts.h2,
            partial(self._hooks.on_remove_society, index),
            partial(self._hooks.on_edit_society, index),
        )

    def _build_suppliers(self) -> None:
        body = card_body(
            self, "Proveedores", "Se importan por Excel y ordenan cada factura por emisor.", 4, self._fonts
        )
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, textvariable=self.supplier_count_var, font=self._fonts.body, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w"
        )
        path_button(header, "Importar Excel", self._hooks.on_import_suppliers).grid(row=0, column=1, padx=(6, 0))
        self.clear_suppliers_btn = path_button(header, "Vaciar", self._hooks.on_clear_suppliers)
        self.clear_suppliers_btn.grid(row=0, column=2, padx=(6, 0))
        search = ctk.CTkEntry(
            body, textvariable=self.supplier_search_var, height=38, placeholder_text="Buscar proveedor..."
        )
        search.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        search.bind("<KeyRelease>", lambda _event: self._hooks.on_search_suppliers())
        self.suppliers_list = ctk.CTkFrame(body, fg_color="transparent")
        self.suppliers_list.grid(row=2, column=0, sticky="ew")
        self.suppliers_list.grid_columnconfigure(0, weight=1)

    def _supplier_row(self, index: int, supplier: Supplier) -> None:
        entity_row(
            self.suppliers_list,
            index,
            supplier.razon_social,
            f"CUIT {format_cuit(supplier.cuit)}",
            self._fonts,
            self._fonts.body,
            partial(self._hooks.on_remove_supplier, supplier.cuit),
        )

    def _build_options(self) -> None:
        body = card_body(self, "Comportamiento", "", 5, self._fonts)
        checkbox(body, "Simular (no mueve archivos)", self.dry_run_var, 0, self._fonts.body)
        checkbox(body, "Copiar en vez de mover", self.copy_var, 1, self._fonts.body)
        checkbox(body, "Notificar cuando hay pendientes", self.notify_var, 2, self._fonts.body)

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
