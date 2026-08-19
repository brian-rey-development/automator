"""Parse an AFIP invoice (not a purchase order)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from automator.domain.cuit import unique_issuer_cuit
from automator.domain.models import UNKNOWN_SUPPLIER, ParsedInvoice
from automator.domain.parser.afip_codes import detect_voucher
from automator.domain.parser.numbers import detect_number
from automator.domain.parser.text import detect_buyer_cuit, detect_date, first_column

_SUPPLIER_PATTERN = re.compile(r"Raz[oó]n\s+Social\s*:?\s*(.+)", re.IGNORECASE)


def parse_factura(text: str, known_cuits: Iterable[str]) -> ParsedInvoice:
    sales_point, number = detect_number(text)
    buyer_cuit, ambiguous = detect_buyer_cuit(text, known_cuits)
    return ParsedInvoice(
        voucher=detect_voucher(text),
        sales_point=sales_point,
        number=number,
        supplier=_detect_supplier(text),
        buyer_cuit=buyer_cuit,
        ambiguous_buyer=ambiguous,
        issue_date=detect_date(text),
        issuer_cuit=unique_issuer_cuit(text, buyer_cuit),
    )


def _detect_supplier(text: str) -> str:
    match = _SUPPLIER_PATTERN.search(text)
    if match and first_column(match.group(1)):
        return first_column(match.group(1))
    return UNKNOWN_SUPPLIER
