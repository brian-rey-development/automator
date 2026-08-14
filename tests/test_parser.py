"""Tests de extraccion de datos de facturas (nucleo del sistema)."""

from __future__ import annotations

import pytest

from automator.domain.models import VoucherKind
from automator.domain.parser import parse_invoice
from tests.conftest import (
    COMBINED_NUMBER_TEXT,
    CUIT_ONE,
    CUIT_TWO,
    FACTURA_A_TEXT,
    NO_RAZON_SOCIAL_TEXT,
    NOTA_CREDITO_B_TEXT,
    NOTA_DEBITO_B_TEXT,
)


def test_parses_factura_a_completely() -> None:
    invoice = parse_invoice(FACTURA_A_TEXT, [CUIT_ONE])
    assert invoice.voucher.label == "FC A"
    assert invoice.full_number == "0001-00000123"
    assert invoice.supplier == "PROVEEDOR EJEMPLO SRL"
    assert invoice.buyer_cuit == CUIT_ONE


def test_detects_credit_note_kind_and_letter() -> None:
    invoice = parse_invoice(NOTA_CREDITO_B_TEXT)
    assert invoice.voucher.kind is VoucherKind.CREDIT_NOTE
    assert invoice.voucher.label == "NC B"
    assert invoice.full_number == "0003-00000045"


def test_detects_debit_note() -> None:
    invoice = parse_invoice(NOTA_DEBITO_B_TEXT)
    assert invoice.voucher.label == "ND B"


def test_supports_combined_number_format() -> None:
    invoice = parse_invoice(COMBINED_NUMBER_TEXT)
    assert invoice.full_number == "0002-00000777"
    assert invoice.voucher.label == "FC A"


def test_supplier_unknown_when_no_razon_social_label() -> None:
    # Sin la etiqueta "Razon Social" no se adivina con la primera linea: se marca
    # como desconocido para que el procesador lo envie a revision.
    invoice = parse_invoice(NO_RAZON_SOCIAL_TEXT)
    assert invoice.supplier == "PROVEEDOR_DESCONOCIDO"
    assert not invoice.has_supplier


def test_matches_cuit_ignoring_separators() -> None:
    invoice = parse_invoice(FACTURA_A_TEXT, [CUIT_ONE])
    assert invoice.buyer_cuit == CUIT_ONE


def test_returns_none_when_cuit_is_unknown() -> None:
    invoice = parse_invoice(FACTURA_A_TEXT, ["99999999999"])
    assert invoice.buyer_cuit is None
    assert not invoice.ambiguous_buyer


def test_single_known_cuit_is_not_ambiguous() -> None:
    invoice = parse_invoice(FACTURA_A_TEXT, [CUIT_ONE, CUIT_TWO])
    assert invoice.buyer_cuit == CUIT_ONE
    assert not invoice.ambiguous_buyer


def test_two_known_cuits_are_marked_ambiguous() -> None:
    # Factura entre dos sociedades propias: no se puede decidir el comprador.
    text = f"FACTURA\nCod. 01\nCUIT: {CUIT_ONE}\nCUIT: {CUIT_TWO}\n"
    invoice = parse_invoice(text, [CUIT_ONE, CUIT_TWO])
    assert invoice.buyer_cuit is None
    assert invoice.ambiguous_buyer


def test_detects_issue_date() -> None:
    from datetime import date

    invoice = parse_invoice(FACTURA_A_TEXT)
    assert invoice.issue_date == date(2026, 8, 1)


def test_missing_or_invalid_date_is_none() -> None:
    assert parse_invoice("FACTURA\nCod. 01\n").issue_date is None
    assert parse_invoice("Fecha de Emision: 45/13/2026\n").issue_date is None


def test_empty_text_uses_deterministic_defaults() -> None:
    invoice = parse_invoice("")
    assert invoice.voucher.label == "FC A"
    assert invoice.full_number == "0000-00000000"
    assert invoice.supplier == "PROVEEDOR_DESCONOCIDO"
    assert invoice.buyer_cuit is None


@pytest.mark.parametrize(
    ("code", "expected_label"),
    [("Cod. 01", "FC A"), ("Cod. 06", "FC B"), ("Cod. 11", "FC C"), ("Cod. 03", "NC A"), ("Cod. 02", "ND A")],
)
def test_afip_code_maps_to_voucher(code: str, expected_label: str) -> None:
    invoice = parse_invoice(f"COMPROBANTE\n{code}\n")
    assert invoice.voucher.label == expected_label


def test_parser_never_raises_on_garbage() -> None:
    # Robustez: texto arbitrario no debe romper el parser.
    invoice = parse_invoice("\x00\x01 ??? \n---\n123")
    assert invoice.voucher.label == "FC A"


def test_afip_code_ignores_long_numbers_like_cae() -> None:
    # Un CAE largo tras "Codigo" no debe interpretarse como codigo de comprobante.
    text = "FACTURA\nCodigo de Autorizacion (CAE): 71234567890123\nCod. 06\nComp. Nro: 0001-00000001\n"
    invoice = parse_invoice(text)
    assert invoice.voucher.label == "FC B"


def test_has_number_flags_missing_number() -> None:
    assert parse_invoice("Documento sin numero").has_number is False
    assert parse_invoice(FACTURA_A_TEXT).has_number is True
