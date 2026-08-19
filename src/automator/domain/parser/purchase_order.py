"""Parse a purchase order (Orden de Compra)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from automator.domain.models import UNKNOWN_SUPPLIER, DocumentType, ParsedInvoice, Voucher, VoucherKind
from automator.domain.parser.numbers import default_number
from automator.domain.parser.text import detect_buyer_cuit, detect_date, first_column

_DEFAULT_LETTER = "A"
_ORDER_PATTERN = re.compile(r"(?m)^\s*\bORD(?:EN)?\.?\s+(?:DE\s+)?COMPRA\b", re.IGNORECASE)
_ORDER_NUMBER_PATTERN = re.compile(
    r"ORD(?:EN)?\.?\s+(?:DE\s+)?COMPRA\s+N[roº°]*\.?\s*:?\s*(\d{4})\s*-\s*(\d+)",
    re.IGNORECASE,
)
_PROVEEDOR_PATTERN = re.compile(r"Proveedor\s*:?\s*(.+)", re.IGNORECASE)
_SOCIEDAD_PATTERN = re.compile(r"Sociedad\s*:?\s*(.+)", re.IGNORECASE)


def looks_like_order(text: str) -> bool:
    return _ORDER_PATTERN.search(text) is not None


def parse_order(text: str, known_cuits: Iterable[str]) -> ParsedInvoice:
    sales_point, number = _detect_order_number(text)
    buyer_cuit, ambiguous = detect_buyer_cuit(text, known_cuits)
    return ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, _DEFAULT_LETTER),
        sales_point=sales_point,
        number=number,
        supplier=_detect_order_supplier(text),
        buyer_cuit=buyer_cuit,
        ambiguous_buyer=ambiguous,
        issue_date=detect_date(text),
        document_type=DocumentType.ORDEN_COMPRA,
        buyer_name=_detect_buyer_name(text),
    )


def _detect_order_number(text: str) -> tuple[str, str]:
    match = _ORDER_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1).zfill(4), match.group(2).zfill(8)
    return default_number()


def _detect_order_supplier(text: str) -> str:
    match = _PROVEEDOR_PATTERN.search(text)
    if match and first_column(match.group(1)):
        return first_column(match.group(1))
    return UNKNOWN_SUPPLIER


def _detect_buyer_name(text: str) -> str | None:
    match = _SOCIEDAD_PATTERN.search(text)
    return first_column(match.group(1)) or None if match else None
