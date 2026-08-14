"""Application configuration: validated model, persistence and a safe store."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import threading
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_downloads_dir, user_log_dir
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

APP_NAME = "Automator"
APP_AUTHOR = "Brian Rey"

_CUIT_LENGTH = 11
_CUIT_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_MIN_STABILITY_TIMEOUT = 0.0
_MAX_STABILITY_TIMEOUT = 120.0
_TEMPLATE_TOKENS = {"supplier", "society", "year", "month", "day"}


def _is_valid_cuit(digits: str) -> bool:
    """Validate the CUIT check digit (AFIP modulo 11 algorithm)."""
    total = sum(int(digit) * weight for digit, weight in zip(digits[:10], _CUIT_WEIGHTS, strict=True))
    expected = 11 - (total % 11)
    expected = 0 if expected == 11 else expected
    return expected != 10 and expected == int(digits[10])


def _is_within(child: Path, parent: Path) -> bool:
    """True if child equals parent or is nested inside parent."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def config_path() -> Path:
    return Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "config.json"


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def ledger_path() -> Path:
    return data_dir() / "history.db"


def log_dir() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


class SocietyMapping(BaseModel):
    """Association between a company's CUIT and its suppliers folder."""

    model_config = ConfigDict(frozen=True)  # Immutable: can be shared without copying.

    cuit: str
    name: str
    folder: Path

    @field_validator("cuit")
    @classmethod
    def _normalize_cuit(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) != _CUIT_LENGTH:
            raise ValueError(f"El CUIT debe tener {_CUIT_LENGTH} digitos: '{value}'")
        if not _is_valid_cuit(digits):
            raise ValueError(f"El CUIT no es valido (digito verificador incorrecto): '{value}'")
        return digits

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La razon social no puede estar vacia.")
        return value.strip()

    @field_validator("folder")
    @classmethod
    def _folder_must_be_absolute(cls, value: Path) -> Path:
        # An empty folder would resolve to Path('.') (the working directory) and
        # would archive invoices in an unpredictable place: an absolute path is required.
        if not str(value).strip() or not value.is_absolute():
            raise ValueError("La carpeta debe ser una ruta absoluta (elegila con 'Elegir').")
        return value


class AppConfig(BaseModel):
    """Full application configuration."""

    model_config = ConfigDict(frozen=True)  # Immutable: shareable snapshot without copying.

    input_folder: Path
    base_output_folder: Path
    unknown_folder: Path
    quarantine_folder: Path
    societies: tuple[SocietyMapping, ...] = Field(default_factory=tuple)
    dry_run: bool = False
    wait_for_stability: bool = True
    stability_timeout_s: float = Field(default=10.0, ge=_MIN_STABILITY_TIMEOUT, le=_MAX_STABILITY_TIMEOUT)
    # Subfolder template inside each company's folder. Valid tokens:
    # {supplier} {society} {year} {month} {day}. By default only by supplier.
    destination_template: str = "{supplier}"
    notify: bool = True  # System notifications when something needs attention.
    # Copy instead of move: leaves the original in the input folder. The engine
    # remembers each already-processed file (in the ledger) so it is not reprocessed.
    copy_files: bool = False

    @model_validator(mode="after")
    def _reject_duplicate_cuits(self) -> AppConfig:
        cuits = [society.cuit for society in self.societies]
        duplicates = {cuit for cuit in cuits if cuits.count(cuit) > 1}
        if duplicates:
            raise ValueError(f"Hay CUIT repetidos entre las sociedades: {', '.join(sorted(duplicates))}")
        return self

    @model_validator(mode="after")
    def _reject_output_inside_input(self) -> AppConfig:
        # An output folder inside the input one would make the watcher detect
        # the just-archived files and reprocess them in an infinite loop.
        outputs = [self.base_output_folder, self.unknown_folder, self.quarantine_folder]
        outputs.extend(society.folder for society in self.societies)
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
        return self.base_output_folder / "_PARA_REVISAR"

    @property
    def duplicates_folder(self) -> Path:
        """Folder for invoices already archived before (detected by identity)."""
        return self.base_output_folder / "_DUPLICADOS"

    def known_cuits(self) -> list[str]:
        return [society.cuit for society in self.societies]

    def society_names(self) -> set[str]:
        return {society.name.casefold() for society in self.societies}

    def folder_for_cuit(self, cuit: str | None) -> Path:
        if cuit is not None:
            for society in self.societies:
                if society.cuit == cuit:
                    return society.folder
        return self.unknown_folder

    def all_folders(self) -> list[Path]:
        folders = [
            self.input_folder,
            self.base_output_folder,
            self.unknown_folder,
            self.quarantine_folder,
            self.review_folder,
            self.duplicates_folder,
        ]
        folders.extend(society.folder for society in self.societies)
        return folders

    def ensure_folders(self) -> None:
        # The input folder is critical: without it there is nothing to monitor, so
        # its error propagates. Output folders are created on the fly when moving; if one
        # (for example a network drive) is not available now, it does not block startup.
        self.input_folder.mkdir(parents=True, exist_ok=True)
        for folder in self.all_folders():
            if folder == self.input_folder:
                continue
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.warning("No se pudo crear la carpeta %s ahora; se creara al archivar", folder)


def default_config() -> AppConfig:
    """Neutral initial configuration, with no company preloaded.

    No real data is hardcoded: the user defines their companies and CUITs
    from the interface (or the first-time wizard). It starts with no companies.
    """
    home = Path.home()
    base = home / "Automator" / "Facturas ordenadas"
    return AppConfig(
        input_folder=Path(user_downloads_dir()),
        base_output_folder=base,
        unknown_folder=base / "_SIN_CLASIFICAR",
        quarantine_folder=base / "_ERRORES",
    )


def load_config(path: Path | None = None) -> AppConfig:
    """Load the configuration; on absence, corruption or read error it degrades to the default.

    Two cases are distinguished so a valid config is not destroyed by a transient
    problem: a read error (lock, permissions, network drive) does NOT touch the
    file; only genuinely invalid content is backed up for diagnostics.
    """
    target = path or config_path()
    if not target.exists():
        return default_config()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        # Transient error: the user's file is preserved for the next startup.
        logger.warning("No se pudo leer la config en %s; se usa la default sin tocar el archivo (%s)", target, exc)
        return default_config()
    try:
        return AppConfig.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        # Invalid content (old or damaged file): it is backed up and the default is used.
        logger.warning("Config invalida en %s; se respalda y se usa la configuracion por defecto (%s)", target, exc)
        _backup_corrupt_config(target)
        return default_config()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Save the configuration atomically (write to a temp file and replace)."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)  # Atomic rename: never leaves the file half-written.


def _backup_corrupt_config(target: Path) -> None:
    # Timestamped name: never overwrites a previous backup (it could hold the last good config).
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(f"{target.name}.{stamp}.corrupt")
    try:
        os.replace(target, backup)
    except OSError:
        logger.exception("No se pudo respaldar la configuracion corrupta %s", target)


class ConfigStore:
    """Thread-safe container for the application's live configuration.

    AppConfig is immutable (frozen), so the background worker can read the
    snapshot directly, without defensive copies, while the interface changes it
    atomically (the reference is replaced, never mutated in place).
    """

    def __init__(self, config: AppConfig, path: Path | None = None) -> None:
        self._config = config
        self._path = path or config_path()
        self._lock = threading.Lock()

    def get(self) -> AppConfig:
        with self._lock:
            return self._config

    def set(self, config: AppConfig) -> None:
        with self._lock:
            self._config = config

    def save(self) -> None:
        with self._lock:
            save_config(self._config, self._path)

    def update(self, config: AppConfig) -> None:
        """Persist first and only then commit in memory.

        If the save fails, neither disk nor memory changes: the app is not left
        with a live config different from the one in the file.
        """
        with self._lock:
            save_config(config, self._path)
            self._config = config


def load_store(path: Path | None = None) -> ConfigStore:
    target = path or config_path()
    store = ConfigStore(load_config(target), target)
    if not target.exists():
        # Persist the default config (first startup or after backing up a corrupt one).
        store.save()
    return store
