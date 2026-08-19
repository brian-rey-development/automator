"""Create configured folders. Input must exist; other folders are best-effort."""

from __future__ import annotations

import logging

from automator.config.model import AppConfig

logger = logging.getLogger(__name__)


def ensure_folders(config: AppConfig) -> None:
    config.input_folder.mkdir(parents=True, exist_ok=True)
    for folder in config.all_folders():
        if folder == config.input_folder:
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("No se pudo crear la carpeta %s ahora; se creara al archivar", folder)
