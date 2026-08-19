"""Tests for invoice identity and presence flags."""

from __future__ import annotations

from automator.domain.models import UNKNOWN_SUPPLIER, ParsedInvoice, Voucher, VoucherKind


def _invoice(**overrides: object) -> ParsedInvoice:
    values: dict[str, object] = {
        "voucher": Voucher(VoucherKind.INVOICE, "A"),
        "sales_point": "0001",
        "number": "00000123",
        "supplier": "ACME S.A.",
        "buyer_cuit": "30111111118",
    }
    values.update(overrides)
    return ParsedInvoice(**values)  # type: ignore[arg-type]


def test_identity_requires_number_and_supplier() -> None:
    invoice = _invoice()
    assert invoice.identity == "acme s.a.|0001-00000123|FC A"


def test_identity_normalizes_accents() -> None:
    invoice = _invoice(supplier="Café SRL")
    assert invoice.identity == "cafe srl|0001-00000123|FC A"


def test_identity_is_none_without_supplier() -> None:
    invoice = _invoice(supplier=UNKNOWN_SUPPLIER)
    assert invoice.has_supplier is False
    assert invoice.identity is None


def test_has_number_is_false_for_filler() -> None:
    invoice = _invoice(sales_point="0000", number="00000000")
    assert invoice.has_number is False
    assert invoice.identity is None


def test_has_number_is_true_when_only_sales_point_differs() -> None:
    invoice = _invoice(sales_point="0001", number="00000000")
    assert invoice.has_number is True
