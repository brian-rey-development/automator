"""Tests for destination folder resolution."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from automator.domain.classifier import destination_dir
from automator.domain.models import ParsedInvoice, Voucher, VoucherKind


def _invoice(supplier: str, issue_date: date | None = None) -> ParsedInvoice:
    return ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, "A"),
        sales_point="0001",
        number="00000001",
        supplier=supplier,
        buyer_cuit=None,
        issue_date=issue_date,
    )


def test_destination_joins_base_with_sanitized_supplier() -> None:
    base = Path("/salida/EMPRESA")
    result = destination_dir(_invoice("ACME S.A."), base)
    # Windows does not allow folders ending in a dot: the trailing dot is removed.
    assert result == base / "ACME S.A"


def test_destination_sanitizes_invalid_supplier() -> None:
    base = Path("/salida/EMPRESA")
    result = destination_dir(_invoice("ACME: S.A. *"), base)
    assert result == base / "ACME S.A"


def test_template_with_date_tokens() -> None:
    base = Path("/salida/EMPRESA")
    invoice = _invoice("ACME S.A.", issue_date=date(2026, 8, 14))
    result = destination_dir(invoice, base, "{year}/{month}/{supplier}")
    assert result == base / "2026" / "08" / "ACME S.A"


def test_template_falls_back_when_date_missing() -> None:
    base = Path("/salida/EMPRESA")
    result = destination_dir(_invoice("ACME S.A."), base, "{year}/{supplier}")
    assert result == base / "sin_fecha" / "ACME S.A"
