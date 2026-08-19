"""Pure filing policy: review, duplicate, unclassified or move."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from automator.domain.buyer import BuyerResolution, SocietyLike
from automator.domain.filing.reliability import is_reliable
from automator.domain.models import DocumentType, ParsedInvoice, ProcessOutcome

_AMBIGUOUS = "Aparecen varias de tus sociedades: revisa cual es la compradora."
_INCOMPLETE = "Datos incompletos: se envio a revision manual."
_DUPLICATE = "Duplicado: ya se habia archivado este documento antes."
_UNCLASSIFIED = "Archivado sin clasificar: no se detecto la sociedad compradora."
_MOVED = "Archivado correctamente."
_FUZZY = "Emparejada por nombre ({percent}%): se envio a revision para confirmar la compradora."


@dataclass(frozen=True, slots=True)
class FilingFolders:
    review: Path
    duplicates: Path
    archive: Path


@dataclass(frozen=True, slots=True)
class FilingDecision:
    outcome: ProcessOutcome
    base_folder: Path
    message: str


def decide_filing(
    invoice: ParsedInvoice,
    buyer: BuyerResolution,
    *,
    societies: Sequence[SocietyLike],
    is_duplicate: bool,
    folders: FilingFolders,
) -> FilingDecision:
    if buyer.ambiguous:
        return FilingDecision(ProcessOutcome.NEEDS_REVIEW, folders.review, _AMBIGUOUS)
    if not is_reliable(invoice, societies):
        return FilingDecision(ProcessOutcome.NEEDS_REVIEW, folders.review, _INCOMPLETE)
    if is_duplicate:
        return FilingDecision(ProcessOutcome.DUPLICATE, folders.duplicates, _DUPLICATE)
    if buyer.fuzzy:
        message = _FUZZY.format(percent=round(buyer.score * 100))
        return FilingDecision(ProcessOutcome.NEEDS_REVIEW, folders.review, message)
    outcome, message = _archive_choice(buyer)
    return FilingDecision(outcome, folders.archive, message)


def _archive_choice(buyer: BuyerResolution) -> tuple[ProcessOutcome, str]:
    if buyer.cuit is None:
        return ProcessOutcome.UNCLASSIFIED, _UNCLASSIFIED
    return ProcessOutcome.MOVED, _MOVED


def archive_base(invoice: ParsedInvoice, buyer: BuyerResolution, invoices: Path, orders: Path) -> Path:
    if invoice.document_type is DocumentType.ORDEN_COMPRA:
        return orders
    return invoices
