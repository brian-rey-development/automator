"""Configuracion centralizada de logging con rotacion de archivos."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from automator.config import log_dir

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_FILENAME = "automator.log"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 5


def log_location() -> Path:
    """Ruta del archivo de log principal (para mostrarla al usuario ante un fallo)."""
    return log_dir() / _LOG_FILENAME


def setup_logging(level: int = logging.INFO) -> None:
    """Configura logging a consola y a un archivo rotativo en la carpeta de logs."""
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_LOG_FORMAT)

    file_handler = RotatingFileHandler(
        directory / _LOG_FILENAME,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
