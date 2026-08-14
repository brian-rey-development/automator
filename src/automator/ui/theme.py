"""Design system: paleta de marca, tipografias, logo y estilo de la tabla.

La identidad combina un fondo papel calido, una barra lateral casi negra y un
unico acento chartreuse usado con moderacion. Es una eleccion deliberada de
un solo tema (claro) hecho con cuidado, no un tema generico.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk


class Palette:
    """Colores de marca de Automator."""

    BG = "#F5F5F1"  # Papel calido
    SURFACE = "#FFFFFF"
    SURFACE_ALT = "#F0F0EC"
    BORDER = "#E4E4DD"

    SIDEBAR = "#16181D"  # Casi negro
    SIDEBAR_HOVER = "#23262E"
    SIDEBAR_ACTIVE = "#23262E"

    ACCENT = "#C9F24D"  # Chartreuse, el acento distintivo
    ACCENT_HOVER = "#B6E035"
    ACCENT_TEXT = "#16181D"

    PRIMARY = "#16181D"  # Boton principal premium (oscuro)
    PRIMARY_HOVER = "#000000"

    TEXT = "#16181D"
    TEXT_ON_DARK = "#EDEDEA"
    MUTED = "#6C7078"
    MUTED_ON_DARK = "#9A9EA6"

    SUCCESS = "#1F9D57"
    WARNING = "#C9820A"
    ERROR = "#D64545"

    ROW_SUCCESS = "#F0FAF3"
    ROW_WARNING = "#FBF6EA"
    ROW_ERROR = "#FCF1F0"


CORNER_RADIUS = 12
_PREFERRED_FAMILY = "Segoe UI"
_FALLBACK_FAMILY = "Helvetica"


def font_family(root: tk.Misc) -> str:
    """Devuelve Segoe UI en Windows o una alternativa disponible en otros sistemas."""
    families = set(tkfont.families(root))
    return _PREFERRED_FAMILY if _PREFERRED_FAMILY in families else _FALLBACK_FAMILY


def init_appearance() -> None:
    """Configura el modo de apariencia global de CustomTkinter."""
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def create_brand_mark(parent: tk.Misc, size: int = 34) -> tk.Canvas:
    """Dibuja el isotipo de Automator: un rayo oscuro sobre un mosaico chartreuse."""
    canvas = tk.Canvas(parent, width=size, height=size, bg=Palette.SIDEBAR, highlightthickness=0, bd=0)
    _rounded_rect(canvas, 1, 1, size - 1, size - 1, radius=size * 0.28, fill=Palette.ACCENT)
    bolt = [0.56, 0.14, 0.31, 0.55, 0.47, 0.55, 0.42, 0.86, 0.69, 0.43, 0.51, 0.43, 0.60, 0.14]
    canvas.create_polygon([coord * size for coord in bolt], fill=Palette.SIDEBAR, outline="")
    return canvas


def configure_table_style(root: tk.Misc, family: str) -> None:
    """Estiliza la tabla ttk.Treeview para que combine con el design system."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Activity.Treeview",
        background=Palette.SURFACE,
        fieldbackground=Palette.SURFACE,
        foreground=Palette.TEXT,
        rowheight=30,
        borderwidth=0,
        font=(family, 10),
    )
    style.configure(
        "Activity.Treeview.Heading",
        background=Palette.SURFACE_ALT,
        foreground=Palette.MUTED,
        font=(family, 10, "bold"),
        relief="flat",
        padding=(8, 8),
    )
    style.map(
        "Activity.Treeview",
        background=[("selected", Palette.SIDEBAR)],
        foreground=[("selected", "#ffffff")],
    )
    style.map("Activity.Treeview.Heading", background=[("active", Palette.BORDER)])


def _rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, fill: str) -> int:
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, fill=fill)
