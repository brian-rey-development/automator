"""Lectura de texto desde archivos PDF."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text(path: Path) -> str:
    """Devuelve todo el texto extraible del PDF, concatenando sus paginas.

    Se abre con `with` para cerrar el archivo de forma deterministica: en Windows,
    un handle abierto haria fallar el posterior movimiento del PDF (WinError 32).
    """
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        return "\n".join(_page_text(page) for page in reader.pages)


def _page_text(page: Any) -> str:
    # Una pagina corrupta no debe descartar el texto de las demas; ante su fallo se
    # continua. Si con eso faltan datos clave, el parser lo marcara para revision.
    try:
        return page.extract_text() or ""
    except Exception:  # noqa: BLE001 -- resiliencia deliberada: una pagina rota no descarta el resto
        logger.warning("No se pudo extraer texto de una pagina; se continua con el resto")
        return ""
