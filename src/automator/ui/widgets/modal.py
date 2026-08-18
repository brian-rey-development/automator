"""Shared modal wiring for CTk toplevels."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk


def make_modal(
    window: ctk.CTkToplevel,
    master: tk.Misc,
    *,
    on_return: Callable[[], None] | None = None,
    on_escape: Callable[[], None] | None = None,
) -> None:
    window.transient(master.winfo_toplevel())
    if on_return is not None:
        window.bind("<Return>", lambda _event: on_return())
    if on_escape is not None:
        window.bind("<Escape>", lambda _event: on_escape())
    window.wait_visibility()
    window.grab_set()
    window.focus_set()
