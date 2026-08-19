from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

_EXCEL_TYPES = [("Excel", "*.xlsx")]


def ask_excel(parent: tk.Misc | None = None) -> Path | None:
    path = filedialog.askopenfilename(parent=parent, title="Elegi el Excel", filetypes=_EXCEL_TYPES)
    return Path(path) if path else None


def ask_folder(parent: tk.Misc | None = None, title: str = "Selecciona una carpeta") -> Path | None:
    chosen = filedialog.askdirectory(parent=parent, title=title)
    return Path(chosen) if chosen else None
