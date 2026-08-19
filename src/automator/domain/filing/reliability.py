"""Whether a document is complete enough to file without review."""

from __future__ import annotations

from collections.abc import Sequence

from automator.domain.buyer import SocietyLike
from automator.domain.models import ParsedInvoice
from automator.domain.names import normalize_name


def is_reliable(invoice: ParsedInvoice, societies: Sequence[SocietyLike]) -> bool:
    if not invoice.has_number or not invoice.has_supplier:
        return False
    return not _matches_own_society(invoice.supplier, societies)


def _matches_own_society(supplier: str, societies: Sequence[SocietyLike]) -> bool:
    key = normalize_name(supplier)
    return any(normalize_name(name) == key for society in societies for name in society.match_names())
