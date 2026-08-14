"""Resolucion de la carpeta destino para una factura."""

from __future__ import annotations

from pathlib import Path

from automator.domain.filenames import sanitize_component
from automator.domain.models import ParsedInvoice

_NO_DATE = "sin_fecha"


def destination_dir(invoice: ParsedInvoice, base_folder: Path, template: str = "{supplier}") -> Path:
    """Devuelve la carpeta destino: base de la sociedad + subcarpetas de la plantilla.

    La plantilla admite {supplier} {society} {year} {month} {day}. Cada segmento
    (separado por '/') se saneada para que sea un nombre valido en Windows.
    """
    context = _template_context(invoice, base_folder)
    segments = [sanitize_component(segment.format(**context)) for segment in template.split("/") if segment]
    return base_folder.joinpath(*segments) if segments else base_folder


def _template_context(invoice: ParsedInvoice, base_folder: Path) -> dict[str, str]:
    issued = invoice.issue_date
    return {
        "supplier": invoice.supplier,
        "society": base_folder.name,
        "year": f"{issued.year:04d}" if issued else _NO_DATE,
        "month": f"{issued.month:02d}" if issued else _NO_DATE,
        "day": f"{issued.day:02d}" if issued else _NO_DATE,
    }
