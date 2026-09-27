"""Tests for decoding the AFIP QR and overlaying it on the text parse."""

from __future__ import annotations

from datetime import date

from automator.domain.models import DocumentType
from automator.domain.parser import parse_invoice
from automator.domain.parser.afip_qr import parse_afip_qr, unique_afip_qr
from fixtures.invoices import (
    CUIT_ONE,
    CUIT_TWO,
    INVOICE_QUOTING_ORDER_TEXT,
    ORDEN_COMPRA_TEXT,
    PREPRINTED_FORM_TEXT,
    SUPPLIER_CUIT,
    afip_qr_url,
)


def test_decodes_the_voucher_identity() -> None:
    qr = parse_afip_qr(afip_qr_url())
    assert qr is not None
    assert qr.issuer_cuit == SUPPLIER_CUIT
    assert (qr.sales_point, qr.number) == (3, 10650)
    assert qr.voucher is not None
    assert qr.voucher.label == "FC A"
    assert qr.receiver_cuit == CUIT_ONE
    assert qr.issue_date == date(2026, 9, 17)


def test_accepts_arca_host_byte_order_mark_and_key_casing() -> None:
    url = afip_qr_url(host="serviciosweb.arca.gob.ar/genericos/comprobantes/cae.aspx", tipoCmp=3)
    qr = parse_afip_qr("﻿" + url.replace("tipoCmp", "TIPOCMP"))
    assert qr is not None
    assert qr.voucher is not None
    assert qr.voucher.label == "NC A"


def test_accepts_unpadded_urlsafe_base64() -> None:
    url = afip_qr_url()
    prefix, encoded = url.split("?p=")
    urlsafe = encoded.replace("+", "-").replace("/", "_").rstrip("=")
    assert parse_afip_qr(f"{prefix}?p={urlsafe}") == parse_afip_qr(url)


def test_rejects_qr_from_other_hosts() -> None:
    # A payment QR (or a phishing look-alike) must never feed filing data.
    assert parse_afip_qr(afip_qr_url(host="www.mercadopago.com.ar/")) is None
    assert parse_afip_qr(afip_qr_url(host="afip.gob.ar.example.com/")) is None


def test_rejects_invalid_issuer_cuit_or_number() -> None:
    assert parse_afip_qr(afip_qr_url(cuit=30999999990)) is None
    assert parse_afip_qr(afip_qr_url(nroCmp=0)) is None
    assert parse_afip_qr(afip_qr_url(ptoVta="x")) is None


def test_garbage_payload_is_ignored() -> None:
    assert parse_afip_qr("https://www.afip.gob.ar/fe/qr/?p=%%%not-base64") is None
    assert parse_afip_qr("texto cualquiera") is None


def test_receiver_without_cuit_document_is_unknown() -> None:
    qr = parse_afip_qr(afip_qr_url(tipoDocRec=99, nroDocRec=0))
    assert qr is not None
    assert qr.receiver_cuit is None


def test_unknown_voucher_code_keeps_identity() -> None:
    qr = parse_afip_qr(afip_qr_url(tipoCmp=999))
    assert qr is not None
    assert qr.voucher is None


def test_repeated_qr_counts_once_and_different_ones_cancel_out() -> None:
    one, other = afip_qr_url(), afip_qr_url(nroCmp=10651)
    assert unique_afip_qr([one, one, "ruido"]) == parse_afip_qr(one)
    assert unique_afip_qr([one, other]) is None
    assert unique_afip_qr([]) is None


def test_qr_fills_what_a_preprinted_form_hides() -> None:
    qr = parse_afip_qr(afip_qr_url(nroCmp=3590, ptoVta=2))
    invoice = parse_invoice(PREPRINTED_FORM_TEXT, [CUIT_ONE], qr)
    assert invoice.issuer_cuit == SUPPLIER_CUIT
    assert invoice.buyer_cuit == CUIT_ONE
    assert invoice.qr_verified
    # The printed width "00002" agrees with the QR, so the printed form is kept.
    assert invoice.full_number == "00002-00003590"


def test_qr_number_wins_over_a_disagreeing_text() -> None:
    qr = parse_afip_qr(afip_qr_url(ptoVta=7, nroCmp=42))
    invoice = parse_invoice(INVOICE_QUOTING_ORDER_TEXT, [CUIT_ONE], qr)
    assert invoice.full_number == "0007-00000042"


def test_qr_makes_it_an_invoice_even_with_order_wording() -> None:
    invoice = parse_invoice(ORDEN_COMPRA_TEXT, [CUIT_ONE], parse_afip_qr(afip_qr_url()))
    assert invoice.document_type is DocumentType.FACTURA


def test_qr_receiver_outside_our_companies_is_not_a_buyer() -> None:
    qr = parse_afip_qr(afip_qr_url(nroDocRec=int(CUIT_TWO)))
    invoice = parse_invoice(INVOICE_QUOTING_ORDER_TEXT, [CUIT_ONE], qr)
    assert invoice.buyer_cuit is None
    assert not invoice.ambiguous_buyer


def test_qr_resolves_an_intercompany_invoice() -> None:
    text = f"FACTURA\nCod. 01\nCUIT: {CUIT_ONE}\nCUIT: {CUIT_TWO}\n"
    qr = parse_afip_qr(afip_qr_url(cuit=int(CUIT_ONE), nroDocRec=int(CUIT_TWO)))
    invoice = parse_invoice(text, [CUIT_ONE, CUIT_TWO], qr)
    assert invoice.buyer_cuit == CUIT_TWO
    assert not invoice.ambiguous_buyer


def test_our_company_as_seller_is_never_the_buyer() -> None:
    text = f"FACTURA\nCod. 01\nCUIT: {CUIT_ONE}\n"
    qr = parse_afip_qr(afip_qr_url(cuit=int(CUIT_ONE), tipoDocRec=99, nroDocRec=0))
    invoice = parse_invoice(text, [CUIT_ONE], qr)
    assert invoice.buyer_cuit is None
