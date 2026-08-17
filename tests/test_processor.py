"""Tests for PDF processing orchestration (integration without real PDFs)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from automator.config import AppConfig, SocietyMapping
from automator.domain.models import ProcessOutcome
from automator.services.processor import InvoiceProcessor
from tests.conftest import (
    CUIT_ONE,
    CUIT_TWO,
    FACTURA_A_TEXT,
    ORDEN_COMPRA_NO_CUIT_TEXT,
    ORDEN_COMPRA_TEXT,
)


def _processor(config: AppConfig, text: str) -> InvoiceProcessor:
    # A fake extractor is injected to avoid depending on real PDFs.
    return InvoiceProcessor(lambda: config, extractor=lambda _path: text)


def test_moves_invoice_to_matching_society_folder(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("descarga.pdf")
    result = _processor(config, FACTURA_A_TEXT).process(source)

    folder = config.folder_for_cuit(CUIT_ONE) / "PROVEEDOR EJEMPLO SRL"
    expected = folder / "PROVEEDOR EJEMPLO SRL FC A 0001-00000123.pdf"
    assert result.outcome is ProcessOutcome.MOVED
    assert result.destination == expected
    assert expected.exists()
    assert not source.exists()


def test_unknown_cuit_goes_to_unclassified_folder(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    # It is archived anyway, but with a different outcome (not MOVED) so the user
    # sees that the buying society was not identified.
    config = make_config()
    source = dummy_pdf("otro.pdf")
    text = "FACTURA\nCod. 01\nRazon Social: X S.A.\nComp. Nro: 0001-00000001\n"
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.UNCLASSIFIED
    assert result.destination is not None
    assert config.unknown_folder in result.destination.parents


def test_dry_run_does_not_move_file(make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]) -> None:
    config = make_config(dry_run=True)
    source = dummy_pdf("simulacion.pdf")
    result = _processor(config, FACTURA_A_TEXT).process(source)
    assert result.outcome is ProcessOutcome.DRY_RUN
    assert result.intended is ProcessOutcome.MOVED
    assert source.exists()


def test_dry_run_keeps_review_as_intended_outcome(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config(dry_run=True)
    source = dummy_pdf("sin_numero.pdf")
    text = "FACTURA\nCod. 01\nRazon Social: PROVEEDOR SIN NUMERO S.A.\n"
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.DRY_RUN
    assert result.intended is ProcessOutcome.NEEDS_REVIEW
    assert result.destination is not None
    assert config.review_folder in result.destination.parents
    assert source.exists()


def test_copy_mode_keeps_original_and_places_copy(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config(copy_files=True)
    source = dummy_pdf("descarga.pdf")
    result = _processor(config, FACTURA_A_TEXT).process(source)

    folder = config.folder_for_cuit(CUIT_ONE) / "PROVEEDOR EJEMPLO SRL"
    expected = folder / "PROVEEDOR EJEMPLO SRL FC A 0001-00000123.pdf"
    assert result.outcome is ProcessOutcome.MOVED
    assert expected.exists()
    assert source.exists()  # the original is kept in the input folder


def test_copy_mode_quarantine_keeps_original(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config(copy_files=True)
    source = dummy_pdf("ilegible.pdf")
    result = _processor(config, "").process(source)  # empty text: unreadable PDF
    assert result.outcome is ProcessOutcome.QUARANTINED
    assert result.destination is not None
    assert result.destination.exists()
    assert source.exists()


def test_empty_text_is_quarantined(make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]) -> None:
    config = make_config()
    source = dummy_pdf("vacio.pdf")
    result = _processor(config, "   ").process(source)
    assert result.outcome is ProcessOutcome.QUARANTINED
    assert result.destination is not None
    assert config.quarantine_folder in result.destination.parents
    assert not source.exists()


def test_reader_error_is_quarantined(make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]) -> None:
    config = make_config()
    source = dummy_pdf("roto.pdf")

    def broken_extractor(_path: Path) -> str:
        raise ValueError("PDF corrupto")

    result = InvoiceProcessor(lambda: config, extractor=broken_extractor).process(source)
    assert result.outcome is ProcessOutcome.QUARANTINED
    assert not source.exists()


def test_missing_file_is_skipped(make_config: Callable[..., AppConfig]) -> None:
    config = make_config()
    result = _processor(config, FACTURA_A_TEXT).process(Path("/ruta/que/no/existe.pdf"))
    assert result.outcome is ProcessOutcome.SKIPPED_MISSING


def test_invoice_without_number_goes_to_review(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("sin_numero.pdf")
    text = "FACTURA\nCod. 01\nRazon Social: PROVEEDOR SIN NUMERO S.A.\n"
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.NEEDS_REVIEW
    assert result.destination is not None
    assert config.review_folder in result.destination.parents


def test_duplicate_invoice_goes_to_duplicates_folder(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("repetida.pdf")
    processor = InvoiceProcessor(lambda: config, extractor=lambda _p: FACTURA_A_TEXT, is_duplicate=lambda _inv: True)
    result = processor.process(source)
    assert result.outcome is ProcessOutcome.DUPLICATE
    assert result.destination is not None
    assert config.duplicates_folder in result.destination.parents


def test_ambiguous_intercompany_invoice_goes_to_review(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path], tmp_path: Path
) -> None:
    # Two of our own societies appear: the buyer cannot be decided, it goes to review.
    config = make_config(
        societies=(
            SocietyMapping(cuit=CUIT_ONE, name="COMPRADORA UNO SA", folder=tmp_path / "salida" / "A"),
            SocietyMapping(cuit=CUIT_TWO, name="COMPRADORA DOS SA", folder=tmp_path / "salida" / "C"),
        )
    )
    source = dummy_pdf("intercompany.pdf")
    text = (
        f"FACTURA\nCod. 01\nRazon Social: PROVEEDOR X\nComp. Nro: 0001-00000001\nCUIT: {CUIT_ONE}\nCUIT: {CUIT_TWO}\n"
    )
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.NEEDS_REVIEW
    assert result.destination is not None
    assert config.review_folder in result.destination.parents


def test_supplier_equal_to_society_goes_to_review(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    # If the detected supplier is our own society, the buyer was read: send to review.
    config = make_config()
    source = dummy_pdf("comprador.pdf")
    text = "FACTURA\nCod. 01\nRazon Social: COMPRADORA UNO SA\nComp. Nro: 0001-00000009\n"
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.NEEDS_REVIEW


def test_purchase_order_files_into_orders_area(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("orden.pdf")
    result = _processor(config, ORDEN_COMPRA_TEXT).process(source)

    expected = config.orders_folder / "COMPRADORA UNO SA" / "RICARDO BARTOLI Y CIA S.R.L"
    expected_file = expected / "RICARDO BARTOLI Y CIA S.R.L OC 2026-00004046.pdf"
    assert result.outcome is ProcessOutcome.MOVED
    assert result.destination == expected_file
    assert expected_file.exists()


def test_purchase_order_fuzzy_matches_society_by_name(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    # No buyer CUIT in the text; the near-identical society name resolves it.
    config = make_config()
    source = dummy_pdf("orden_fuzzy.pdf")
    result = _processor(config, ORDEN_COMPRA_NO_CUIT_TEXT).process(source)

    assert result.outcome is ProcessOutcome.MOVED
    assert result.destination is not None
    assert config.orders_folder / "COMPRADORA UNO SA" in result.destination.parents
    assert "nombre" in result.message


def test_purchase_order_without_society_goes_to_sin_sociedad(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("orden_sin.pdf")
    text = "ORD COMPRA  NRO: 2026-00009999\nProveedor: FERRETERIA LEJANA SA\nSociedad: EMPRESA NO CONFIGURADA XYZ\n"
    result = _processor(config, text).process(source)

    assert result.outcome is ProcessOutcome.UNCLASSIFIED
    assert result.destination is not None
    assert config.orders_folder / "_SIN_SOCIEDAD" in result.destination.parents
