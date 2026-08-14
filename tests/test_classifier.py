"""Tests de resolucion de carpeta destino."""

from __future__ import annotations

from pathlib import Path

from automator.domain.classifier import destination_dir
from automator.domain.models import ParsedInvoice, Voucher, VoucherKind


def _invoice(supplier: str) -> ParsedInvoice:
    return ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, "A"),
        sales_point="0001",
        number="00000001",
        supplier=supplier,
        buyer_cuit=None,
    )


def test_destination_joins_base_with_sanitized_supplier() -> None:
    base = Path("/salida/ANDREOLI")
    result = destination_dir(_invoice("ACME S.A."), base)
    # Windows no admite carpetas terminadas en punto: se elimina el punto final.
    assert result == base / "ACME S.A"


def test_destination_sanitizes_invalid_supplier() -> None:
    base = Path("/salida/ANDREOLI")
    result = destination_dir(_invoice("ACME: S.A. *"), base)
    assert result == base / "ACME S.A"
