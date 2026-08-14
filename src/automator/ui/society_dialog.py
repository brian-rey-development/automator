"""Modern modal dialog to create or edit a society."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from pydantic import ValidationError

from automator.config import SocietyMapping
from automator.ui.theme import CORNER_RADIUS, Palette


class SocietyDialog(ctk.CTkToplevel):
    """Dialog that returns a validated SocietyMapping or None if cancelled."""

    def __init__(self, master: tk.Misc, existing: SocietyMapping | None = None) -> None:
        super().__init__(master)
        self.result: SocietyMapping | None = None
        self._cuit = tk.StringVar(value=existing.cuit if existing else "")
        self._name = tk.StringVar(value=existing.name if existing else "")
        self._folder = tk.StringVar(value=str(existing.folder) if existing else "")

        self.title("Editar sociedad" if existing else "Nueva sociedad")
        self.configure(fg_color=Palette.BG)
        self.resizable(False, False)
        self._build_form()
        self._make_modal(master)

    def _build_form(self) -> None:
        container = ctk.CTkFrame(self, fg_color=Palette.SURFACE, corner_radius=CORNER_RADIUS)
        container.pack(fill="both", expand=True, padx=20, pady=20)
        container.columnconfigure(1, weight=1)

        self._field(container, "CUIT (11 digitos)", self._cuit, row=0)
        self._field(container, "Razon social", self._name, row=1)
        self._folder_field(container, row=2)
        self._error = ctk.CTkLabel(container, text="", text_color=Palette.ERROR, anchor="w")
        self._error.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(4, 0))
        self._buttons(container, row=4)

    def _field(self, parent: ctk.CTkFrame, label: str, var: tk.StringVar, row: int) -> None:
        ctk.CTkLabel(parent, text=label, text_color=Palette.MUTED).grid(
            row=row, column=0, sticky="w", padx=16, pady=(16 if row == 0 else 8, 0)
        )
        ctk.CTkEntry(parent, textvariable=var, width=320).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=16, pady=(16 if row == 0 else 8, 0)
        )

    def _folder_field(self, parent: ctk.CTkFrame, row: int) -> None:
        ctk.CTkLabel(parent, text="Carpeta de proveedores", text_color=Palette.MUTED).grid(
            row=row, column=0, sticky="w", padx=16, pady=(8, 0)
        )
        ctk.CTkEntry(parent, textvariable=self._folder).grid(row=row, column=1, sticky="ew", padx=(16, 8), pady=(8, 0))
        ctk.CTkButton(parent, text="Elegir", width=80, command=self._pick_folder).grid(
            row=row, column=2, padx=(0, 16), pady=(8, 0)
        )

    def _buttons(self, parent: ctk.CTkFrame, row: int) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=row, column=0, columnspan=3, sticky="e", padx=16, pady=16)
        ctk.CTkButton(
            bar, text="Cancelar", width=100, fg_color=Palette.MUTED, hover_color=Palette.TEXT, command=self.destroy
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            bar,
            text="Guardar",
            width=120,
            fg_color=Palette.PRIMARY,
            hover_color=Palette.PRIMARY_HOVER,
            command=self._save,
        ).pack(side="left")

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Carpeta de proveedores")
        if chosen:
            self._folder.set(chosen)

    def _save(self) -> None:
        try:
            self.result = SocietyMapping(
                cuit=self._cuit.get().strip(),
                name=self._name.get().strip(),
                folder=self._folder.get().strip(),
            )
        except ValidationError as exc:
            self._error.configure(text=_first_error(exc))
            return
        self.destroy()

    def _make_modal(self, master: tk.Misc) -> None:
        self.transient(master.winfo_toplevel())
        # grab_set fails if the window is not yet visible: wait until it is.
        self.wait_visibility()
        self.grab_set()
        self.focus_set()


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    field = error["loc"][0] if error["loc"] else ""
    return f"{field}: {error['msg']}"
