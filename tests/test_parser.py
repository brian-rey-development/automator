"""Tests for invoice data extraction (the core of the system)."""

from __future__ import annotations

import pytest

from automator.domain.filenames import build_filename
from automator.domain.models import DocumentType, VoucherKind
from automator.domain.parser import parse_invoice
from tests.conftest import (
    AMBIGUOUS_STANDALONE_TEXT,
    COLUMN_BLEED_ORDER_TEXT,
    COLUMN_BLEED_SUPPLIER_TEXT,
    COMBINED_NUMBER_TEXT,
    COMPROBANTE_WORD_TEXT,
    CUIT_ONE,
    CUIT_TWO,
    FACTURA_A_TEXT,
    INLINE_NUMERO_TEXT,
    NO_RAZON_SOCIAL_TEXT,
    NOTA_CREDITO_B_TEXT,
    NOTA_DEBITO_B_TEXT,
    ONLY_IIBB_TEXT,
    ORDEN_COMPRA_NO_CUIT_TEXT,
    ORDEN_COMPRA_TEXT,
    SPLIT_NUMBER_TEXT,
    STANDALONE_TABLE_TEXT,
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


def test_reads_full_word_comprobante_and_ignores_iibb() -> None:
    invoice = parse_invoice(COMPROBANTE_WORD_TEXT)
    assert invoice.full_number == "1238-00002972"


def test_reads_inline_numero_label_with_dash() -> None:
    invoice = parse_invoice(INLINE_NUMERO_TEXT)
    assert invoice.full_number == "0007-00001522"


def test_reads_standalone_table_number_without_grabbing_cuit() -> None:
    invoice = parse_invoice(STANDALONE_TABLE_TEXT)
    assert invoice.full_number == "0004-00004899"


def test_ambiguous_standalone_numbers_stay_default() -> None:
    invoice = parse_invoice(AMBIGUOUS_STANDALONE_TEXT)
    assert not invoice.has_number


def test_iibb_alone_is_never_taken_as_number() -> None:
    invoice = parse_invoice(ONLY_IIBB_TEXT)
    assert not invoice.has_number


def test_reads_split_point_of_sale_and_sequence() -> None:
    invoice = parse_invoice(SPLIT_NUMBER_TEXT)
    assert invoice.full_number == "0022-00082809"


def test_supplier_capture_stops_at_column_gap() -> None:
    invoice = parse_invoice(COLUMN_BLEED_SUPPLIER_TEXT)
    assert invoice.supplier == "PROVEEDOR COLUMNA SRL"


def test_order_labels_stop_at_column_gap() -> None:
    invoice = parse_invoice(COLUMN_BLEED_ORDER_TEXT)
    assert invoice.supplier == "JIMENEZ LORENZO HECTOR"
    assert invoice.buyer_name == "ANDREOLI AGRO S.A."


def test_supplier_unknown_when_no_razon_social_label() -> None:
    # Without the "Razon Social" label it is not guessed from the first line: it is
    # flagged as unknown so the processor sends it to review.
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
    # Invoice between two of our own societies: the buyer cannot be decided.
    text = f"FACTURA\nCod. 01\nCUIT: {CUIT_ONE}\nCUIT: {CUIT_TWO}\n"
    invoice = parse_invoice(text, [CUIT_ONE, CUIT_TWO])
    assert invoice.buyer_cuit is None
    assert invoice.ambiguous_buyer


def test_known_cuit_not_matched_inside_longer_number() -> None:
    # The 11 digits of a known CUIT appear as a substring of a longer number (a CAE and
    # a concatenated run). A digit-bounded match must NOT treat it as the buyer, otherwise
    # the invoice would be misfiled into that company's folder.
    buried = f"9{CUIT_ONE}9"  # 13-digit run containing CUIT_ONE
    text = f"FACTURA\nCod. 01\nCAE: {buried}\nComp. Nro: 0001-00000001\n"
    invoice = parse_invoice(text, [CUIT_ONE])
    assert invoice.buyer_cuit is None
    assert not invoice.ambiguous_buyer


def test_known_cuit_matched_with_separators_and_boundaries() -> None:
    # A properly delimited CUIT (with dashes) is still detected as the buyer.
    dashed = f"{CUIT_ONE[:2]}-{CUIT_ONE[2:10]}-{CUIT_ONE[10]}"
    invoice = parse_invoice(f"FACTURA\nCod. 01\nCUIT: {dashed}\n", [CUIT_ONE])
    assert invoice.buyer_cuit == CUIT_ONE


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
    # Robustness: arbitrary text must not break the parser.
    invoice = parse_invoice("\x00\x01 ??? \n---\n123")
    assert invoice.voucher.label == "FC A"


def test_afip_code_ignores_long_numbers_like_cae() -> None:
    # A long CAE after "Codigo" must not be interpreted as a voucher code.
    text = "FACTURA\nCodigo de Autorizacion (CAE): 71234567890123\nCod. 06\nComp. Nro: 0001-00000001\n"
    invoice = parse_invoice(text)
    assert invoice.voucher.label == "FC B"


def test_has_number_flags_missing_number() -> None:
    assert parse_invoice("Documento sin numero").has_number is False
    assert parse_invoice(FACTURA_A_TEXT).has_number is True


def test_parses_purchase_order() -> None:
    invoice = parse_invoice(ORDEN_COMPRA_TEXT, [CUIT_ONE])
    assert invoice.document_type is DocumentType.ORDEN_COMPRA
    assert invoice.type_label == "OC"
    assert invoice.full_number == "2026-00004046"
    assert invoice.supplier == "FERRETERIA EJEMPLO SRL"
    assert invoice.buyer_cuit == CUIT_ONE
    assert invoice.buyer_name == "COMPRADORA UNO SA"


def test_purchase_order_matches_cuit_across_mixed_formats() -> None:
    # The OC prints the buyer CUIT without separators and the supplier CUIT with
    # dashes: the buyer is still matched from the contiguous 11-digit form.
    assert parse_invoice(ORDEN_COMPRA_TEXT, [CUIT_ONE]).buyer_cuit == CUIT_ONE


def test_purchase_order_filename_uses_oc_tag() -> None:
    invoice = parse_invoice(ORDEN_COMPRA_TEXT, [CUIT_ONE])
    assert build_filename(invoice) == "FERRETERIA EJEMPLO SRL OC 2026-00004046.pdf"


def test_purchase_order_without_cuit_keeps_buyer_name() -> None:
    invoice = parse_invoice(ORDEN_COMPRA_NO_CUIT_TEXT)
    assert invoice.document_type is DocumentType.ORDEN_COMPRA
    assert invoice.buyer_cuit is None
    assert invoice.buyer_name == "COMPRADORA UNO S.A."
