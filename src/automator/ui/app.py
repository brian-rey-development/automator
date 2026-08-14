"""Punto de entrada de la aplicacion de escritorio."""

from __future__ import annotations

import logging
from tkinter import messagebox

import customtkinter as ctk

from automator.config import load_store
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


def _run() -> None:
    init_appearance()
    root = ctk.CTk()
    root.title(_WINDOW_TITLE)
    root.geometry(_INITIAL_GEOMETRY)
    root.minsize(*_MIN_SIZE)

    window = MainWindow(root, load_store())
    window.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", window.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
