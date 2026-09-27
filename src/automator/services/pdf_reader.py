"""Text and AFIP QR extraction from PDF files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import zxingcpp
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# The QR sits on the first page; a duplicate copy may repeat it. Long documents are
# not vouchers, so scanning stops early to keep large PDFs cheap.
_MAX_QR_PAGES = 3
_QR_ONLY = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)
_MIN_QR_SIDE_PX = 21  # A version-1 QR is 21 modules wide; anything smaller is a logo dot.


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


def read_qr_payloads(path: Path) -> tuple[str, ...]:
    """Text of every QR found in the PDF's embedded images. Never raises.

    A missing QR is normal (older or non-fiscal documents), so any failure yields an
    empty result and the caller falls back to the printed text.
    """
    try:
        with path.open("rb") as stream:
            pages = PdfReader(stream).pages[:_MAX_QR_PAGES]
            return tuple(payload for page in pages for payload in _page_qr_payloads(page))
    except Exception:
        logger.debug("No se pudieron leer imagenes de %s", path, exc_info=True)
        return ()


def _page_qr_payloads(page: Any) -> list[str]:
    payloads: list[str] = []
    for embedded in page.images:
        try:
            image = embedded.image
            if image is None or min(image.size) < _MIN_QR_SIDE_PX:
                continue
            found = zxingcpp.read_barcodes(image.convert("L"), formats=_QR_ONLY)
            payloads.extend(barcode.text for barcode in found)
        except Exception:  # one undecodable image must not hide the others
            logger.debug("Imagen ilegible en la pagina; se continua", exc_info=True)
    return payloads
