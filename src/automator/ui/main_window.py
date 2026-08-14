"""Ventana principal: sidebar de marca, panel de monitoreo y configuracion.

La interfaz esta pensada para alguien sin experiencia: etiquetas claras, textos
de ayuda debajo de cada campo y selectores de carpeta en todos lados.
"""

from __future__ import annotations

import datetime as dt
import logging
import queue
import sqlite3
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from pydantic import ValidationError

from automator import __version__
from automator.config import AppConfig, ConfigStore, SocietyMapping, ledger_path, log_dir
from automator.domain.models import ProcessOutcome, ProcessResult
from automator.services import file_ops
from automator.services.engine import EngineEvent, EngineEventType, ProcessingEngine
from automator.services.ledger import Ledger, LedgerRecord
from automator.ui.onboarding import OnboardingDialog
from automator.ui.society_dialog import SocietyDialog
from automator.ui.system_utils import notify, open_folder
from automator.ui.theme import CORNER_RADIUS, Palette, configure_table_style, create_brand_mark, font_family

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 150
_PENDING_POLL_MS = 5000  # Relee las carpetas de pendientes cada 5s.
_MAX_LOG_ROWS = 500
_CUIT_LENGTH = 11

# Glyphs de icono: heredan el color del texto del boton y no dependen de assets.
_ICON_RETRY = "↻"  # flecha circular: reintentar
_ICON_UNDO = "↶"  # flecha de retorno: deshacer
_ICON_REFRESH = "⟳"  # flecha circular amplia: actualizar

_OUTCOME_LABELS: dict[ProcessOutcome, str] = {
    ProcessOutcome.MOVED: "Archivado",
    ProcessOutcome.DRY_RUN: "Simulado",
    ProcessOutcome.UNCLASSIFIED: "Sin clasificar",
    ProcessOutcome.DUPLICATE: "Duplicado",
    ProcessOutcome.NEEDS_REVIEW: "Revisar",
    ProcessOutcome.QUARANTINED: "Cuarentena",
    ProcessOutcome.ERROR: "Error",
    ProcessOutcome.SKIPPED_MISSING: "Omitido",
}
_OUTCOME_ROW_TAG: dict[ProcessOutcome, str] = {
    ProcessOutcome.MOVED: "ok",
    ProcessOutcome.DRY_RUN: "ok",
    ProcessOutcome.UNCLASSIFIED: "warn",
    ProcessOutcome.DUPLICATE: "warn",
    ProcessOutcome.NEEDS_REVIEW: "warn",
    ProcessOutcome.QUARANTINED: "warn",
    ProcessOutcome.ERROR: "error",
    ProcessOutcome.SKIPPED_MISSING: "warn",
}
_STAT_CARDS = (
    ("detected", "Detectados", Palette.TEXT),
    ("archived", "Archivados", Palette.SUCCESS),
    ("review", "Para revisar", Palette.WARNING),
    ("error", "Errores", Palette.ERROR),
)


class MainWindow(ctk.CTkFrame):
    """Frame raiz que contiene toda la interfaz y coordina el motor."""

    def __init__(self, master: ctk.CTk, store: ConfigStore, first_run: bool = False) -> None:
        super().__init__(master, fg_color=Palette.BG, corner_radius=0)
        self._store = store
        self._first_run = first_run
        self._events: queue.Queue[EngineEvent] = queue.Queue()
        self._ledger = _open_ledger()
        self._engine = ProcessingEngine(store.get, self._events.put, ledger=self._ledger)
        self._societies: list[SocietyMapping] = []
        self._counts = {"detected": 0, "archived": 0, "review": 0, "error": 0}
        self._last_pending = 0  # Para avisar solo cuando aumentan los pendientes.
        self._stat_values: dict[str, tk.StringVar] = {}
        self._nav_items: dict[str, tuple[ctk.CTkFrame, ctk.CTkButton]] = {}

        self._family = font_family(self)
        self._init_fonts()
        self._init_vars()
        configure_table_style(self, self._family)
        self._build_layout()
        self._load_config_into_widgets()
        self._set_running(False)
        self._show("monitor")
        self.after(_POLL_INTERVAL_MS, self._poll_events)
        self._poll_pending()
        if self._first_run:
            self.after(250, self._run_onboarding)  # Setup guiado tras dibujar la ventana.

    def _run_onboarding(self) -> None:
        dialog = OnboardingDialog(self, self._store.get())
        self.wait_window(dialog)
        if dialog.result is not None and self._save(dialog.result):
            self._load_config_into_widgets()

    def _init_fonts(self) -> None:
        self._f_h1 = ctk.CTkFont(self._family, 22, "bold")
        self._f_h2 = ctk.CTkFont(self._family, 15, "bold")
        self._f_body = ctk.CTkFont(self._family, 13)
        self._f_body_bold = ctk.CTkFont(self._family, 13, "bold")
        self._f_small = ctk.CTkFont(self._family, 12)
        self._f_hint = ctk.CTkFont(self._family, 11)
        self._f_stat = ctk.CTkFont(self._family, 26, "bold")

    def _init_vars(self) -> None:
        self._input_var = tk.StringVar()
        self._output_var = tk.StringVar()
        self._unknown_var = tk.StringVar()
        self._quarantine_var = tk.StringVar()
        self._dry_run_var = tk.BooleanVar()
        self._stability_var = tk.BooleanVar()
        self._notify_var = tk.BooleanVar()
        self._timeout_var = tk.StringVar()
        self._template_var = tk.StringVar()
        self._state_var = tk.StringVar(value="Detenido")  # Estado corto para el pill del sidebar.
        self._detail_var = tk.StringVar(value="Listo para empezar")  # Detalle largo para el header.
        self._pending_var = tk.StringVar()  # Cantidad de archivos que esperan revision.

    # --- Fabricas de widgets reutilizables ---------------------------------

    def _primary_button(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        # Primario: color de marca (lima). La accion protagonista de cada vista.
        return ctk.CTkButton(
            parent,
            text=text,
            font=self._f_h2,
            height=44,
            corner_radius=CORNER_RADIUS,
            fg_color=Palette.ACCENT,
            hover_color=Palette.ACCENT_HOVER,
            text_color=Palette.ACCENT_TEXT,
            command=command,
        )

    def _secondary_button(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        # Secundario: oscuro con texto blanco. Fuerte pero por debajo del primario.
        return ctk.CTkButton(
            parent,
            text=text,
            font=self._f_body,
            height=40,
            corner_radius=CORNER_RADIUS,
            fg_color=Palette.PRIMARY,
            hover_color=Palette.SIDEBAR_HOVER,
            text_color="#ffffff",
            command=command,
        )

    def _ghost_button(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        # Terciario: gris apagado que se enciende (color + fondo sutil) al pasar el mouse.
        button = ctk.CTkButton(
            parent,
            text=text,
            font=self._f_body,
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

    def _hint(self, parent: tk.Misc, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(parent, text=text, font=self._f_hint, text_color=Palette.MUTED, anchor="w", justify="left")

    # --- Estructura general -------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        content = ctk.CTkFrame(self, fg_color=Palette.BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self._monitor_view = ctk.CTkFrame(content, fg_color=Palette.BG, corner_radius=0)
        self._history_view = ctk.CTkFrame(content, fg_color=Palette.BG, corner_radius=0)
        self._config_view = ctk.CTkScrollableFrame(content, fg_color=Palette.BG, corner_radius=0)
        self._views = {
            "monitor": self._monitor_view,
            "history": self._history_view,
            "config": self._config_view,
        }
        self._build_monitor_view()
        self._build_history_view()
        self._build_config_view()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=224, fg_color=Palette.SIDEBAR, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 28))
        create_brand_mark(brand).pack(side="left", padx=(0, 12))
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Automator", font=self._f_h2, text_color="#ffffff").pack(anchor="w")
        ctk.CTkLabel(
            titles, text=f"Facturas AFIP  ·  v{__version__}", font=self._f_hint, text_color=Palette.MUTED_ON_DARK
        ).pack(anchor="w")

        self._nav_item(sidebar, "monitor", "Monitor", row=1)
        self._nav_item(sidebar, "history", "Historial", row=2)
        self._nav_item(sidebar, "config", "Configuracion", row=3)
        self._build_status_pill(sidebar)

    def _nav_item(self, parent: ctk.CTkFrame, key: str, text: str, row: int) -> None:
        item = ctk.CTkFrame(parent, fg_color="transparent", height=40)
        item.grid(row=row, column=0, sticky="ew", padx=12, pady=2)
        item.grid_columnconfigure(1, weight=1)
        item.grid_rowconfigure(0, weight=1)
        item.grid_propagate(False)
        strip = ctk.CTkFrame(item, width=4, fg_color="transparent", corner_radius=2)
        strip.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        button = ctk.CTkButton(
            item,
            text=text,
            anchor="w",
            height=40,
            corner_radius=8,
            font=self._f_body,
            fg_color="transparent",
            hover_color=Palette.SIDEBAR_HOVER,
            text_color=Palette.MUTED_ON_DARK,
            command=lambda: self._show(key),
        )
        button.grid(row=0, column=1, sticky="nsew")
        self._nav_items[key] = (strip, button)

    def _build_status_pill(self, parent: ctk.CTkFrame) -> None:
        pill = ctk.CTkFrame(parent, fg_color=Palette.SIDEBAR_HOVER, corner_radius=10)
        pill.grid(row=5, column=0, sticky="ew", padx=14, pady=20)
        self._status_dot = ctk.CTkLabel(pill, text="●", font=self._f_body, text_color=Palette.MUTED_ON_DARK)
        self._status_dot.pack(side="left", padx=(12, 6), pady=10)
        ctk.CTkLabel(pill, textvariable=self._state_var, font=self._f_small, text_color=Palette.TEXT_ON_DARK).pack(
            side="left", padx=(0, 12), pady=10
        )

    def _show(self, key: str) -> None:
        # Solo una vista montada a la vez: evita solapamientos de render entre el
        # frame de monitoreo y el scrollable de configuracion.
        for name, view in self._views.items():
            if name == key:
                view.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
            else:
                view.grid_remove()
        if key == "history":
            self._refresh_history()
        for name, (strip, button) in self._nav_items.items():
            active = name == key
            strip.configure(fg_color=Palette.ACCENT if active else "transparent")
            button.configure(
                fg_color=Palette.SIDEBAR_HOVER if active else "transparent",
                text_color="#ffffff" if active else Palette.MUTED_ON_DARK,
            )

    # --- Vista Monitor ------------------------------------------------------

    def _build_monitor_view(self) -> None:
        self._monitor_view.grid_columnconfigure(0, weight=1)
        self._monitor_view.grid_rowconfigure(3, weight=1)
        self._build_monitor_header()
        self._build_stats()
        self._build_pending_banner()
        self._build_activity_log()

    def _build_monitor_header(self) -> None:
        header = ctk.CTkFrame(self._monitor_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(titles, text="Monitor de facturas", font=self._f_h1, text_color=Palette.TEXT).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            textvariable=self._detail_var,
            font=self._f_body,
            text_color=Palette.MUTED,
            wraplength=520,
            justify="left",
        ).pack(anchor="w")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="e")
        self._toggle_btn = self._primary_button(controls, "Iniciar", self._toggle)
        self._toggle_btn.configure(width=150)
        self._toggle_btn.pack(side="left")

    def _build_stats(self) -> None:
        row = ctk.CTkFrame(self._monitor_view, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        for index, (key, label, color) in enumerate(_STAT_CARDS):
            row.grid_columnconfigure(index, weight=1)
            self._build_stat_card(row, index, key, label, color)

    def _build_stat_card(self, parent: ctk.CTkFrame, column: int, key: str, label: str, color: str) -> None:
        card = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 14, 0))
        var = tk.StringVar(value="0")
        self._stat_values[key] = var
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(anchor="w", padx=20, pady=(18, 0))
        ctk.CTkLabel(header, text="●", font=self._f_hint, text_color=color).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(header, text=label.upper(), font=self._f_hint, text_color=Palette.MUTED).pack(side="left")
        ctk.CTkLabel(card, textvariable=var, font=self._f_stat, text_color=Palette.TEXT).pack(
            anchor="w", padx=20, pady=(2, 18)
        )

    def _build_pending_banner(self) -> None:
        # Verdad persistente leida de las carpetas: aunque se pierda un evento de la
        # UI, el usuario ve que hay archivos esperando su atencion.
        banner = ctk.CTkFrame(self._monitor_view, fg_color=Palette.ROW_WARNING, corner_radius=CORNER_RADIUS)
        banner.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(banner, textvariable=self._pending_var, font=self._f_body, text_color=Palette.WARNING).grid(
            row=0, column=0, sticky="w", padx=18, pady=12
        )
        ctk.CTkButton(
            banner,
            text="Abrir carpeta de revision",
            width=190,
            height=34,
            corner_radius=CORNER_RADIUS,
            font=self._f_small,
            fg_color=Palette.SURFACE,
            hover_color=Palette.BORDER,
            text_color=Palette.TEXT,
            border_width=1,
            border_color=Palette.BORDER,
            command=self._open_review,
        ).grid(row=0, column=1, sticky="e", padx=(0, 12), pady=8)
        self._pending_banner = banner  # Se muestra/oculta segun haya pendientes.

    def _build_activity_log(self) -> None:
        card = ctk.CTkFrame(self._monitor_view, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=3, column=0, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="Actividad reciente", font=self._f_h2, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", padx=22, pady=(18, 8)
        )
        self._build_log_table(card)

    def _build_log_table(self, parent: ctk.CTkFrame) -> None:
        container = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=0)
        container.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        columns = ("hora", "archivo", "tipo", "estado", "destino")
        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse", style="Activity.Treeview")
        self._configure_log_columns(tree)
        tree.tag_configure("ok", background=Palette.ROW_SUCCESS)
        tree.tag_configure("warn", background=Palette.ROW_WARNING)
        tree.tag_configure("error", background=Palette.ROW_ERROR)

        scroll = ctk.CTkScrollbar(container, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self._log = tree
        self._empty_state = self._build_empty_state(container)

    def _build_empty_state(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        # Cubre la tabla vacia con un mensaje amable en vez de un vacio blanco.
        frame = ctk.CTkFrame(parent, fg_color=Palette.SURFACE, corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.place(relx=0.5, rely=0.42, anchor="center")
        ctk.CTkLabel(inner, text="Todavia no hay actividad", font=self._f_h2, text_color=Palette.TEXT).pack()
        ctk.CTkLabel(
            inner,
            text='Apreta "Iniciar" y las facturas procesadas van a aparecer aca.',
            font=self._f_body,
            text_color=Palette.MUTED,
        ).pack(pady=(4, 0))
        return frame

    def _configure_log_columns(self, tree: ttk.Treeview) -> None:
        headings = {
            "hora": ("Hora", 70),
            "archivo": ("Archivo", 220),
            "tipo": ("Comprobante", 110),
            "estado": ("Estado", 110),
            "destino": ("Destino", 340),
        }
        for column, (text, width) in headings.items():
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="w", stretch=(column == "destino"))

    # --- Vista Historial ----------------------------------------------------

    def _build_history_view(self) -> None:
        self._history_view.grid_columnconfigure(0, weight=1)
        self._history_view.grid_rowconfigure(2, weight=1)
        self._build_history_header()
        self._build_history_toolbar()
        self._build_history_table()

    def _build_history_header(self) -> None:
        header = ctk.CTkFrame(self._history_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(header, text="Historial", font=self._f_h1, text_color=Palette.TEXT).pack(anchor="w")
        self._hint(header, "Todo lo procesado queda registrado, incluso tras cerrar la app.").pack(
            anchor="w", pady=(4, 0)
        )

    def _build_history_toolbar(self) -> None:
        bar = ctk.CTkFrame(self._history_view, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        # Jerarquia: accion protagonista a la izquierda, refrescar como control sutil a la derecha.
        self._retry_btn = self._primary_button(bar, f"{_ICON_RETRY}  Reintentar pendientes", self._reprocess_pending)
        self._retry_btn.configure(height=40)
        self._retry_btn.pack(side="left", padx=(0, 10))
        self._undo_btn = self._secondary_button(bar, f"{_ICON_UNDO}  Deshacer ultimo movimiento", self._undo_last)
        self._undo_btn.pack(side="left")
        self._ghost_button(bar, f"{_ICON_REFRESH}  Actualizar", self._refresh_history).pack(side="right")

    def _update_history_actions(self) -> None:
        # Deshabilita lo que no se puede usar ahora: nada que deshacer, o nada pendiente.
        running = self._engine.is_running
        can_undo = not running and self._ledger is not None and self._ledger.last_undoable() is not None
        self._undo_btn.configure(state="normal" if can_undo else "disabled")
        self._retry_btn.configure(state="normal" if self._count_pending() > 0 else "disabled")

    def _build_history_table(self) -> None:
        card = ctk.CTkFrame(self._history_view, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        columns = ("fecha", "archivo", "comprobante", "estado", "destino")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="browse", style="Activity.Treeview")
        headings = {
            "fecha": ("Fecha", 150),
            "archivo": ("Archivo", 200),
            "comprobante": ("Comprobante", 110),
            "estado": ("Estado", 130),
            "destino": ("Destino", 320),
        }
        for column, (text, width) in headings.items():
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="w", stretch=(column == "destino"))
        for tag, color in (("ok", Palette.ROW_SUCCESS), ("warn", Palette.ROW_WARNING), ("error", Palette.ROW_ERROR)):
            tree.tag_configure(tag, background=color)
        scroll = ctk.CTkScrollbar(card, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(18, 0), pady=18)
        scroll.grid(row=0, column=1, sticky="ns", padx=(6, 12), pady=18)
        self._history_tree = tree

    def _refresh_history(self) -> None:
        if self._ledger is None:
            return
        self._history_tree.delete(*self._history_tree.get_children())
        for record in self._ledger.recent():
            self._history_tree.insert("", "end", values=_history_row(record), tags=(_history_tag(record),))
        self._update_history_actions()

    def _undo_last(self) -> None:
        if self._ledger is None:
            return
        if self._engine.is_running:
            messagebox.showinfo("Deshacer", "Deten el monitor antes de deshacer, asi no se reprocesa al instante.")
            return
        record = self._ledger.last_undoable()
        if record is None or record.destination is None:
            messagebox.showinfo("Deshacer", "No hay movimientos para deshacer.")
            return
        self._perform_undo(record)

    def _perform_undo(self, record: LedgerRecord) -> None:
        if self._ledger is None or record.destination is None:
            return
        source = Path(record.destination)
        if not source.exists():
            self._ledger.mark_reverted(record.id)
            messagebox.showwarning("Deshacer", "El archivo ya no esta en su destino; se marco como deshecho.")
            self._refresh_history()
            return
        try:
            file_ops.move_file(source, self._store.get().input_folder, source.name)
        except OSError as exc:
            messagebox.showerror("Deshacer", f"No se pudo devolver el archivo: {exc}")
            return
        self._ledger.mark_reverted(record.id)
        messagebox.showinfo("Deshacer", f"Se devolvio {source.name} a la carpeta de entrada.")
        self._refresh_history()

    def _reprocess_pending(self) -> None:
        def run() -> None:
            if not self._engine.is_running:
                self._engine.start()
            count = self._engine.reprocess_pending()
            logger.info("Reintentando %d archivos pendientes", count)

        _run_async(run)

    # --- Vista Configuracion ------------------------------------------------

    def _build_config_view(self) -> None:
        self._config_view.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._config_view, text="Configuracion", font=self._f_h1, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._hint(self._config_view, "Configura esto una vez. Los cambios se guardan con el boton de abajo.").grid(
            row=1, column=0, sticky="w", pady=(0, 18)
        )
        self._build_main_folders_card()
        self._build_societies_card()
        self._build_options_card()
        self._build_advanced_folders_card()
        self._build_config_actions()

    def _card(self, title: str, subtitle: str, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._config_view, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 18))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=self._f_h2, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 0)
        )
        self._hint(card, subtitle).grid(row=1, column=0, sticky="w", padx=20, pady=(2, 8))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        return body

    def _folder_field(self, parent: tk.Misc, label: str, hint: str, var: tk.StringVar, row: int) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(block, text=label, font=self._f_body, text_color=Palette.TEXT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ctk.CTkEntry(block, textvariable=var, height=38).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkButton(
            block,
            text="Elegir carpeta...",
            width=140,
            height=38,
            corner_radius=CORNER_RADIUS,
            fg_color=Palette.SURFACE_ALT,
            hover_color=Palette.BORDER,
            text_color=Palette.TEXT,
            border_width=1,
            border_color=Palette.BORDER,
            command=lambda: self._pick_folder(var),
        ).grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
        self._hint(block, hint).grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

    def _build_main_folders_card(self) -> None:
        body = self._card("Carpetas principales", "Las dos carpetas que si o si tenes que elegir.", row=2)
        self._folder_field(
            body,
            "Carpeta de entrada",
            "Donde caen los PDF que descargas (por ejemplo, tu carpeta Descargas).",
            self._input_var,
            row=0,
        )
        self._folder_field(
            body,
            "Carpeta de salida",
            "Donde se van a guardar las facturas ya ordenadas por empresa y proveedor.",
            self._output_var,
            row=1,
        )

    def _build_societies_card(self) -> None:
        body = self._card(
            "Empresas (sociedades)",
            "Cada factura se guarda en la carpeta de la empresa segun su CUIT. Agrega las tuyas aca.",
            row=3,
        )
        self._societies_list = ctk.CTkFrame(body, fg_color="transparent")
        self._societies_list.grid(row=0, column=0, sticky="ew")
        self._societies_list.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            body,
            text="+  Agregar empresa",
            height=40,
            corner_radius=CORNER_RADIUS,
            font=self._f_body,
            fg_color=Palette.PRIMARY,
            hover_color=Palette.PRIMARY_HOVER,
            text_color="#ffffff",
            command=self._add_society,
        ).grid(row=1, column=0, sticky="ew", pady=(12, 0))

    def _refresh_societies_list(self) -> None:
        for child in self._societies_list.winfo_children():
            child.destroy()
        if not self._societies:
            self._hint(self._societies_list, "Todavia no agregaste ninguna empresa.").grid(
                row=0, column=0, sticky="w", pady=6
            )
            return
        for index, society in enumerate(self._societies):
            self._build_society_row(index, society)

    def _build_society_row(self, index: int, society: SocietyMapping) -> None:
        row = ctk.CTkFrame(self._societies_list, fg_color=Palette.SURFACE_ALT, corner_radius=CORNER_RADIUS)
        row.grid(row=index, column=0, sticky="ew", pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=0, sticky="w", padx=14, pady=10)
        ctk.CTkLabel(info, text=society.name, font=self._f_h2, text_color=Palette.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            info,
            text=f"CUIT {_format_cuit(society.cuit)}   -   {society.folder}",
            font=self._f_hint,
            text_color=Palette.MUTED,
            anchor="w",
        ).pack(anchor="w")
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=(0, 12))
        self._row_button(actions, "Editar", Palette.TEXT, lambda: self._edit_society(index)).pack(side="left", padx=6)
        self._row_button(actions, "Eliminar", Palette.ERROR, lambda: self._remove_society(index)).pack(side="left")

    def _row_button(self, parent: tk.Misc, text: str, color: str, command: Callable[[], None]) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=78,
            height=32,
            corner_radius=8,
            font=self._f_small,
            fg_color=Palette.SURFACE,
            hover_color=Palette.BORDER,
            text_color=color,
            border_width=1,
            border_color=Palette.BORDER,
            command=command,
        )

    def _build_options_card(self) -> None:
        body = self._card("Opciones", "Valores comodos por defecto. Podes dejarlos como estan.", row=4)
        ctk.CTkCheckBox(
            body,
            text="Modo de prueba (no mueve nada, solo muestra que haria)",
            font=self._f_body,
            variable=self._dry_run_var,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._hint(body, "Util la primera vez, para ver como clasifica sin tocar tus archivos.").grid(
            row=1, column=0, sticky="w", pady=(0, 10)
        )
        ctk.CTkCheckBox(
            body,
            text="Esperar a que termine la descarga antes de procesar",
            font=self._f_body,
            variable=self._stability_var,
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))
        timeout_row = ctk.CTkFrame(body, fg_color="transparent")
        timeout_row.grid(row=3, column=0, sticky="w", pady=(0, 10))
        ctk.CTkLabel(timeout_row, text="Espera maxima (segundos)", font=self._f_body, text_color=Palette.TEXT).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkEntry(timeout_row, textvariable=self._timeout_var, width=80, height=36).pack(side="left")
        ctk.CTkCheckBox(
            body,
            text="Avisar con una notificacion cuando algo necesita revision",
            font=self._f_body,
            variable=self._notify_var,
        ).grid(row=4, column=0, sticky="w", pady=(0, 10))
        template_block = ctk.CTkFrame(body, fg_color="transparent")
        template_block.grid(row=5, column=0, sticky="ew")
        template_block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            template_block, text="Estructura de carpetas", font=self._f_body, text_color=Palette.TEXT, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(template_block, textvariable=self._template_var, height=36).grid(
            row=1, column=0, sticky="ew", pady=(4, 0)
        )
        self._hint(
            template_block,
            "Dentro de la carpeta de cada empresa. Tokens: {supplier} {year} {month} {day}. "
            "Ej: {year}/{month}/{supplier} archiva por ano y mes.",
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

    def _build_advanced_folders_card(self) -> None:
        body = self._card(
            "Carpetas automaticas (avanzado)",
            "Se crean solas. Cambialas solo si sabes lo que haces.",
            row=5,
        )
        self._folder_field(
            body,
            "Facturas sin clasificar",
            "Para facturas de un CUIT que no configuraste.",
            self._unknown_var,
            row=0,
        )
        self._folder_field(
            body,
            "Cuarentena",
            "Para PDF ilegibles o con errores, que no se pudieron archivar.",
            self._quarantine_var,
            row=1,
        )

    def _build_config_actions(self) -> None:
        bar = ctk.CTkFrame(self._config_view, fg_color="transparent")
        bar.grid(row=6, column=0, sticky="ew", pady=(4, 24))
        bar.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        self._ghost_button(left, "Abrir carpeta de entrada", self._open_input).pack(side="left", padx=(0, 10))
        self._ghost_button(left, "Abrir carpeta de salida", self._open_output).pack(side="left", padx=(0, 10))
        self._ghost_button(left, "Abrir carpeta de logs", self._open_logs).pack(side="left")
        self._primary_button(bar, "Guardar configuracion", self._save_config).grid(row=0, column=1, sticky="e")

    # --- Carga y recoleccion de configuracion ------------------------------

    def _load_config_into_widgets(self) -> None:
        config = self._store.get()
        self._input_var.set(str(config.input_folder))
        self._output_var.set(str(config.base_output_folder))
        self._unknown_var.set(str(config.unknown_folder))
        self._quarantine_var.set(str(config.quarantine_folder))
        self._dry_run_var.set(config.dry_run)
        self._stability_var.set(config.wait_for_stability)
        self._notify_var.set(config.notify)
        self._timeout_var.set(str(config.stability_timeout_s))
        self._template_var.set(config.destination_template)
        self._societies = list(config.societies)
        self._refresh_societies_list()

    def _collect_config(self) -> AppConfig | None:
        paths = (self._input_var, self._output_var, self._unknown_var, self._quarantine_var)
        if any(not var.get().strip() for var in paths):
            messagebox.showerror("Configuracion incompleta", "Todas las carpetas son obligatorias.")
            return None
        timeout = self._parse_timeout()
        if timeout is None:
            return None
        try:
            return self._build_config(timeout)
        except ValidationError as exc:
            messagebox.showerror("Configuracion invalida", _format_validation_error(exc))
            return None

    def _parse_timeout(self) -> float | None:
        try:
            return float(self._timeout_var.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showerror("Valor invalido", "El tiempo de espera debe ser un numero.")
            return None

    def _build_config(self, timeout: float) -> AppConfig:
        return AppConfig(
            input_folder=Path(self._input_var.get().strip()),
            base_output_folder=Path(self._output_var.get().strip()),
            unknown_folder=Path(self._unknown_var.get().strip()),
            quarantine_folder=Path(self._quarantine_var.get().strip()),
            societies=tuple(self._societies),
            dry_run=self._dry_run_var.get(),
            wait_for_stability=self._stability_var.get(),
            stability_timeout_s=timeout,
            destination_template=self._template_var.get().strip() or "{supplier}",
            notify=self._notify_var.get(),
        )

    # --- Acciones de sociedades --------------------------------------------

    def _add_society(self) -> None:
        dialog = SocietyDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            self._societies.append(dialog.result)
            self._refresh_societies_list()

    def _edit_society(self, index: int) -> None:
        dialog = SocietyDialog(self, existing=self._societies[index])
        self.wait_window(dialog)
        if dialog.result is not None:
            self._societies[index] = dialog.result
            self._refresh_societies_list()

    def _remove_society(self, index: int) -> None:
        del self._societies[index]
        self._refresh_societies_list()

    # --- Control del motor --------------------------------------------------

    def _toggle(self) -> None:
        if self._engine.is_running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        config = self._collect_config()
        if config is None or not self._save(config):
            return
        self._toggle_btn.configure(state="disabled")
        self._state_var.set("Iniciando...")
        self._detail_var.set("Iniciando el monitoreo...")
        _run_async(self._engine.start)

    def _stop(self) -> None:
        self._toggle_btn.configure(state="disabled")
        self._state_var.set("Deteniendo...")
        _run_async(self._engine.stop)

    def _save_config(self) -> None:
        config = self._collect_config()
        if config is None:
            return
        was_running = self._engine.is_running
        if was_running:
            self._stop()
        if self._save(config):
            messagebox.showinfo("Configuracion", "Configuracion guardada correctamente.")
        if was_running:
            self._start()

    def _save(self, config: AppConfig) -> bool:
        try:
            self._store.update(config)
        except OSError as exc:
            logger.exception("No se pudo guardar la configuracion")
            messagebox.showerror("Error al guardar", f"No se pudo guardar la configuracion: {exc}")
            return False
        return True

    def _set_running(self, running: bool) -> None:
        self._toggle_btn.configure(
            state="normal",
            text="Detener" if running else "Iniciar",
            fg_color=Palette.ERROR if running else Palette.ACCENT,
            hover_color="#B83A3A" if running else Palette.ACCENT_HOVER,
            text_color="#ffffff" if running else Palette.ACCENT_TEXT,
        )
        self._status_dot.configure(text_color=Palette.SUCCESS if running else Palette.MUTED_ON_DARK)
        self._state_var.set("En ejecucion" if running else "Detenido")
        if not running:
            self._detail_var.set("Monitoreo detenido")
        # Deshacer depende de que el monitor este detenido; refleja el cambio al instante.
        if hasattr(self, "_undo_btn"):
            self._update_history_actions()

    # --- Pickers y navegacion ----------------------------------------------

    def _pick_folder(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Selecciona una carpeta")
        if chosen:
            var.set(chosen)

    def _open_input(self) -> None:
        open_folder(Path(self._input_var.get().strip() or "."))

    def _open_output(self) -> None:
        open_folder(Path(self._output_var.get().strip() or "."))

    def _open_review(self) -> None:
        open_folder(self._store.get().review_folder)

    def _open_logs(self) -> None:
        open_folder(log_dir())

    # --- Pendientes de revision (verdad leida de las carpetas) --------------

    def _poll_pending(self) -> None:
        # Se reprograma siempre (finally) para que un error de conteo no corte el aviso.
        try:
            count = self._count_pending()
            if count > 0:
                self._pending_var.set(f"{count} pendiente{'s' if count != 1 else ''} de revision")
                self._pending_banner.grid(row=2, column=0, sticky="ew", pady=(0, 20))
            else:
                self._pending_banner.grid_remove()
            self._maybe_notify_pending(count)
            if hasattr(self, "_retry_btn"):
                self._retry_btn.configure(state="normal" if count > 0 else "disabled")
        finally:
            self.after(_PENDING_POLL_MS, self._poll_pending)

    def _maybe_notify_pending(self, count: int) -> None:
        # Avisa solo cuando aparecen nuevos pendientes y el usuario lo habilito.
        if count > self._last_pending and self._store.get().notify:
            _run_async(lambda: notify("Automator", f"{count} factura(s) necesitan tu revision"))
        self._last_pending = count

    def _count_pending(self) -> int:
        config = self._store.get()
        folders = (config.review_folder, config.quarantine_folder, config.unknown_folder)
        return sum(_count_pdfs(folder) for folder in folders)

    # --- Bucle de eventos del motor ----------------------------------------

    def _poll_events(self) -> None:
        # El bucle se reprograma siempre (finally): un evento defectuoso no puede
        # dejar a la UI sin procesar mas eventos del motor.
        try:
            while True:
                try:
                    event = self._events.get_nowait()
                except queue.Empty:
                    break
                self._safe_handle_event(event)
        finally:
            self.after(_POLL_INTERVAL_MS, self._poll_events)

    def _safe_handle_event(self, event: EngineEvent) -> None:
        try:
            self._handle_event(event)
        except Exception:
            logger.exception("Error procesando un evento del motor en la interfaz")

    def _handle_event(self, event: EngineEvent) -> None:
        if event.type is EngineEventType.STARTED:
            self._set_running(True)
            self._detail_var.set(event.message)
        elif event.type is EngineEventType.STOPPED:
            self._set_running(False)
        elif event.type is EngineEventType.DETECTED:
            self._increment("detected")
        elif event.type is EngineEventType.RESULT and event.result is not None:
            self._on_result(event.result)
        elif event.type is EngineEventType.ERROR:
            self._on_error(event)

    def _on_error(self, event: EngineEvent) -> None:
        if event.path is None:
            # Error sin archivo asociado (arranque fallido o carpeta ilegible en
            # ejecucion): se avisa y se refleja el estado real del motor.
            self._set_running(self._engine.is_running)
            messagebox.showerror("Automator", event.message)
            return
        self._increment("error")
        self._append_log(event.path.name, "", "Error", "error", event.message)

    def _on_result(self, result: ProcessResult) -> None:
        if result.outcome is ProcessOutcome.SKIPPED_MISSING:
            return
        self._increment(_count_key(result.outcome))
        voucher = result.invoice.voucher.label if result.invoice else ""
        destination = str(result.destination) if result.destination else result.message
        self._append_log(
            result.source.name, voucher, _OUTCOME_LABELS[result.outcome], _OUTCOME_ROW_TAG[result.outcome], destination
        )

    def _append_log(self, filename: str, voucher: str, status: str, tag: str, destination: str) -> None:
        self._empty_state.grid_remove()  # Ya hay actividad: se descubre la tabla.
        now = dt.datetime.now().strftime("%H:%M:%S")
        self._log.insert("", 0, values=(now, filename, voucher, status, destination), tags=(tag,))
        children = self._log.get_children()
        if len(children) > _MAX_LOG_ROWS:
            self._log.delete(children[-1])

    def _increment(self, key: str) -> None:
        self._counts[key] += 1
        self._stat_values[key].set(str(self._counts[key]))

    def on_close(self) -> None:
        # Se detiene de forma sincronica para que el worker termine el archivo en
        # curso antes de cerrar: abandonar un movimiento a mitad podria dejar un
        # PDF corrupto en el destino. stop() ya limita la espera con un timeout.
        self._engine.stop()
        if self._ledger is not None:
            self._ledger.close()
        self.winfo_toplevel().destroy()


def _run_async(target: Callable[[], object]) -> None:
    threading.Thread(target=target, daemon=True).start()


def _count_key(outcome: ProcessOutcome) -> str:
    if outcome in (ProcessOutcome.MOVED, ProcessOutcome.DRY_RUN):
        return "archived"
    if outcome in (
        ProcessOutcome.UNCLASSIFIED,
        ProcessOutcome.DUPLICATE,
        ProcessOutcome.NEEDS_REVIEW,
        ProcessOutcome.QUARANTINED,
    ):
        return "review"
    return "error"


def _format_validation_error(exc: ValidationError) -> str:
    return "\n".join(str(error["msg"]) for error in exc.errors())


def _format_cuit(cuit: str) -> str:
    # Muestra el CUIT de 11 digitos como XX-XXXXXXXX-X; si no, tal cual.
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}" if len(cuit) == _CUIT_LENGTH else cuit


def _count_pdfs(folder: Path) -> int:
    try:
        return sum(1 for path in folder.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    except OSError:
        return 0


def _history_row(record: LedgerRecord) -> tuple[str, str, str, str, str]:
    when = record.ts.replace("T", "  ")
    estado = _OUTCOME_LABELS.get(record.outcome, record.outcome.value)
    if record.reverted:
        estado = f"{estado} (deshecho)"
    destino = record.destination or record.message
    return (when, record.source_name, record.voucher or "", estado, destino)


def _history_tag(record: LedgerRecord) -> str:
    return "warn" if record.reverted else _OUTCOME_ROW_TAG.get(record.outcome, "warn")


def _open_ledger() -> Ledger | None:
    # Si el historial no se puede abrir, la app funciona igual (sin historial/undo/dedup).
    try:
        return Ledger(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el historial; se continua sin el")
        return None
