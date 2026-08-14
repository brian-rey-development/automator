"""Utilidades del sistema operativo independientes de la plataforma."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def open_folder(path: Path) -> None:
    """Abre una carpeta en el explorador de archivos del sistema."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]  # Solo existe en Windows.
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        logger.exception("No se pudo abrir la carpeta %s", path)
