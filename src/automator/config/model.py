"""Frozen configuration model: companies, folders and routing helpers."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from automator.config.defaults import (
    DUPLICATES_FOLDER_NAME,
    ORDERS_UNKNOWN_FOLDER_NAME,
    REVIEW_FOLDER_NAME,
    default_orders_folder,
)
from automator.domain.cuit import Cuit
from automator.domain.filenames import sanitize_component
from automator.domain.names import LegalName

_MIN_STABILITY_TIMEOUT = 0.0
_MAX_STABILITY_TIMEOUT = 120.0
_TEMPLATE_TOKENS = {"supplier", "society", "year", "month", "day"}


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


class SocietyMapping(BaseModel):
    """A buying company: its CUIT, legal name and optional trade name/aliases.

    The destination folder is not stored: it is derived from the output base and
    the legal name (base/{Razon Social}), so every company files under one root.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    cuit: Cuit
    name: LegalName
    trade_name: str | None = Field(default=None, validation_alias=AliasChoices("trade_name", "nombre_fantasia"))
    aliases: tuple[str, ...] = ()

    def match_names(self) -> tuple[str, ...]:
        extra = (self.trade_name,) if self.trade_name else ()
        return (self.name, *extra, *self.aliases)


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_folder: Path
    base_output_folder: Path
    unknown_folder: Path
    quarantine_folder: Path
    societies: tuple[SocietyMapping, ...] = Field(default_factory=tuple)
    dry_run: bool = False
    wait_for_stability: bool = True
    stability_timeout_s: float = Field(default=10.0, ge=_MIN_STABILITY_TIMEOUT, le=_MAX_STABILITY_TIMEOUT)
    destination_template: str = "{supplier}"
    notify: bool = True
    copy_files: bool = False
    orders_folder: Path = Field(default_factory=default_orders_folder)

    @model_validator(mode="after")
    def _reject_duplicate_cuits(self) -> AppConfig:
        cuits = [society.cuit for society in self.societies]
        duplicates = {cuit for cuit in cuits if cuits.count(cuit) > 1}
        if duplicates:
            raise ValueError(f"Hay CUIT repetidos entre las sociedades: {', '.join(sorted(duplicates))}")
        return self

    @model_validator(mode="after")
    def _reject_output_inside_input(self) -> AppConfig:
        outputs = [self.base_output_folder, self.unknown_folder, self.quarantine_folder, self.orders_folder]
        outputs.extend(self.society_folder(society) for society in self.societies)
        if any(_is_within(folder, self.input_folder) for folder in outputs):
            raise ValueError("Las carpetas de salida no pueden estar dentro de la carpeta de entrada.")
        return self

    @field_validator("destination_template")
    @classmethod
    def _validate_template(cls, value: str) -> str:
        tokens = set(re.findall(r"\{(\w+)\}", value))
        unknown = tokens - _TEMPLATE_TOKENS
        if unknown:
            raise ValueError(f"La plantilla usa tokens invalidos: {', '.join(sorted(unknown))}")
        return value

    @property
    def review_folder(self) -> Path:
        """Folder for invoices with incomplete data that require manual review."""
        return self.base_output_folder / REVIEW_FOLDER_NAME

    @property
    def duplicates_folder(self) -> Path:
        """Folder for invoices already archived before (detected by identity)."""
        return self.base_output_folder / DUPLICATES_FOLDER_NAME

    def known_cuits(self) -> list[str]:
        return [society.cuit for society in self.societies]

    def society_for_cuit(self, cuit: str | None) -> SocietyMapping | None:
        if cuit is None:
            return None
        return next((society for society in self.societies if society.cuit == cuit), None)

    def society_folder(self, society: SocietyMapping) -> Path:
        """Each company files under a standardized folder: base/{Razon Social}."""
        return self.base_output_folder / sanitize_component(society.name)

    def folder_for_cuit(self, cuit: str | None) -> Path:
        society = self.society_for_cuit(cuit)
        return self.society_folder(society) if society is not None else self.unknown_folder

    def orders_base_for(self, cuit: str | None) -> Path:
        society = self.society_for_cuit(cuit)
        name = society.name if society is not None else ORDERS_UNKNOWN_FOLDER_NAME
        return self.orders_folder / sanitize_component(name)

    def all_folders(self) -> list[Path]:
        folders = [
            self.input_folder,
            self.base_output_folder,
            self.unknown_folder,
            self.quarantine_folder,
            self.review_folder,
            self.duplicates_folder,
            self.orders_folder,
        ]
        folders.extend(self.society_folder(society) for society in self.societies)
        return folders


ConfigProvider = Callable[[], AppConfig]
