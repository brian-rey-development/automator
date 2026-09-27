"""Extraction of AFIP invoice data from plain text and the voucher's QR."""

from __future__ import annotations

from collections.abc import Iterable

from automator.domain.models import ParsedInvoice
from automator.domain.parser.afip_qr import AfipQr
from automator.domain.parser.factura import parse_factura
from automator.domain.parser.purchase_order import looks_like_order, parse_order
from automator.domain.parser.qr_merge import merge_qr


def parse_invoice(text: str, known_cuits: Iterable[str] = (), qr: AfipQr | None = None) -> ParsedInvoice:
    known = tuple(known_cuits)
    if qr is not None:
        return merge_qr(parse_factura(text, known), qr, known)
    if looks_like_order(text):
        return parse_order(text, known)
    return parse_factura(text, known)
