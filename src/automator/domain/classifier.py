"""Resolucion de la carpeta destino para una factura."""

from __future__ import annotations

from pathlib import Path

from automator.domain.filenames import sanitize_component
from automator.domain.models import ParsedInvoice


def destination_dir(invoice: ParsedInvoice, base_folder: Path) -> Path:
    """Devuelve la carpeta destino: base de la sociedad + subcarpeta del proveedor."""
    return base_folder / sanitize_component(invoice.supplier)
