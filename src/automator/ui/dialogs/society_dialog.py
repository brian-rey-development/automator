"""Modern modal dialog to create or edit a society (buying company)."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from pydantic import ValidationError

from automator.config import SocietyMapping
from automator.domain.validation import first_validation_error
from automator.ui.theme import CORNER_RADIUS, Palette
from automator.ui.widgets import make_modal, muted_button, primary_button

_ALIAS_SEPARATOR = ","


class SocietyDialog(ctk.CTkToplevel):
    """Dialog that returns a validated SocietyMapping or None if cancelled."""

    def __init__(self, master: tk.Misc, existing: SocietyMapping | None = None) -> None:
        super().__init__(master)
        self.result: SocietyMapping | None = None
        self._cuit = tk.StringVar(value=existing.cuit if existing else "")
        self._name = tk.StringVar(value=existing.name if existing else "")
        self._trade_name = tk.StringVar(value=existing.trade_name if existing and existing.trade_name else "")
        self._aliases = tk.StringVar(value=_ALIAS_SEPARATOR.join(existing.aliases) if existing else "")

        self.title("Editar empresa" if existing else "Nueva empresa")
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
        self._field(container, "Nombre de fantasia (opcional)", self._trade_name, row=2)
        self._field(container, "Alias, separados por coma (opcional)", self._aliases, row=3)
        self._error = ctk.CTkLabel(container, text="", text_color=Palette.ERROR, anchor="w")
        self._error.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 0))
        self._buttons(container, row=5)

    def _field(self, parent: ctk.CTkFrame, label: str, var: tk.StringVar, row: int) -> None:
        ctk.CTkLabel(parent, text=label, text_color=Palette.MUTED).grid(
            row=row, column=0, sticky="w", padx=16, pady=(16 if row == 0 else 8, 0)
        )
        ctk.CTkEntry(parent, textvariable=var, width=320).grid(
            row=row, column=1, sticky="ew", padx=16, pady=(16 if row == 0 else 8, 0)
        )

    def _buttons(self, parent: ctk.CTkFrame, row: int) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=row, column=0, columnspan=2, sticky="e", padx=16, pady=16)
        muted_button(bar, "Cancelar", self.destroy, width=100).pack(side="left", padx=(0, 8))
        primary_button(bar, "Guardar", self._save, width=120).pack(side="left")

    def _save(self) -> None:
        try:
            self.result = SocietyMapping(
                cuit=self._cuit.get().strip(),
                name=self._name.get().strip(),
                trade_name=self._trade_name.get().strip() or None,
                aliases=_parse_aliases(self._aliases.get()),
            )
        except ValidationError as exc:
            self._error.configure(text=first_validation_error(exc))
            return
        self.destroy()

    def _make_modal(self, master: tk.Misc) -> None:
        make_modal(self, master, on_return=self._save, on_escape=self.destroy)


def _parse_aliases(raw: str) -> tuple[str, ...]:
    return tuple(alias.strip() for alias in raw.split(_ALIAS_SEPARATOR) if alias.strip())
