"""Shared form building blocks for settings screens."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from automator.ui.theme import CORNER_RADIUS, Fonts, Palette
from automator.ui.widgets.buttons import path_button, row_button


def hint(parent: tk.Misc, text: str, font: ctk.CTkFont) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font, text_color=Palette.MUTED, anchor="w", justify="left")


def checkbox(parent: tk.Misc, text: str, var: tk.BooleanVar, row: int, font: ctk.CTkFont) -> None:
    ctk.CTkCheckBox(parent, text=text, font=font, variable=var).grid(row=row, column=0, sticky="w", pady=(0, 8))


def card_body(parent: tk.Misc, title: str, subtitle: str, row: int, fonts: Fonts) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
    card.grid(row=row, column=0, sticky="ew", pady=(0, 18))
    card.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(card, text=title, font=fonts.h2, text_color=Palette.TEXT).grid(
        row=0, column=0, sticky="w", padx=20, pady=(16, 8)
    )
    if subtitle:
        hint(card, subtitle, fonts.hint).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))
    body = ctk.CTkFrame(card, fg_color="transparent")
    body.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
    body.grid_columnconfigure(0, weight=1)
    return body


def folder_field(
    parent: tk.Misc,
    label: str,
    var: tk.StringVar,
    row: int,
    fonts: Fonts,
    on_pick: Callable[[], None],
    on_open: Callable[[], None] | None = None,
) -> None:
    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 10))
    block.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(block, text=label, font=fonts.body, text_color=Palette.TEXT, anchor="w").grid(
        row=0, column=0, columnspan=3, sticky="w"
    )
    ctk.CTkEntry(block, textvariable=var, height=38).grid(row=1, column=0, sticky="ew", pady=(4, 0))
    path_button(block, "Elegir", on_pick).grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
    if on_open is not None:
        path_button(block, "Abrir", on_open).grid(row=1, column=2, padx=(6, 0), pady=(4, 0))


def entity_row(
    parent: tk.Misc,
    index: int,
    title: str,
    subtitle: str,
    fonts: Fonts,
    title_font: ctk.CTkFont,
    on_delete: Callable[[], None],
    on_edit: Callable[[], None] | None = None,
) -> None:
    row = ctk.CTkFrame(parent, fg_color=Palette.SURFACE_ALT, corner_radius=CORNER_RADIUS)
    row.grid(row=index, column=0, sticky="ew", pady=(0, 8 if on_edit else 6))
    row.grid_columnconfigure(0, weight=1)
    info = ctk.CTkFrame(row, fg_color="transparent")
    info.grid(row=0, column=0, sticky="w", padx=12, pady=8)
    ctk.CTkLabel(info, text=title, font=title_font, text_color=Palette.TEXT, anchor="w").pack(anchor="w")
    ctk.CTkLabel(info, text=subtitle, font=fonts.hint, text_color=Palette.MUTED, anchor="w").pack(anchor="w")
    _entity_actions(row, fonts.small, on_delete, on_edit)


def _entity_actions(
    row: ctk.CTkFrame, font: ctk.CTkFont, on_delete: Callable[[], None], on_edit: Callable[[], None] | None
) -> None:
    if on_edit is None:
        row_button(row, "Eliminar", Palette.ERROR, on_delete, font).grid(row=0, column=1, sticky="e", padx=(0, 10))
        return
    actions = ctk.CTkFrame(row, fg_color="transparent")
    actions.grid(row=0, column=1, sticky="e", padx=(0, 12))
    row_button(actions, "Editar", Palette.TEXT, on_edit, font).pack(side="left", padx=6)
    row_button(actions, "Eliminar", Palette.ERROR, on_delete, font).pack(side="left")


def template_field(parent: tk.Misc, var: tk.StringVar, row: int, fonts: Fonts) -> None:
    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(block, text="Estructura de carpetas", font=fonts.body, text_color=Palette.TEXT).grid(
        row=0, column=0, sticky="w"
    )
    ctk.CTkEntry(block, textvariable=var, height=36).grid(row=1, column=0, sticky="ew", pady=(4, 0))
    hint(block, "{supplier} {year} {month} {day}. Ej: {year}/{month}/{supplier}", fonts.hint).grid(
        row=2, column=0, sticky="w", pady=(3, 0)
    )
