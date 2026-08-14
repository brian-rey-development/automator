"""Orquestacion del procesamiento de un unico PDF de factura."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from automator.config import AppConfig
from automator.domain.classifier import destination_dir
from automator.domain.filenames import build_filename
from automator.domain.models import ParsedInvoice, ProcessOutcome, ProcessResult
from automator.domain.parser import parse_invoice
from automator.services import file_ops
from automator.services.pdf_reader import extract_text

logger = logging.getLogger(__name__)

# Callable inyectables para poder testear sin PDFs ni configuracion global reales.
TextExtractor = Callable[[Path], str]
ConfigProvider = Callable[[], AppConfig]


class InvoiceProcessor:
    """Procesa un PDF: lo lee, extrae datos, lo clasifica y lo archiva."""

    def __init__(self, config_provider: ConfigProvider, extractor: TextExtractor = extract_text) -> None:
        self._config_provider = config_provider
        self._extractor = extractor

    def process(self, source: Path) -> ProcessResult:
        config = self._config_provider()
        if not source.exists():
            return _result(source, ProcessOutcome.SKIPPED_MISSING, None, None, "El archivo ya no existe.")
        if config.wait_for_stability and not file_ops.wait_until_stable(source, config.stability_timeout_s):
            return self._quarantine(source, config, "La descarga no termino a tiempo; el archivo quedo incompleto.")
        return self._process_stable(source, config)

    def _process_stable(self, source: Path, config: AppConfig) -> ProcessResult:
        try:
            text = self._extractor(source)
        except Exception as exc:
            logger.exception("Fallo al leer el PDF %s", source)
            return self._quarantine(source, config, f"No se pudo leer el PDF: {exc}")
        if not text.strip():
            return self._quarantine(source, config, "El PDF no contiene texto legible (posible escaneo).")
        invoice = parse_invoice(text, config.known_cuits())
        if invoice.ambiguous_buyer:
            return self._archive(
                source,
                config,
                invoice,
                config.review_folder,
                ProcessOutcome.NEEDS_REVIEW,
                "Aparecen varias de tus sociedades: revisa cual es la compradora.",
            )
        if not _is_reliable(invoice, config):
            return self._archive(
                source,
                config,
                invoice,
                config.review_folder,
                ProcessOutcome.NEEDS_REVIEW,
                "Datos incompletos: se envio a revision manual.",
            )
        if invoice.buyer_cuit is None:
            # Se archiva igual (no se pierde), pero con un estado distinto para que el
            # usuario vea que la sociedad compradora no se pudo identificar.
            return self._archive(
                source,
                config,
                invoice,
                config.unknown_folder,
                ProcessOutcome.UNCLASSIFIED,
                "Archivado sin clasificar: no se detecto la sociedad compradora.",
            )
        return self._archive(
            source,
            config,
            invoice,
            config.folder_for_cuit(invoice.buyer_cuit),
            ProcessOutcome.MOVED,
            "Archivado correctamente.",
        )

    def _archive(
        self,
        source: Path,
        config: AppConfig,
        invoice: ParsedInvoice,
        base_folder: Path,
        outcome: ProcessOutcome,
        message: str,
    ) -> ProcessResult:
        target_dir = destination_dir(invoice, base_folder)
        filename = build_filename(invoice)
        if config.dry_run:
            return _result(
                source, ProcessOutcome.DRY_RUN, target_dir / filename, invoice, "Simulacion: no se movio el archivo."
            )
        try:
            destination = file_ops.move_file(source, target_dir, filename)
        except Exception as exc:
            logger.exception("Fallo al mover %s", source)
            return self._quarantine(source, config, f"No se pudo archivar: {exc}")
        return _result(source, outcome, destination, invoice, message)

    def _quarantine(self, source: Path, config: AppConfig, message: str) -> ProcessResult:
        # En modo simulacion o si el archivo ya no esta, no se mueve nada.
        if config.dry_run or not source.exists():
            return _result(source, ProcessOutcome.ERROR, None, None, message)
        try:
            destination = file_ops.move_file(source, config.quarantine_folder, source.name)
        except Exception:
            logger.exception("No se pudo poner en cuarentena %s; queda en la carpeta de entrada para reintento", source)
            return _result(source, ProcessOutcome.ERROR, None, None, message)
        return _result(source, ProcessOutcome.QUARANTINED, destination, None, message)


def _is_reliable(invoice: ParsedInvoice, config: AppConfig) -> bool:
    """Confiable si tiene numero, se detecto el proveedor y no es una sociedad propia.

    Si el proveedor no se detecto (centinela) se envia a revision para no archivarlo
    bajo un nombre inventado. Si coincide con una sociedad configurada, es senal de
    que se leyo al comprador en lugar del emisor: tambien va a revision.
    """
    if not invoice.has_number or not invoice.has_supplier:
        return False
    return invoice.supplier.casefold() not in config.society_names()


def _result(
    source: Path,
    outcome: ProcessOutcome,
    destination: Path | None,
    invoice: ParsedInvoice | None,
    message: str,
) -> ProcessResult:
    return ProcessResult(source=source, outcome=outcome, destination=destination, invoice=invoice, message=message)
