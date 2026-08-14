"""Tests de orquestacion del procesamiento de PDFs (integracion sin PDFs reales)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from automator.config import AppConfig, SocietyMapping
from automator.domain.models import ProcessOutcome
from automator.services.processor import InvoiceProcessor
from tests.conftest import CUIT_ANDREOLI, CUIT_CUENCA, FACTURA_A_TEXT


def _processor(config: AppConfig, text: str) -> InvoiceProcessor:
    # Se inyecta un extractor falso para no depender de PDFs reales.
    return InvoiceProcessor(lambda: config, extractor=lambda _path: text)


def test_moves_invoice_to_matching_society_folder(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("descarga.pdf")
    result = _processor(config, FACTURA_A_TEXT).process(source)

    # El punto final de "S.R.L." se elimina por compatibilidad con Windows.
    folder = config.folder_for_cuit(CUIT_ANDREOLI) / "ACME INSUMOS S.R.L"
    expected = folder / "ACME INSUMOS S.R.L FC A 0001-00000123.pdf"
    assert result.outcome is ProcessOutcome.MOVED
    assert result.destination == expected
    assert expected.exists()
    assert not source.exists()


def test_unknown_cuit_goes_to_unclassified_folder(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    # Se archiva igual, pero con outcome distinto (no MOVED) para que el usuario
    # vea que no se identifico la sociedad compradora.
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
    # Aparecen dos sociedades propias: no se puede decidir la compradora, va a revision.
    config = make_config(
        societies=(
            SocietyMapping(cuit=CUIT_ANDREOLI, name="ANDREOLI S.A.", folder=tmp_path / "salida" / "A"),
            SocietyMapping(cuit=CUIT_CUENCA, name="CUENCA S.A.", folder=tmp_path / "salida" / "C"),
        )
    )
    source = dummy_pdf("intercompany.pdf")
    text = (
        f"FACTURA\nCod. 01\nRazon Social: PROVEEDOR X\nComp. Nro: 0001-00000001\n"
        f"CUIT: {CUIT_ANDREOLI}\nCUIT: {CUIT_CUENCA}\n"
    )
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.NEEDS_REVIEW
    assert result.destination is not None
    assert config.review_folder in result.destination.parents


def test_supplier_equal_to_society_goes_to_review(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    # Si el proveedor detectado es la propia sociedad, se leyo al comprador: a revisar.
    config = make_config()
    source = dummy_pdf("comprador.pdf")
    text = "FACTURA\nCod. 01\nRazon Social: ANDREOLI S.A.\nComp. Nro: 0001-00000009\n"
    result = _processor(config, text).process(source)
    assert result.outcome is ProcessOutcome.NEEDS_REVIEW
