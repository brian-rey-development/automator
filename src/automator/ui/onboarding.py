"""First-time wizard: guided setup for someone without experience."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from pydantic import ValidationError

from automator.config import AppConfig, SocietyMapping
from automator.ui.theme import CORNER_RADIUS, Palette

_UNKNOWN_SUBFOLDER = "_FACTURAS_SIN_CLASIFICAR"
_QUARANTINE_SUBFOLDER = "_ERRORES"


class OnboardingDialog(ctk.CTkToplevel):
    """Asks for the minimum (input, output and one company) and returns an AppConfig."""

    def __init__(self, master: tk.Misc, base: AppConfig) -> None:
        super().__init__(master)
        self.result: AppConfig | None = None
        self._input = tk.StringVar(value=str(base.input_folder))
        self._output = tk.StringVar(value=str(base.base_output_folder))
        self._cuit = tk.StringVar()
        self._name = tk.StringVar()

        self.title("Bienvenido a Automator")
        self.configure(fg_color=Palette.BG)
        self.resizable(False, False)
        self._build()
        self._make_modal(master)

    def _build(self) -> None:
        card = ctk.CTkFrame(self, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        card.pack(fill="both", expand=True, padx=20, pady=20)
        card.columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="Configuremos lo basico", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(20, 2)
        )
        ctk.CTkLabel(
            card,
            text="Elegi de donde se leen los PDF y donde se guardan ordenados. La empresa es opcional.",
            text_color=Palette.MUTED,
            wraplength=460,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))
        self._folder_row(card, "Carpeta de entrada (tus descargas)", self._input, row=2)
        self._folder_row(card, "Carpeta de salida (facturas ordenadas)", self._output, row=3)
        ctk.CTkLabel(card, text="Primera empresa (opcional)", text_color=Palette.TEXT).grid(
            row=4, column=0, sticky="w", padx=20, pady=(10, 2)
        )
        self._entry_row(card, "CUIT", self._cuit, row=5)
        self._entry_row(card, "Razon social", self._name, row=6)
        self._error = ctk.CTkLabel(card, text="", text_color=Palette.ERROR, wraplength=460, justify="left")
        self._error.grid(row=7, column=0, sticky="w", padx=20, pady=(6, 0))
        self._buttons(card, row=8)

    def _entry_row(self, parent: ctk.CTkFrame, label: str, var: tk.StringVar, row: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=4)
        frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, text_color=Palette.MUTED, width=140, anchor="w").grid(
            row=0, column=1, padx=(8, 0)
        )
        ctk.CTkEntry(frame, textvariable=var).grid(row=0, column=0, sticky="ew")

    def _folder_row(self, parent: ctk.CTkFrame, label: str, var: tk.StringVar, row: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=4)
        frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, text_color=Palette.TEXT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ctk.CTkEntry(frame, textvariable=var).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkButton(frame, text="Elegir", width=80, command=lambda: self._pick(var)).grid(
            row=1, column=1, padx=(8, 0), pady=(4, 0)
        )

    def _buttons(self, parent: ctk.CTkFrame, row: int) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="e", padx=20, pady=16)
        ctk.CTkButton(
            bar, text="Lo hago despues", fg_color=Palette.MUTED, hover_color=Palette.TEXT, command=self.destroy
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            bar, text="Empezar", fg_color=Palette.PRIMARY, hover_color=Palette.PRIMARY_HOVER, command=self._finish
        ).pack(side="left")

    def _pick(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Elegi una carpeta")
        if chosen:
            var.set(chosen)

    def _finish(self) -> None:
        try:
            self.result = self._build_config()
        except ValidationError as exc:
            self._error.configure(text=exc.errors()[0]["msg"])
            return
        self.destroy()

    def _build_config(self) -> AppConfig:
        base = Path(self._output.get().strip())
        return AppConfig(
            input_folder=Path(self._input.get().strip()),
            base_output_folder=base,
            unknown_folder=base / _UNKNOWN_SUBFOLDER,
            quarantine_folder=base / _QUARANTINE_SUBFOLDER,
            societies=self._collect_society(),
        )

    def _collect_society(self) -> tuple[SocietyMapping, ...]:
        cuit, name = self._cuit.get().strip(), self._name.get().strip()
        if not cuit and not name:
            return ()
        return (SocietyMapping(cuit=cuit, name=name),)

    def _make_modal(self, master: tk.Misc) -> None:
        self.transient(master.winfo_toplevel())
        self.wait_visibility()
        self.grab_set()
        self.focus_set()
