"""Shared button styles. Every clickable control goes through one of these."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

import customtkinter as ctk

from automator.ui.theme import CORNER_RADIUS, Palette


@dataclass(frozen=True)
class _Look:
    height: int
    fg: str
    hover: str
    text: str
    width: int | None = None
    bordered: bool = False


def _button(
    parent: tk.Misc,
    label: str,
    command: Callable[[], None],
    look: _Look,
    font: ctk.CTkFont | None = None,
) -> ctk.CTkButton:
    button = ctk.CTkButton(
        parent,
        text=label,
        height=look.height,
        corner_radius=CORNER_RADIUS,
        fg_color=look.fg,
        hover_color=look.hover,
        text_color=look.text,
        command=command,
        border_width=1 if look.bordered else 0,
        border_color=Palette.BORDER,
    )
    if look.width is not None:
        button.configure(width=look.width)
    if font is not None:
        button.configure(font=font)
    return button


def primary_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont | None = None,
    width: int | None = None,
) -> ctk.CTkButton:
    return _button(
        parent,
        text,
        command,
        _Look(44, Palette.ACCENT, Palette.ACCENT_HOVER, Palette.ACCENT_TEXT, width),
        font,
    )


def secondary_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont | None = None,
    width: int | None = None,
    height: int = 40,
) -> ctk.CTkButton:
    return _button(
        parent,
        text,
        command,
        _Look(height, Palette.PRIMARY, Palette.PRIMARY_HOVER, Palette.ON_PRIMARY, width),
        font,
    )


def muted_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    width: int | None = None,
) -> ctk.CTkButton:
    return _button(parent, text, command, _Look(36, Palette.MUTED, Palette.TEXT, Palette.ON_PRIMARY, width))


def ghost_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont | None = None,
) -> ctk.CTkButton:
    button = _button(parent, text, command, _Look(40, "transparent", Palette.SURFACE_ALT, Palette.MUTED), font)
    button.bind("<Enter>", lambda _event: button.configure(text_color=Palette.TEXT))
    button.bind("<Leave>", lambda _event: button.configure(text_color=Palette.MUTED))
    return button


def danger_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont | None = None,
    width: int | None = None,
) -> ctk.CTkButton:
    return _button(
        parent,
        text,
        command,
        _Look(44, Palette.ERROR, Palette.ERROR_HOVER, Palette.ON_PRIMARY, width),
        font,
    )


def nav_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont | None = None,
) -> ctk.CTkButton:
    return _button(
        parent,
        text,
        command,
        _Look(40, "transparent", Palette.SIDEBAR_HOVER, Palette.MUTED_ON_DARK),
        font,
    )


def path_button(parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
    return _button(
        parent,
        text,
        command,
        _Look(38, Palette.SURFACE_ALT, Palette.BORDER, Palette.TEXT, 72, bordered=True),
    )


def row_button(parent: tk.Misc, text: str, color: str, command: Callable[[], None], font: ctk.CTkFont) -> ctk.CTkButton:
    return _button(
        parent,
        text,
        command,
        _Look(32, Palette.SURFACE, Palette.BORDER, color, 78, bordered=True),
        font,
    )
