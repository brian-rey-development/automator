"""Orchestration of processing a single invoice PDF."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path

from automator.config import AppConfig
from automator.domain.buyer import BuyerResolution, resolve_buyer
from automator.domain.classifier import destination_dir
from automator.domain.filenames import build_filename
from automator.domain.models import DocumentType, ParsedInvoice, ProcessOutcome, ProcessResult
from automator.domain.parser import parse_invoice
from automator.domain.suppliers import SupplierRegistry
from automator.services import file_ops
from automator.services.pdf_reader import extract_text

logger = logging.getLogger(__name__)

# Injectable callables to allow testing without real PDFs or global configuration.
TextExtractor = Callable[[Path], str]
ConfigProvider = Callable[[], AppConfig]
DuplicateCheck = Callable[[ParsedInvoice], bool]
RegistryProvider = Callable[[], SupplierRegistry]

_EMPTY_REGISTRY = SupplierRegistry([])


def _never_duplicate(_invoice: ParsedInvoice) -> bool:
    return False


def _empty_registry() -> SupplierRegistry:
    return _EMPTY_REGISTRY


class InvoiceProcessor:
    """Processes a PDF: reads it, extracts data, classifies it and archives it."""

    def __init__(
        self,
        config_provider: ConfigProvider,
        extractor: TextExtractor = extract_text,
        is_duplicate: DuplicateCheck = _never_duplicate,
        registry_provider: RegistryProvider = _empty_registry,
    ) -> None:
        self._config_provider = config_provider
        self._extractor = extractor
        self._is_duplicate = is_duplicate
        self._registry_provider = registry_provider

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
        buyer = resolve_buyer(invoice, list(config.societies))
        invoice = self._canonicalize_supplier(invoice, text, buyer)
        if buyer.ambiguous:
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
        if self._is_duplicate(invoice):
            return self._archive(
                source,
                config,
                invoice,
                config.duplicates_folder,
                ProcessOutcome.DUPLICATE,
                "Duplicado: ya se habia archivado este documento antes.",
            )
        outcome, message = _outcome_for(invoice, buyer)
        return self._archive(source, config, invoice, _destination_base(invoice, buyer, config), outcome, message)

    def _canonicalize_supplier(self, invoice: ParsedInvoice, text: str, buyer: BuyerResolution) -> ParsedInvoice:
        """Replace the printed supplier name with the registry's canonical one, if known.

        The registry is the source of truth: identifying the issuer by CUIT (or name)
        keeps filing consistent across the many ways a supplier prints its invoices.
        No match leaves the invoice untouched, never guessing.
        """
        exclude = {buyer.cuit} if buyer.cuit else set()
        match = self._registry_provider().match(text, exclude_cuits=exclude)
        if match is None:
            return invoice
        return dataclasses.replace(invoice, supplier=match.razon_social)

    def _archive(
        self,
        source: Path,
        config: AppConfig,
        invoice: ParsedInvoice,
        base_folder: Path,
        outcome: ProcessOutcome,
        message: str,
    ) -> ProcessResult:
        target_dir = destination_dir(invoice, base_folder, config.destination_template)
        filename = build_filename(invoice)
        if config.dry_run:
            return _result(
                source,
                ProcessOutcome.DRY_RUN,
                target_dir / filename,
                invoice,
                "Simulacion: no se movio el archivo.",
                intended=outcome,
            )
        try:
            destination = _place(source, target_dir, filename, config)
        except Exception as exc:
            logger.exception("Fallo al archivar %s", source)
            return self._quarantine(source, config, f"No se pudo archivar: {exc}")
        return _result(source, outcome, destination, invoice, message)

    def _quarantine(self, source: Path, config: AppConfig, message: str) -> ProcessResult:
        # In dry-run mode or if the file is no longer there, nothing is moved.
        if config.dry_run or not source.exists():
            return _result(source, ProcessOutcome.ERROR, None, None, message)
        try:
            destination = _place(source, config.quarantine_folder, source.name, config)
        except Exception:
            logger.exception("No se pudo poner en cuarentena %s; queda en la carpeta de entrada para reintento", source)
            return _result(source, ProcessOutcome.ERROR, None, None, message)
        return _result(source, ProcessOutcome.QUARANTINED, destination, None, message)


def _destination_base(invoice: ParsedInvoice, buyer: BuyerResolution, config: AppConfig) -> Path:
    # Purchase orders live in their own area; invoices go under the buyer's folder.
    if invoice.document_type is DocumentType.ORDEN_COMPRA:
        return config.orders_base_for(buyer.cuit)
    return config.folder_for_cuit(buyer.cuit)


def _outcome_for(invoice: ParsedInvoice, buyer: BuyerResolution) -> tuple[ProcessOutcome, str]:
    if buyer.cuit is None:
        # Still archived (never lost), but flagged: the buying company is unknown.
        return ProcessOutcome.UNCLASSIFIED, "Archivado sin clasificar: no se detecto la sociedad compradora."
    if buyer.fuzzy:
        # Matched by name similarity, not by CUIT: recorded distinctly so it is auditable.
        return ProcessOutcome.MOVED, f"Archivado (sociedad emparejada por nombre, {round(buyer.score * 100)}%)."
    return ProcessOutcome.MOVED, "Archivado correctamente."


def _is_reliable(invoice: ParsedInvoice, config: AppConfig) -> bool:
    """Reliable if it has a number, the supplier was detected and it is not an own society.

    If the supplier was not detected (sentinel) it goes to review so it is not archived
    under a made-up name. If it matches a configured society, it is a sign that the buyer
    was read instead of the issuer: it also goes to review.
    """
    if not invoice.has_number or not invoice.has_supplier:
        return False
    return invoice.supplier.casefold() not in config.society_names()


def _place(source: Path, target_dir: Path, filename: str, config: AppConfig) -> Path:
    """Places the file at its destination: copy (leaves the original) or move, per the config."""
    if config.copy_files:
        return file_ops.copy_file(source, target_dir, filename)
    return file_ops.move_file(source, target_dir, filename)


def _result(
    source: Path,
    outcome: ProcessOutcome,
    destination: Path | None,
    invoice: ParsedInvoice | None,
    message: str,
    intended: ProcessOutcome | None = None,
) -> ProcessResult:
    return ProcessResult(
        source=source,
        outcome=outcome,
        destination=destination,
        invoice=invoice,
        message=message,
        intended=intended,
    )
