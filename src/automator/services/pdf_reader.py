"""Text extraction from PDF files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text(path: Path) -> str:
    """Returns all extractable text from the PDF, concatenating its pages.

    Opened with `with` to close the file deterministically: on Windows, an open
    handle would make the later move of the PDF fail (WinError 32).
    """
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        return "\n".join(_page_text(page) for page in reader.pages)


def _page_text(page: Any) -> str:
    # A corrupt page must not discard the text of the others; on its failure we
    # continue. If key data is missing as a result, the parser will flag it for review.
    try:
        return page.extract_text() or ""
    except Exception:  # noqa: BLE001 -- deliberate resilience: one broken page does not discard the rest
        logger.warning("No se pudo extraer texto de una pagina; se continua con el resto")
        return ""
