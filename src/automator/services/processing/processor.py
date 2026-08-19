"""Orchestration of processing a single invoice PDF."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path

from automator.config import AppConfig
from automator.domain.buyer import BuyerResolution, resolve_buyer
from automator.domain.filenames import build_filename
from automator.domain.filing import FilingDecision, FilingFolders, archive_base, decide_filing, destination_dir
from automator.domain.models import ParsedInvoice, ProcessOutcome, ProcessResult
from automator.domain.parser import parse_invoice
from automator.domain.suppliers import SupplierRegistry
from automator.services import file_ops
from automator.services.pdf_reader import extract_text
from automator.services.processing.placement import place_file

logger = logging.getLogger(__name__)

TextExtractor = Callable[[Path], str]
ConfigProvider = Callable[[], AppConfig]
DuplicateCheck = Callable[[ParsedInvoice], bool]
RegistryProvider = Callable[[], SupplierRegistry]

_EMPTY_REGISTRY = SupplierRegistry([])


def _never_duplicate(_invoice: ParsedInvoice) -> bool:
    return False


def empty_registry() -> SupplierRegistry:
    return _EMPTY_REGISTRY


class InvoiceProcessor:
    def __init__(
        self,
        config_provider: ConfigProvider,
        extractor: TextExtractor = extract_text,
        is_duplicate: DuplicateCheck = _never_duplicate,
        registry_provider: RegistryProvider = empty_registry,
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
        parsed = self._extract(source, config)
        if isinstance(parsed, ProcessResult):
            return parsed
        text, invoice = parsed
        buyer = resolve_buyer(invoice, list(config.societies))
        invoice = self._canonicalize_supplier(invoice, text, buyer)
        decision = self._decide(invoice, buyer, config)
        return self._archive(source, config, invoice, decision)

    def _decide(self, invoice: ParsedInvoice, buyer: BuyerResolution, config: AppConfig) -> FilingDecision:
        folders = FilingFolders(
            review=config.review_folder,
            duplicates=config.duplicates_folder,
            archive=archive_base(
                invoice, buyer, config.folder_for_cuit(buyer.cuit), config.orders_base_for(buyer.cuit)
            ),
        )
        return decide_filing(
            invoice,
            buyer,
            societies=config.societies,
            is_duplicate=self._is_duplicate(invoice),
            folders=folders,
        )

    def _extract(self, source: Path, config: AppConfig) -> tuple[str, ParsedInvoice] | ProcessResult:
        try:
            text = self._extractor(source)
        except Exception as exc:
            logger.exception("Fallo al leer el PDF %s", source)
            return self._quarantine(source, config, f"No se pudo leer el PDF: {exc}")
        if not text.strip():
            return self._quarantine(source, config, "El PDF no contiene texto legible (posible escaneo).")
        return text, parse_invoice(text, config.known_cuits())

    def _canonicalize_supplier(self, invoice: ParsedInvoice, text: str, buyer: BuyerResolution) -> ParsedInvoice:
        exclude = {buyer.cuit} if buyer.cuit else set()
        match = self._registry_provider().match(text, exclude_cuits=exclude)
        if match is None:
            return invoice
        return dataclasses.replace(invoice, supplier=match.razon_social)

    def _archive(
        self, source: Path, config: AppConfig, invoice: ParsedInvoice, decision: FilingDecision
    ) -> ProcessResult:
        target_dir = destination_dir(invoice, decision.base_folder, config.destination_template)
        filename = build_filename(invoice)
        if config.dry_run:
            return _result(
                source,
                ProcessOutcome.DRY_RUN,
                target_dir / filename,
                invoice,
                "Simulacion: no se movio el archivo.",
                intended=decision.outcome,
            )
        try:
            destination = place_file(source, target_dir, filename, copy_files=config.copy_files)
        except Exception as exc:
            logger.exception("Fallo al archivar %s", source)
            return self._quarantine(source, config, f"No se pudo archivar: {exc}")
        return _result(source, decision.outcome, destination, invoice, decision.message)

    def _quarantine(self, source: Path, config: AppConfig, message: str) -> ProcessResult:
        if config.dry_run or not source.exists():
            return _result(source, ProcessOutcome.ERROR, None, None, message)
        try:
            destination = place_file(source, config.quarantine_folder, source.name, copy_files=config.copy_files)
        except Exception:
            logger.exception("No se pudo poner en cuarentena %s; queda en la carpeta de entrada para reintento", source)
            return _result(source, ProcessOutcome.ERROR, None, None, message)
        return _result(source, ProcessOutcome.QUARANTINED, destination, None, message)


def _result(
    source: Path,
    outcome: ProcessOutcome,
    destination: Path | None,
    invoice: ParsedInvoice | None,
    message: str,
    intended: ProcessOutcome | None = None,
) -> ProcessResult:
    return ProcessResult(source, outcome, destination, invoice, message, intended)
