from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

from automator.ui.theme import Palette


def configure_tree_columns(tree: ttk.Treeview, headings: dict[str, tuple[str, int]], stretch: str) -> None:
    for column, (text, width) in headings.items():
        tree.heading(column, text=text)
        tree.column(column, width=width, anchor="w", stretch=(column == stretch))


def apply_status_tags(tree: ttk.Treeview) -> None:
    tree.tag_configure("ok", background=Palette.ROW_SUCCESS)
    tree.tag_configure("warn", background=Palette.ROW_WARNING)
    tree.tag_configure("error", background=Palette.ROW_ERROR)


def status_tree(
    parent: ctk.CTkFrame,
    headings: dict[str, tuple[str, int]],
    stretch: str,
) -> ttk.Treeview:
    tree = ttk.Treeview(
        parent, columns=tuple(headings), show="headings", selectmode="browse", style="Activity.Treeview"
    )
    configure_tree_columns(tree, headings, stretch)
    apply_status_tags(tree)
    scroll = ctk.CTkScrollbar(parent, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
    return tree
