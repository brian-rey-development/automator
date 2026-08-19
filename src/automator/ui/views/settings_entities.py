from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from functools import partial
from typing import TYPE_CHECKING

import customtkinter as ctk

from automator.config import SocietyMapping
from automator.domain.suppliers import Supplier
from automator.ui.presentation import format_cuit
from automator.ui.theme import Fonts, Palette
from automator.ui.widgets import card_body, entity_row, hint, path_button, secondary_button

if TYPE_CHECKING:
    from automator.ui.views.settings import SettingsHooks


def build_societies(parent: ctk.CTkScrollableFrame, fonts: Fonts, hooks: SettingsHooks) -> ctk.CTkFrame:
    body = card_body(parent, "Empresas", "Se archiva segun el CUIT de la compradora.", 3, fonts)
    societies_list = ctk.CTkFrame(body, fg_color="transparent")
    societies_list.grid(row=0, column=0, sticky="ew")
    societies_list.grid_columnconfigure(0, weight=1)
    _society_actions(body, fonts, hooks)
    return societies_list


def fill_societies(
    holder: ctk.CTkFrame, societies: Sequence[SocietyMapping], fonts: Fonts, hooks: SettingsHooks
) -> None:
    _clear(holder)
    if not societies:
        hint(holder, "Todavia no agregaste ninguna empresa.", fonts.hint).grid(row=0, column=0, sticky="w", pady=6)
        return
    for index, society in enumerate(societies):
        subtitle = f"CUIT {format_cuit(society.cuit)}"
        if society.trade_name:
            subtitle = f"{subtitle}   -   {society.trade_name}"
        entity_row(
            holder,
            index,
            society.name,
            subtitle,
            fonts,
            fonts.h2,
            partial(hooks.on_remove_society, index),
            partial(hooks.on_edit_society, index),
        )


def build_suppliers(
    parent: ctk.CTkScrollableFrame,
    fonts: Fonts,
    hooks: SettingsHooks,
    count_var: tk.StringVar,
    search_var: tk.StringVar,
) -> tuple[ctk.CTkFrame, ctk.CTkButton]:
    body = card_body(parent, "Proveedores", "Se importan por Excel y ordenan cada factura por emisor.", 4, fonts)
    clear_btn = _supplier_header(body, fonts, hooks, count_var)
    search = ctk.CTkEntry(body, textvariable=search_var, height=38, placeholder_text="Buscar proveedor...")
    search.grid(row=1, column=0, sticky="ew", pady=(12, 8))
    search.bind("<KeyRelease>", lambda _event: hooks.on_search_suppliers())
    suppliers_list = ctk.CTkFrame(body, fg_color="transparent")
    suppliers_list.grid(row=2, column=0, sticky="ew")
    suppliers_list.grid_columnconfigure(0, weight=1)
    return suppliers_list, clear_btn


def fill_suppliers(
    holder: ctk.CTkFrame,
    suppliers: Sequence[Supplier],
    fonts: Fonts,
    hooks: SettingsHooks,
) -> None:
    _clear(holder)
    for index, supplier in enumerate(suppliers):
        entity_row(
            holder,
            index,
            supplier.legal_name,
            f"CUIT {format_cuit(supplier.cuit)}",
            fonts,
            fonts.body,
            partial(hooks.on_remove_supplier, supplier.cuit),
        )


def _society_actions(body: ctk.CTkFrame, fonts: Fonts, hooks: SettingsHooks) -> None:
    buttons = ctk.CTkFrame(body, fg_color="transparent")
    buttons.grid(row=1, column=0, sticky="ew", pady=(12, 0))
    buttons.grid_columnconfigure((0, 1), weight=1)
    add = secondary_button(buttons, "+  Agregar empresa", hooks.on_add_society, font=fonts.body)
    add.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    import_button = path_button(buttons, "Importar Excel", hooks.on_import_societies)
    import_button.configure(height=40)
    import_button.grid(row=0, column=1, sticky="ew")


def _supplier_header(body: ctk.CTkFrame, fonts: Fonts, hooks: SettingsHooks, count_var: tk.StringVar) -> ctk.CTkButton:
    header = ctk.CTkFrame(body, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew")
    header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(header, textvariable=count_var, font=fonts.body, text_color=Palette.TEXT).grid(
        row=0, column=0, sticky="w"
    )
    path_button(header, "Importar Excel", hooks.on_import_suppliers).grid(row=0, column=1, padx=(6, 0))
    clear_btn = path_button(header, "Vaciar", hooks.on_clear_suppliers)
    clear_btn.grid(row=0, column=2, padx=(6, 0))
    return clear_btn


def _clear(holder: ctk.CTkFrame) -> None:
    for child in holder.winfo_children():
        child.destroy()
