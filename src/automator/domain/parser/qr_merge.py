"""Overlay of the authoritative AFIP QR data on a text-parsed invoice."""

from __future__ import annotations

import dataclasses
from collections.abc import Collection

from automator.domain.models import ParsedInvoice
from automator.domain.parser.afip_qr import AfipQr


def merge_qr(invoice: ParsedInvoice, qr: AfipQr, known_cuits: Collection[str]) -> ParsedInvoice:
    """The QR wins on identity fields; the text still supplies the supplier name."""
    sales_point, number = _number(invoice, qr)
    buyer_cuit, ambiguous = _buyer(invoice, qr, known_cuits)
    return dataclasses.replace(
        invoice,
        voucher=qr.voucher or invoice.voucher,
        sales_point=sales_point,
        number=number,
        buyer_cuit=buyer_cuit,
        ambiguous_buyer=ambiguous,
        issue_date=qr.issue_date or invoice.issue_date,
        issuer_cuit=qr.issuer_cuit,
        qr_verified=True,
    )


def _number(invoice: ParsedInvoice, qr: AfipQr) -> tuple[str, str]:
    # Keep the printed width ("00003" vs "0003") when it agrees, so names and duplicate
    # keys stay identical to what the text-only parser produced for the same voucher.
    agrees = int(invoice.sales_point) == qr.sales_point and int(invoice.number) == qr.number
    if invoice.has_number and agrees:
        return invoice.sales_point, invoice.number
    return f"{qr.sales_point:04d}", f"{qr.number:08d}"


def _buyer(invoice: ParsedInvoice, qr: AfipQr, known_cuits: Collection[str]) -> tuple[str | None, bool]:
    if qr.receiver_cuit is not None:
        return (qr.receiver_cuit if qr.receiver_cuit in known_cuits else None), False
    if invoice.buyer_cuit == qr.issuer_cuit:
        # One of our own companies is the seller here, never the buyer.
        return None, False
    return invoice.buyer_cuit, invoice.ambiguous_buyer
