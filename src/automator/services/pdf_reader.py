"""Text extraction from PDF files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text(path: Path) -> str:
    """Returns all extractable text from the PDF, concatenating its pages.

    Layout mode preserves the on-page column order, which is what makes the invoice
    number readable in templates that otherwise extract one glyph per line. When layout
    yields nothing (some PDFs do not support it), plain extraction is used as a fallback.

    Opened with `with` to close the file deterministically: on Windows, an open handle
    would make the later move of the PDF fail (WinError 32).
    """
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        layout = "\n".join(_page_text(page, "layout") for page in reader.pages)
        if layout.strip():
            return layout
        return "\n".join(_page_text(page, "plain") for page in reader.pages)


def _page_text(page: Any, mode: str) -> str:
    # A corrupt page (or one that does not support layout mode) must not discard the
    # text of the others; on its failure we continue. If key data is missing as a
    # result, the parser will flag it for review.
    try:
        if mode == "layout":
            return page.extract_text(extraction_mode="layout") or ""
        return page.extract_text() or ""
    except Exception:  # noqa: BLE001 -- deliberate resilience: one broken page does not discard the rest
        logger.warning("No se pudo extraer texto de una pagina; se continua con el resto")
        return ""
