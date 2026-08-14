"""Configuracion de la aplicacion: modelo validado, persistencia y store seguro."""

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
_MIN_STABILITY_TIMEOUT = 0.0
_MAX_STABILITY_TIMEOUT = 120.0
_TEMPLATE_TOKENS = {"supplier", "society", "year", "month", "day"}


def _is_within(child: Path, parent: Path) -> bool:
    """True si child es igual a parent o esta anidada dentro de parent."""
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
    """Asociacion entre el CUIT de una sociedad y su carpeta de proveedores."""

    model_config = ConfigDict(frozen=True)  # Inmutable: se puede compartir sin copiar.

    cuit: str
    name: str
    folder: Path

    @field_validator("cuit")
    @classmethod
    def _normalize_cuit(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) != _CUIT_LENGTH:
            raise ValueError(f"El CUIT debe tener {_CUIT_LENGTH} digitos: '{value}'")
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
        # Una carpeta vacia se resolveria a Path('.') (el directorio de trabajo) y
        # archivaria las facturas en un lugar impredecible: se exige ruta absoluta.
        if not str(value).strip() or not value.is_absolute():
            raise ValueError("La carpeta debe ser una ruta absoluta (elegila con 'Elegir').")
        return value


class AppConfig(BaseModel):
    """Configuracion completa de la aplicacion."""

    model_config = ConfigDict(frozen=True)  # Inmutable: snapshot compartible sin copiar.

    input_folder: Path
    base_output_folder: Path
    unknown_folder: Path
    quarantine_folder: Path
    societies: tuple[SocietyMapping, ...] = Field(default_factory=tuple)
    dry_run: bool = False
    wait_for_stability: bool = True
    stability_timeout_s: float = Field(default=10.0, ge=_MIN_STABILITY_TIMEOUT, le=_MAX_STABILITY_TIMEOUT)
    # Plantilla de subcarpetas dentro de la carpeta de cada sociedad. Tokens validos:
    # {supplier} {society} {year} {month} {day}. Por defecto solo por proveedor.
    destination_template: str = "{supplier}"
    notify: bool = True  # Avisos del sistema cuando algo necesita atencion.

    @model_validator(mode="after")
    def _reject_duplicate_cuits(self) -> AppConfig:
        cuits = [society.cuit for society in self.societies]
        duplicates = {cuit for cuit in cuits if cuits.count(cuit) > 1}
        if duplicates:
            raise ValueError(f"Hay CUIT repetidos entre las sociedades: {', '.join(sorted(duplicates))}")
        return self

    @model_validator(mode="after")
    def _reject_output_inside_input(self) -> AppConfig:
        # Una carpeta de salida dentro de la de entrada haria que el watcher detecte
        # los archivos recien archivados y los reprocese en un bucle infinito.
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
        """Carpeta para facturas con datos incompletos que requieren revision manual."""
        return self.base_output_folder / "_PARA_REVISAR"

    @property
    def duplicates_folder(self) -> Path:
        """Carpeta para facturas ya archivadas antes (detectadas por identidad)."""
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
        # La carpeta de entrada es critica: sin ella no hay nada que monitorear, asi
        # que su error se propaga. Las de salida se crean al vuelo al mover; si una
        # (por ejemplo un disco de red) no esta disponible ahora, no bloquea el arranque.
        self.input_folder.mkdir(parents=True, exist_ok=True)
        for folder in self.all_folders():
            if folder == self.input_folder:
                continue
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.warning("No se pudo crear la carpeta %s ahora; se creara al archivar", folder)


def default_config() -> AppConfig:
    """Configuracion inicial neutra, sin ninguna empresa precargada.

    No se codifica ningun dato real: el usuario define sus sociedades y CUITs
    desde la interfaz (o el asistente de primera vez). Arranca sin sociedades.
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
    """Carga la configuracion; ante ausencia, corrupcion o error de lectura degrada a default.

    Se distinguen dos casos para no destruir una config valida por un problema
    transitorio: un error de lectura (bloqueo, permisos, disco de red) NO toca el
    archivo; solo el contenido genuinamente invalido se respalda para diagnostico.
    """
    target = path or config_path()
    if not target.exists():
        return default_config()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        # Error transitorio: se preserva el archivo del usuario para el proximo arranque.
        logger.warning("No se pudo leer la config en %s; se usa la default sin tocar el archivo (%s)", target, exc)
        return default_config()
    try:
        return AppConfig.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        # Contenido invalido (archivo viejo o dañado): se respalda y se usa la default.
        logger.warning("Config invalida en %s; se respalda y se usa la configuracion por defecto (%s)", target, exc)
        _backup_corrupt_config(target)
        return default_config()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Guarda la configuracion de forma atomica (escribe a temporal y reemplaza)."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)  # Rename atomico: nunca deja el archivo a medio escribir.


def _backup_corrupt_config(target: Path) -> None:
    # Nombre con timestamp: nunca pisa un respaldo previo (podria contener la ultima config buena).
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(f"{target.name}.{stamp}.corrupt")
    try:
        os.replace(target, backup)
    except OSError:
        logger.exception("No se pudo respaldar la configuracion corrupta %s", target)


class ConfigStore:
    """Contenedor thread-safe de la configuracion viva de la aplicacion.

    AppConfig es inmutable (frozen), asi que el worker en segundo plano puede leer
    el snapshot directamente, sin copias defensivas, mientras la interfaz lo cambia
    de forma atomica (se reemplaza la referencia, nunca se muta en el lugar).
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
        """Persiste primero y solo entonces compromete en memoria.

        Si el guardado falla, ni el disco ni la memoria cambian: la app no queda
        con una config viva distinta de la del archivo.
        """
        with self._lock:
            save_config(config, self._path)
            self._config = config


def load_store(path: Path | None = None) -> ConfigStore:
    target = path or config_path()
    store = ConfigStore(load_config(target), target)
    if not target.exists():
        # Persiste la config por defecto (primer arranque o tras respaldar una corrupta).
        store.save()
    return store
