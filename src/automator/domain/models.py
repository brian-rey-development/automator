"""Immutable models of the AFIP invoices domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

# Sentinel used when the supplier's legal name could not be detected.
UNKNOWN_SUPPLIER = "PROVEEDOR_DESCONOCIDO"


class VoucherKind(StrEnum):
    """Voucher type. The value is the label used in the file name."""

    INVOICE = "FC"  # Invoice
    CREDIT_NOTE = "NC"  # Credit note
    DEBIT_NOTE = "ND"  # Debit note


@dataclass(frozen=True, slots=True)
class Voucher:
    """Voucher identified by type and letter (for example FC A)."""

    kind: VoucherKind
    letter: str

    @property
    def label(self) -> str:
        return f"{self.kind.value} {self.letter}"


@dataclass(frozen=True, slots=True)
class ParsedInvoice:
    """Data extracted from an invoice, ready to be archived."""

    voucher: Voucher
    sales_point: str  # Point of sale (4 digits)
    number: str  # Voucher number (8 digits)
    supplier: str  # Supplier's legal name
    buyer_cuit: str | None  # CUIT of the detected buying company
    ambiguous_buyer: bool = False  # Several own companies appear: it cannot be decided
    issue_date: date | None = None  # Issue date, if it could be read

    @property
    def full_number(self) -> str:
        return f"{self.sales_point}-{self.number}"

    @property
    def has_number(self) -> bool:
        """True if a real voucher number could be extracted (not the filler one)."""
        return self.number != "00000000" or self.sales_point != "0000"

    @property
    def has_supplier(self) -> bool:
        """True if the supplier's legal name was detected (not the sentinel)."""
        return self.supplier != UNKNOWN_SUPPLIER

    @property
    def identity(self) -> str | None:
        """Stable invoice key to detect duplicates; None if not reliable."""
        if not self.has_number or not self.has_supplier:
            return None
        return f"{self.supplier.casefold()}|{self.full_number}|{self.voucher.label}"


class ProcessOutcome(StrEnum):
    """Possible outcome of processing a file."""

    MOVED = "moved"
    DRY_RUN = "dry_run"
    UNCLASSIFIED = "unclassified"  # Archived, but without being able to identify the buying company.
    DUPLICATE = "duplicate"  # An invoice with the same identity had already been archived.
    NEEDS_REVIEW = "needs_review"
    QUARANTINED = "quarantined"
    SKIPPED_MISSING = "skipped_missing"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Result of processing a single PDF."""

    source: Path
    outcome: ProcessOutcome
    destination: Path | None
    invoice: ParsedInvoice | None
    message: str

    @property
    def is_success(self) -> bool:
        return self.outcome in (ProcessOutcome.MOVED, ProcessOutcome.DRY_RUN)
