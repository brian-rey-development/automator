"""Extraction of AFIP invoice data from plain text."""

from __future__ import annotations

from collections.abc import Iterable

from automator.domain.models import ParsedInvoice
from automator.domain.parser.factura import parse_factura
from automator.domain.parser.purchase_order import looks_like_order, parse_order


def parse_invoice(text: str, known_cuits: Iterable[str] = ()) -> ParsedInvoice:
    if looks_like_order(text):
        return parse_order(text, known_cuits)
    return parse_factura(text, known_cuits)
