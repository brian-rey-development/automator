"""Main window: brand sidebar, monitoring panel and configuration.

The interface is designed for someone without experience: clear labels, help
text below each field and folder pickers everywhere.
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
from automator.domain.suppliers import Supplier
from automator.services import file_ops
from automator.services.engine import EngineEvent, EngineEventType, ProcessingEngine
from automator.services.excel_import import (
    ExcelReadError,
    MissingColumnError,
    parse_societies,
    parse_suppliers,
    read_rows,
)
from automator.services.ledger import Ledger, LedgerRecord
from automator.services.supplier_store import SupplierRegistryStore, SupplierStore
from automator.ui.import_report_dialog import ImportReportDialog
from automator.ui.onboarding import OnboardingDialog
from automator.ui.society_dialog import SocietyDialog
from automator.ui.system_utils import notify, open_folder
from automator.ui.theme import CORNER_RADIUS, Palette, configure_table_style, create_brand_mark, font_family

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 150
_PENDING_POLL_MS = 5000  # Re-reads the pending folders every 5s.
_MAX_LOG_ROWS = 500
_MAX_SUPPLIER_RESULTS = 20  # The search shows a bounded slice, never thousands of rows.
_CUIT_LENGTH = 11

# Icon glyphs: inherit the button text color and do not depend on assets.
_ICON_RETRY = "↻"  # circular arrow: retry
_ICON_UNDO = "↶"  # return arrow: undo
_ICON_REFRESH = "⟳"  # wide circular arrow: refresh
_RESTORE_CONFIRM = (
    "Se borra el historial de procesamiento: duplicados, revisiones y archivos ya vistos.\n\n"
    "Los PDF no se mueven ni se eliminan.\n\n"
    "Despues vas a poder reprocesar y revisar de nuevo. Continuar?"
)

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
    """Root frame that contains the whole interface and coordinates the engine."""

    def __init__(self, master: ctk.CTk, store: ConfigStore, first_run: bool = False) -> None:
        super().__init__(master, fg_color=Palette.BG, corner_radius=0)
        self._store = store
        self._first_run = first_run
        self._events: queue.Queue[EngineEvent] = queue.Queue()
        self._ledger = _open_ledger()
        self._supplier_store = _open_supplier_store()
        self._registry_store = SupplierRegistryStore(self._supplier_store) if self._supplier_store is not None else None
        self._engine = ProcessingEngine(
            store.get,
            self._events.put,
            ledger=self._ledger,
            registry_provider=self._registry_store.get if self._registry_store is not None else None,
        )
        self._societies: list[SocietyMapping] = []
        self._counts = {"detected": 0, "archived": 0, "review": 0, "error": 0}
        self._last_pending = 0  # To notify only when the pending count grows.
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
            self.after(250, self._run_onboarding)  # Guided setup after drawing the window.

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
        self._orders_var = tk.StringVar()
        self._dry_run_var = tk.BooleanVar()
        self._stability_var = tk.BooleanVar()
        self._notify_var = tk.BooleanVar()
        self._copy_var = tk.BooleanVar()
        self._timeout_var = tk.StringVar()
        self._template_var = tk.StringVar()
        self._state_var = tk.StringVar(value="Detenido")  # Short status for the sidebar pill.
        self._detail_var = tk.StringVar(value="Listo para empezar")  # Long detail for the header.
        self._pending_var = tk.StringVar()  # Number of files waiting for review.
        self._supplier_count_var = tk.StringVar(value="0 proveedores")
        self._supplier_search_var = tk.StringVar()

    # --- Reusable widget factories -----------------------------------------

    def _primary_button(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        # Primary: brand color (lime). The lead action of each view.
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
        # Secondary: dark with white text. Strong but below the primary.
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
        # Tertiary: muted gray that lights up (color + subtle background) on hover.
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

    # --- General structure --------------------------------------------------

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
        # Only one view mounted at a time: avoids render overlaps between the
        # monitoring frame and the configuration scrollable.
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

    # --- Monitor view -------------------------------------------------------

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
        # Persistent truth read from the folders: even if a UI event is lost, the
        # user sees that there are files waiting for their attention.
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
        self._pending_banner = banner  # Shown/hidden depending on whether there are pendings.

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
        # Covers the empty table with a friendly message instead of a blank void.
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

    # --- History view -------------------------------------------------------

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
        # Hierarchy: lead action on the left, refresh as a subtle control on the right.
        self._retry_btn = self._primary_button(bar, f"{_ICON_RETRY}  Reintentar pendientes", self._reprocess_pending)
        self._retry_btn.configure(height=40)
        self._retry_btn.pack(side="left", padx=(0, 10))
        self._undo_btn = self._secondary_button(bar, f"{_ICON_UNDO}  Deshacer ultimo movimiento", self._undo_last)
        self._undo_btn.pack(side="left")
        self._ghost_button(bar, f"{_ICON_REFRESH}  Actualizar", self._refresh_history).pack(side="right")
        self._restore_btn = self._ghost_button(bar, "Restaurar historial", self._restore_history)
        self._restore_btn.pack(side="right", padx=(0, 10))

    def _update_history_actions(self) -> None:
        # Disables what cannot be used now: nothing to undo, or nothing pending.
        running = self._engine.is_running
        has_history = self._ledger is not None and bool(self._ledger.recent(1))
        can_undo = not running and self._ledger is not None and self._ledger.last_undoable() is not None
        self._undo_btn.configure(state="normal" if can_undo else "disabled")
        self._restore_btn.configure(state="normal" if (not running and has_history) else "disabled")
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

    def _restore_history(self) -> None:
        if self._ledger is None:
            messagebox.showerror("Restaurar historial", "No se pudo abrir el historial.")
            return
        if self._engine.is_running:
            messagebox.showinfo("Restaurar historial", "Deten el monitor antes de restaurar.")
            return
        if not messagebox.askyesno("Restaurar historial", _RESTORE_CONFIRM, icon="warning"):
            return
        self._ledger.clear()
        self._reset_session_stats()
        self._refresh_history()
        messagebox.showinfo("Restaurar historial", "Historial vaciado. Los archivos siguen donde estaban.")

    def _reprocess_pending(self) -> None:
        def run() -> None:
            if not self._engine.is_running:
                self._engine.start()
            count = self._engine.reprocess_pending()
            logger.info("Reintentando %d archivos pendientes", count)

        _run_async(run)

    # --- Configuration view -------------------------------------------------

    def _build_config_view(self) -> None:
        self._config_view.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._config_view, text="Configuracion", font=self._f_h1, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._hint(self._config_view, "Lo esencial aca. El resto esta en Avanzado.").grid(
            row=1, column=0, sticky="w", pady=(0, 18)
        )
        self._build_main_folders_card()
        self._build_societies_card()
        self._build_suppliers_card()
        self._build_options_card()
        self._build_advanced_card()
        self._build_config_actions()

    def _card(self, title: str, subtitle: str, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._config_view, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 18))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=self._f_h2, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 8)
        )
        if subtitle:
            self._hint(card, subtitle).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        return body

    def _path_button(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=72,
            height=38,
            corner_radius=CORNER_RADIUS,
            fg_color=Palette.SURFACE_ALT,
            hover_color=Palette.BORDER,
            text_color=Palette.TEXT,
            border_width=1,
            border_color=Palette.BORDER,
            command=command,
        )

    def _folder_field(self, parent: tk.Misc, label: str, var: tk.StringVar, row: int, hint: str = "") -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(block, text=label, font=self._f_body, text_color=Palette.TEXT, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ctk.CTkEntry(block, textvariable=var, height=38).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._path_button(block, "Elegir", lambda: self._pick_folder(var)).grid(
            row=1, column=1, padx=(8, 0), pady=(4, 0)
        )
        self._path_button(block, "Abrir", lambda: open_folder(Path(var.get().strip() or "."))).grid(
            row=1, column=2, padx=(6, 0), pady=(4, 0)
        )
        if hint:
            self._hint(block, hint).grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))

    def _build_main_folders_card(self) -> None:
        body = self._card("Carpetas", "", row=2)
        self._folder_field(body, "Entrada", self._input_var, row=0)
        self._folder_field(body, "Salida", self._output_var, row=1)

    def _build_societies_card(self) -> None:
        body = self._card("Empresas", "Se archiva segun el CUIT de la compradora.", row=3)
        self._societies_list = ctk.CTkFrame(body, fg_color="transparent")
        self._societies_list.grid(row=0, column=0, sticky="ew")
        self._societies_list.grid_columnconfigure(0, weight=1)
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        buttons.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            buttons,
            text="+  Agregar empresa",
            height=40,
            corner_radius=CORNER_RADIUS,
            font=self._f_body,
            fg_color=Palette.PRIMARY,
            hover_color=Palette.PRIMARY_HOVER,
            text_color="#ffffff",
            command=self._add_society,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        import_button = self._path_button(buttons, "Importar Excel", self._import_societies)
        import_button.configure(height=40)
        import_button.grid(row=0, column=1, sticky="ew")

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
        subtitle = f"CUIT {_format_cuit(society.cuit)}"
        if society.nombre_fantasia:
            subtitle = f"{subtitle}   -   {society.nombre_fantasia}"
        ctk.CTkLabel(
            info,
            text=subtitle,
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

    def _checkbox(self, parent: tk.Misc, text: str, var: tk.BooleanVar, row: int) -> None:
        ctk.CTkCheckBox(parent, text=text, font=self._f_body, variable=var).grid(
            row=row, column=0, sticky="w", pady=(0, 8)
        )

    def _build_options_card(self) -> None:
        body = self._card("Comportamiento", "", row=5)
        self._checkbox(body, "Simular (no mueve archivos)", self._dry_run_var, row=0)
        self._checkbox(body, "Copiar en vez de mover", self._copy_var, row=1)
        self._checkbox(body, "Notificar cuando hay pendientes", self._notify_var, row=2)

    def _build_advanced_card(self) -> None:
        wrap = ctk.CTkFrame(self._config_view, fg_color="transparent")
        wrap.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        wrap.grid_columnconfigure(0, weight=1)
        self._advanced_open = False
        self._advanced_btn = self._ghost_button(wrap, "Avanzado  ▸", self._toggle_advanced)
        self._advanced_btn.grid(row=0, column=0, sticky="w")
        self._advanced_body = ctk.CTkFrame(wrap, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        self._advanced_body.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._advanced_body.grid_columnconfigure(0, weight=1)
        self._advanced_body.grid_remove()
        self._fill_advanced_body()

    def _fill_advanced_body(self) -> None:
        body = ctk.CTkFrame(self._advanced_body, fg_color="transparent")
        body.grid(row=0, column=0, sticky="ew", padx=20, pady=16)
        body.grid_columnconfigure(0, weight=1)
        self._checkbox(body, "Esperar a que termine la descarga", self._stability_var, row=0)
        timeout = ctk.CTkFrame(body, fg_color="transparent")
        timeout.grid(row=1, column=0, sticky="w", pady=(0, 12))
        ctk.CTkLabel(timeout, text="Espera maxima (segundos)", font=self._f_body, text_color=Palette.TEXT).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkEntry(timeout, textvariable=self._timeout_var, width=80, height=36).pack(side="left")
        self._template_field(body, row=2)
        self._folder_field(body, "Sin clasificar", self._unknown_var, row=3)
        self._folder_field(body, "Cuarentena", self._quarantine_var, row=4)
        self._folder_field(body, "Ordenes de compra", self._orders_var, row=5)
        logs = self._ghost_button(body, "Abrir carpeta de logs", self._open_logs)
        logs.grid(row=6, column=0, sticky="w", pady=(8, 0))

    def _template_field(self, parent: tk.Misc, row: int) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        block.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(block, text="Estructura de carpetas", font=self._f_body, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkEntry(block, textvariable=self._template_var, height=36).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._hint(block, "{supplier} {year} {month} {day}. Ej: {year}/{month}/{supplier}").grid(
            row=2, column=0, sticky="w", pady=(3, 0)
        )

    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self._advanced_body.grid()
            self._advanced_btn.configure(text="Avanzado  ▾")
            return
        self._advanced_body.grid_remove()
        self._advanced_btn.configure(text="Avanzado  ▸")

    def _build_config_actions(self) -> None:
        bar = ctk.CTkFrame(self._config_view, fg_color="transparent")
        bar.grid(row=7, column=0, sticky="ew", pady=(4, 24))
        bar.grid_columnconfigure(0, weight=1)
        self._primary_button(bar, "Guardar", self._save_config).grid(row=0, column=0, sticky="e")

    # --- Configuration loading and collection -------------------------------

    def _load_config_into_widgets(self) -> None:
        config = self._store.get()
        self._input_var.set(str(config.input_folder))
        self._output_var.set(str(config.base_output_folder))
        self._unknown_var.set(str(config.unknown_folder))
        self._quarantine_var.set(str(config.quarantine_folder))
        self._orders_var.set(str(config.orders_folder))
        self._dry_run_var.set(config.dry_run)
        self._stability_var.set(config.wait_for_stability)
        self._notify_var.set(config.notify)
        self._copy_var.set(config.copy_files)
        self._timeout_var.set(str(config.stability_timeout_s))
        self._template_var.set(config.destination_template)
        self._societies = list(config.societies)
        self._refresh_societies_list()

    def _collect_config(self) -> AppConfig | None:
        paths = (self._input_var, self._output_var, self._unknown_var, self._quarantine_var, self._orders_var)
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
            orders_folder=Path(self._orders_var.get().strip()),
            societies=tuple(self._societies),
            dry_run=self._dry_run_var.get(),
            wait_for_stability=self._stability_var.get(),
            stability_timeout_s=timeout,
            destination_template=self._template_var.get().strip() or "{supplier}",
            notify=self._notify_var.get(),
            copy_files=self._copy_var.get(),
        )

    # --- Society actions ----------------------------------------------------

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

    # --- Suppliers registry -------------------------------------------------

    def _build_suppliers_card(self) -> None:
        body = self._card("Proveedores", "Se importan por Excel y ordenan cada factura por emisor.", row=4)
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, textvariable=self._supplier_count_var, font=self._f_body, text_color=Palette.TEXT).grid(
            row=0, column=0, sticky="w"
        )
        self._path_button(header, "Importar Excel", self._import_suppliers).grid(row=0, column=1, padx=(6, 0))
        self._path_button(header, "Vaciar", self._clear_suppliers).grid(row=0, column=2, padx=(6, 0))
        search = ctk.CTkEntry(
            body, textvariable=self._supplier_search_var, height=38, placeholder_text="Buscar proveedor..."
        )
        search.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        search.bind("<KeyRelease>", lambda _event: self._refresh_suppliers())
        self._suppliers_list = ctk.CTkFrame(body, fg_color="transparent")
        self._suppliers_list.grid(row=2, column=0, sticky="ew")
        self._suppliers_list.grid_columnconfigure(0, weight=1)
        self._refresh_suppliers()

    def _refresh_suppliers(self) -> None:
        for child in self._suppliers_list.winfo_children():
            child.destroy()
        if self._registry_store is None or self._supplier_store is None:
            return
        self._supplier_count_var.set(f"{self._supplier_store.count()} proveedores")
        query = self._supplier_search_var.get().strip()
        results = self._registry_store.get().search(query, limit=_MAX_SUPPLIER_RESULTS)
        for index, supplier in enumerate(results):
            self._build_supplier_row(index, supplier)

    def _build_supplier_row(self, index: int, supplier: Supplier) -> None:
        row = ctk.CTkFrame(self._suppliers_list, fg_color=Palette.SURFACE_ALT, corner_radius=CORNER_RADIUS)
        row.grid(row=index, column=0, sticky="ew", pady=(0, 6))
        row.grid_columnconfigure(0, weight=1)
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkLabel(info, text=supplier.razon_social, font=self._f_body, text_color=Palette.TEXT, anchor="w").pack(
            anchor="w"
        )
        ctk.CTkLabel(
            info, text=f"CUIT {_format_cuit(supplier.cuit)}", font=self._f_hint, text_color=Palette.MUTED, anchor="w"
        ).pack(anchor="w")
        self._row_button(row, "Eliminar", Palette.ERROR, lambda: self._remove_supplier(supplier.cuit)).grid(
            row=0, column=1, sticky="e", padx=(0, 10)
        )

    def _remove_supplier(self, cuit: str) -> None:
        if self._supplier_store is None or self._registry_store is None:
            return
        self._supplier_store.delete(cuit)
        self._registry_store.reload()
        self._refresh_suppliers()

    def _import_suppliers(self) -> None:
        if self._supplier_store is None or self._registry_store is None:
            messagebox.showerror("Proveedores", "El registro de proveedores no esta disponible.")
            return
        rows = self._read_excel()
        if rows is None:
            return
        try:
            report = parse_suppliers(rows)
        except MissingColumnError as exc:
            messagebox.showerror("Excel invalido", str(exc))
            return
        created, updated = self._supplier_store.bulk_upsert(report.created)
        self._registry_store.reload()
        self._refresh_suppliers()
        summary = f"{created} nuevos, {updated} actualizados, {len(report.invalid)} con errores."
        ImportReportDialog(self, "Importar proveedores", summary, report.invalid)

    def _import_societies(self) -> None:
        rows = self._read_excel()
        if rows is None:
            return
        try:
            report = parse_societies(rows)
        except MissingColumnError as exc:
            messagebox.showerror("Excel invalido", str(exc))
            return
        merged = {society.cuit: society for society in self._societies}
        merged.update({society.cuit: society for society in report.created})
        self._societies = list(merged.values())
        self._refresh_societies_list()
        summary = f"{len(report.created)} empresas importadas, {len(report.invalid)} con errores. Recorda guardar."
        ImportReportDialog(self, "Importar empresas", summary, report.invalid)

    def _clear_suppliers(self) -> None:
        if self._supplier_store is None or self._registry_store is None:
            return
        if not messagebox.askyesno("Vaciar proveedores", "Se borra todo el registro de proveedores. Continuar?"):
            return
        self._supplier_store.clear()
        self._registry_store.reload()
        self._refresh_suppliers()

    def _read_excel(self) -> list[dict[str, str]] | None:
        path = filedialog.askopenfilename(title="Elegi el Excel", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return None
        try:
            return read_rows(Path(path))
        except ExcelReadError as exc:
            logger.exception("No se pudo leer el Excel %s", path)
            messagebox.showerror("Error al leer", f"No se pudo leer el Excel: {exc}")
            return None

    # --- Engine control -----------------------------------------------------

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
        # Undo depends on the monitor being stopped; reflect the change instantly.
        if hasattr(self, "_undo_btn"):
            self._update_history_actions()

    # --- Pickers and navigation ---------------------------------------------

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

    # --- Review pending (truth read from the folders) -----------------------

    def _poll_pending(self) -> None:
        # Always reschedules (finally) so a counting error does not stop the notifications.
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
        # Notifies only when new pendings appear and the user enabled it.
        if count > self._last_pending and self._store.get().notify:
            _run_async(lambda: notify("Automator", f"{count} factura(s) necesitan tu revision"))
        self._last_pending = count

    def _count_pending(self) -> int:
        # Only what the user still has to act on and what "Reintentar" reprocesses:
        # review and quarantine. Unclassified files are already archived, and that
        # folder grows without bound, so walking it every few seconds is wasteful.
        config = self._store.get()
        folders = (config.review_folder, config.quarantine_folder)
        return sum(_count_pdfs(folder) for folder in folders)

    # --- Engine event loop --------------------------------------------------

    def _poll_events(self) -> None:
        # The loop always reschedules (finally): a faulty event cannot leave the
        # UI unable to process further engine events.
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
            self._reset_session_stats()
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
            # Error with no associated file (failed startup or unreadable folder
            # while running): notify and reflect the real engine state.
            self._set_running(self._engine.is_running)
            messagebox.showerror("Automator", event.message)
            return
        self._increment("error")
        self._append_log(event.path.name, "", "Error", "error", event.message)

    def _on_result(self, result: ProcessResult) -> None:
        if result.outcome is ProcessOutcome.SKIPPED_MISSING:
            return
        self._increment(_count_key(result))
        voucher = result.invoice.voucher.label if result.invoice else ""
        destination = str(result.destination) if result.destination else result.message
        counted = result.counted_outcome
        self._append_log(result.source.name, voucher, _status_label(result), _OUTCOME_ROW_TAG[counted], destination)

    def _reset_session_stats(self) -> None:
        self._counts = dict.fromkeys(self._counts, 0)
        for var in self._stat_values.values():
            var.set("0")
        self._log.delete(*self._log.get_children())
        self._empty_state.grid(row=0, column=0, sticky="nsew")

    def _append_log(self, filename: str, voucher: str, status: str, tag: str, destination: str) -> None:
        self._empty_state.grid_remove()  # There is activity now: reveal the table.
        now = dt.datetime.now().strftime("%H:%M:%S")
        self._log.insert("", 0, values=(now, filename, voucher, status, destination), tags=(tag,))
        children = self._log.get_children()
        if len(children) > _MAX_LOG_ROWS:
            self._log.delete(children[-1])

    def _increment(self, key: str) -> None:
        self._counts[key] += 1
        self._stat_values[key].set(str(self._counts[key]))

    def on_close(self) -> None:
        # Stops synchronously so the worker finishes the current file before
        # closing: abandoning a move halfway could leave a corrupt PDF at the
        # destination. stop() already bounds the wait with a timeout.
        self._engine.stop()
        if self._ledger is not None:
            self._ledger.close()
        if self._supplier_store is not None:
            self._supplier_store.close()
        self.winfo_toplevel().destroy()


def _run_async(target: Callable[[], object]) -> None:
    threading.Thread(target=target, daemon=True).start()


def _count_key(result: ProcessResult) -> str:
    outcome = result.counted_outcome
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


def _status_label(result: ProcessResult) -> str:
    if result.outcome is ProcessOutcome.DRY_RUN and result.intended is not None:
        return f"Simulado · {_OUTCOME_LABELS[result.intended]}"
    return _OUTCOME_LABELS[result.outcome]


def _format_validation_error(exc: ValidationError) -> str:
    # Pydantic prefixes messages from our ValueError validators with "Value error, ";
    # drop it so the Spanish-only user does not see the English internal.
    return "\n".join(str(error["msg"]).removeprefix("Value error, ") for error in exc.errors())


def _format_cuit(cuit: str) -> str:
    # Shows the 11-digit CUIT as XX-XXXXXXXX-X; otherwise, as-is.
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
    # If the history cannot be opened, the app still works (no history/undo/dedup).
    try:
        return Ledger(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el historial; se continua sin el")
        return None


def _open_supplier_store() -> SupplierStore | None:
    # If the store cannot be opened, the app still works (no supplier canonicalization).
    try:
        return SupplierStore(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el registro de proveedores; se continua sin el")
        return None
