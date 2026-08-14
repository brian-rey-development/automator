"""Construccion y saneamiento de nombres de archivo/carpeta para Windows."""

from __future__ import annotations

import re

from automator.domain.models import ParsedInvoice

# Caracteres prohibidos en nombres de archivo de Windows.
_INVALID_CHARS = re.compile(r'[\\/*?:"<>|\r\n\t]')
_WHITESPACE = re.compile(r"\s+")
_MAX_COMPONENT_LENGTH = 150
_FALLBACK = "PROVEEDOR_DESCONOCIDO"


def sanitize_component(name: str, fallback: str = _FALLBACK) -> str:
    """Convierte un texto en un nombre valido de carpeta/archivo en Windows."""
    cleaned = _INVALID_CHARS.sub("", name)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .")
    cleaned = cleaned[:_MAX_COMPONENT_LENGTH].strip(" .")
    return cleaned or fallback


def build_filename(invoice: ParsedInvoice) -> str:
    """Construye el nombre final del PDF a partir de los datos extraidos."""
    supplier = sanitize_component(invoice.supplier)
    return f"{supplier} {invoice.voucher.label} {invoice.full_number}.pdf"
