"""Tests for sanitizing and building file names."""

from __future__ import annotations

import pytest

from automator.domain.filenames import build_filename, sanitize_component
from automator.domain.models import ParsedInvoice, Voucher, VoucherKind


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('ACME / S.A. : "test"', "ACME S.A. test"),
        ("  espacios   multiples  ", "espacios multiples"),
        ("nombre\\con/barras", "nombreconbarras"),
        ("...puntos...", "puntos"),
    ],
)
def test_sanitize_removes_invalid_characters(raw: str, expected: str) -> None:
    assert sanitize_component(raw) == expected


def test_sanitize_empty_uses_fallback() -> None:
    assert sanitize_component("   /:*?   ") == "PROVEEDOR_DESCONOCIDO"


def test_sanitize_truncates_long_names() -> None:
    result = sanitize_component("A" * 500)
    assert len(result) <= 150


def test_build_filename_uses_all_components() -> None:
    invoice = ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, "A"),
        sales_point="0001",
        number="00000123",
        supplier="ACME S.A.",
        buyer_cuit=None,
    )
    # The trailing dot is removed because Windows does not allow names ending in a dot.
    assert build_filename(invoice) == "ACME S.A FC A 0001-00000123.pdf"
