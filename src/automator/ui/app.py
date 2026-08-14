"""Punto de entrada de la aplicacion de escritorio."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from automator.config import config_path, load_store
from automator.logging_config import log_location, setup_logging
from automator.ui.main_window import MainWindow
from automator.ui.theme import init_appearance

logger = logging.getLogger(__name__)

_WINDOW_TITLE = "Automator - Clasificador de facturas AFIP"
_INITIAL_GEOMETRY = "1080x700"
_MIN_SIZE = (980, 640)


def main() -> None:
    """Inicializa logging, carga la configuracion y lanza la ventana principal."""
    setup_logging()
    try:
        _run()
    except Exception:
        # En el .exe empaquetado no hay consola: un fallo de arranque debe ser visible.
        logger.exception("Fallo al iniciar Automator")
        messagebox.showerror(
            "Automator",
            f"No se pudo iniciar la aplicacion.\nRevisa el registro en:\n{log_location()}",
        )
        raise


def _apply_icon(root: ctk.CTk) -> None:
    # Icono de la ventana; best-effort para no romper el arranque si falta el asset.
    icon = _icon_path()
    if icon is None:
        return
    try:
        root.iconphoto(True, tk.PhotoImage(file=str(icon)))
    except tk.TclError:
        logger.debug("No se pudo aplicar el icono de la ventana", exc_info=True)


def _icon_path() -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    candidate = base / "assets" / "automator.png"
    return candidate if candidate.exists() else None


def _run() -> None:
    init_appearance()
    root = ctk.CTk()
    root.title(_WINDOW_TITLE)
    root.geometry(_INITIAL_GEOMETRY)
    root.minsize(*_MIN_SIZE)
    _apply_icon(root)

    first_run = not config_path().exists()
    window = MainWindow(root, load_store(), first_run=first_run)
    window.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", window.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
