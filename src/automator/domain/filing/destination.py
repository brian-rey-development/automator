"""Resolution of the destination folder for an invoice."""

from __future__ import annotations

from pathlib import Path

from automator.domain.filenames import sanitize_component
from automator.domain.models import ParsedInvoice

_NO_DATE = "sin_fecha"


class _TemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def destination_dir(invoice: ParsedInvoice, base_folder: Path, template: str = "{supplier}") -> Path:
    context = _template_context(invoice, base_folder)
    filled = [segment.format_map(context) for segment in template.split("/") if segment]
    segments = [sanitize_component(part) for part in filled if part.strip()]
    return base_folder.joinpath(*segments) if segments else base_folder


def _template_context(invoice: ParsedInvoice, base_folder: Path) -> _TemplateContext:
    issued = invoice.issue_date
    return _TemplateContext(
        supplier=invoice.supplier,
        society=base_folder.name,
        year=f"{issued.year:04d}" if issued else _NO_DATE,
        month=f"{issued.month:02d}" if issued else _NO_DATE,
        day=f"{issued.day:02d}" if issued else _NO_DATE,
    )
