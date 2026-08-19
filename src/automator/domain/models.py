"""Immutable models of the AFIP invoices domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from automator.domain.names import normalize_name

UNKNOWN_SUPPLIER = "PROVEEDOR_DESCONOCIDO"
_ORDER_LABEL = "OC"
_FILLER_SALES_POINT = "0000"
_FILLER_NUMBER = "00000000"


class DocumentType(StrEnum):
    FACTURA = "factura"
    ORDEN_COMPRA = "orden_compra"


class VoucherKind(StrEnum):
    INVOICE = "FC"
    CREDIT_NOTE = "NC"
    DEBIT_NOTE = "ND"


@dataclass(frozen=True, slots=True)
class Voucher:
    kind: VoucherKind
    letter: str

    @property
    def label(self) -> str:
        return f"{self.kind.value} {self.letter}"


@dataclass(frozen=True, slots=True)
class ParsedInvoice:
    voucher: Voucher
    sales_point: str
    number: str
    supplier: str
    buyer_cuit: str | None
    ambiguous_buyer: bool = False
    issue_date: date | None = None
    document_type: DocumentType = DocumentType.FACTURA
    buyer_name: str | None = None
    issuer_cuit: str | None = None

    @property
    def type_label(self) -> str:
        if self.document_type is DocumentType.ORDEN_COMPRA:
            return _ORDER_LABEL
        return self.voucher.label

    @property
    def full_number(self) -> str:
        return f"{self.sales_point}-{self.number}"

    @property
    def has_number(self) -> bool:
        return self.number != _FILLER_NUMBER or self.sales_point != _FILLER_SALES_POINT

    @property
    def has_supplier(self) -> bool:
        return self.supplier != UNKNOWN_SUPPLIER

    @property
    def identity(self) -> str | None:
        if not self.has_number or not self.has_supplier:
            return None
        return f"{normalize_name(self.supplier)}|{self.full_number}|{self.type_label}"

    @property
    def issuer_identity(self) -> str | None:
        if not self.has_number or not self.issuer_cuit:
            return None
        return f"{self.issuer_cuit}|{self.full_number}|{self.type_label}"


class ProcessOutcome(StrEnum):
    MOVED = "moved"
    DRY_RUN = "dry_run"
    UNCLASSIFIED = "unclassified"
    DUPLICATE = "duplicate"
    NEEDS_REVIEW = "needs_review"
    QUARANTINED = "quarantined"
    SKIPPED_MISSING = "skipped_missing"
    ERROR = "error"


FILED_OUTCOMES = (ProcessOutcome.MOVED, ProcessOutcome.UNCLASSIFIED)
SESSION_ARCHIVED = (ProcessOutcome.MOVED, ProcessOutcome.DRY_RUN)
UNDOABLE_OUTCOMES = (
    ProcessOutcome.MOVED,
    ProcessOutcome.UNCLASSIFIED,
    ProcessOutcome.DUPLICATE,
    ProcessOutcome.NEEDS_REVIEW,
    ProcessOutcome.QUARANTINED,
)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    source: Path
    outcome: ProcessOutcome
    destination: Path | None
    invoice: ParsedInvoice | None
    message: str
    intended: ProcessOutcome | None = None

    @property
    def counted_outcome(self) -> ProcessOutcome:
        return self.outcome if self.intended is None else self.intended
