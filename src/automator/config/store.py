"""Atomic persistence and the thread-safe live configuration store."""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
import threading
from pathlib import Path

from pydantic import ValidationError

from automator.config.defaults import default_config
from automator.config.model import AppConfig
from automator.paths import config_path

logger = logging.getLogger(__name__)


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
        logger.warning("No se pudo leer la config en %s; se usa la default sin tocar el archivo (%s)", target, exc)
        return default_config()
    try:
        return AppConfig.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        logger.warning("Config invalida en %s; se respalda y se usa la configuracion por defecto (%s)", target, exc)
        _backup_corrupt_config(target)
        return default_config()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Save the configuration atomically and durably.

    The temp file is flushed and fsynced before the rename so a power loss right
    after cannot expose an empty or half-written config; os.replace is the atomic
    swap and the parent directory is synced so the rename itself survives a crash.
    """
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(config.model_dump_json(indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    _fsync_dir(target.parent)


def _fsync_dir(directory: Path) -> None:
    if sys.platform.startswith("win"):
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _backup_corrupt_config(target: Path) -> None:
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
        with self._lock:
            save_config(config, self._path)
            self._config = config  # Disk first: a failed save must not change memory.


def load_store(path: Path | None = None) -> ConfigStore:
    target = path or config_path()
    store = ConfigStore(load_config(target), target)
    if not target.exists():
        store.save()
    return store
