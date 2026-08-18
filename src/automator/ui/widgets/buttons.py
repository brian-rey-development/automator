"""Shared button styles."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from automator.ui.theme import CORNER_RADIUS, Palette


def primary_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        font=font,
        height=44,
        corner_radius=CORNER_RADIUS,
        fg_color=Palette.ACCENT,
        hover_color=Palette.ACCENT_HOVER,
        text_color=Palette.ACCENT_TEXT,
        command=command,
    )


def secondary_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=text,
        font=font,
        height=40,
        corner_radius=CORNER_RADIUS,
        fg_color=Palette.PRIMARY,
        hover_color=Palette.SIDEBAR_HOVER,
        text_color="#ffffff",
        command=command,
    )


def ghost_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    font: ctk.CTkFont,
) -> ctk.CTkButton:
    button = ctk.CTkButton(
        parent,
        text=text,
        font=font,
        height=40,
        corner_radius=CORNER_RADIUS,
        fg_color="transparent",
        hover_color=Palette.SURFACE_ALT,
        text_color=Palette.MUTED,
        command=command,
    )
    button.bind("<Enter>", lambda _event: button.configure(text_color=Palette.TEXT))
    button.bind("<Leave>", lambda _event: button.configure(text_color=Palette.MUTED))
    return button
