"""Building and sanitizing file/folder names for Windows."""

from __future__ import annotations

import re

from automator.domain.models import ParsedInvoice

# Characters forbidden in Windows file names.
_INVALID_CHARS = re.compile(r'[\\/*?:"<>|\r\n\t]')
_WHITESPACE = re.compile(r"\s+")
_MAX_COMPONENT_LENGTH = 150
_FALLBACK = "PROVEEDOR_DESCONOCIDO"


def sanitize_component(name: str, fallback: str = _FALLBACK) -> str:
    """Convert a text into a valid folder/file name on Windows."""
    cleaned = _INVALID_CHARS.sub("", name)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .")
    cleaned = cleaned[:_MAX_COMPONENT_LENGTH].strip(" .")
    return cleaned or fallback


def build_filename(invoice: ParsedInvoice) -> str:
    """Build the final PDF name from the extracted data."""
    supplier = sanitize_component(invoice.supplier)
    return f"{supplier} {invoice.type_label} {invoice.full_number}.pdf"
