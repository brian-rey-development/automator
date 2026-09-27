"""Whether a document is complete enough to file without review."""

from __future__ import annotations

import re
from collections.abc import Sequence

from automator.domain.buyer import SocietyLike
from automator.domain.models import ParsedInvoice
from automator.domain.names import normalize_name

_NON_ALPHANUMERIC = re.compile(r"[^0-9a-z]")
_MIN_CONTAINED_NAME = 8


def is_reliable(invoice: ParsedInvoice, societies: Sequence[SocietyLike]) -> bool:
    if not invoice.has_number or not invoice.has_supplier:
        return False
    return not _matches_own_society(invoice.supplier, societies)


def _matches_own_society(supplier: str, societies: Sequence[SocietyLike]) -> bool:
    key = _compact(supplier)
    return any(_is_own_name(_compact(name), key) for society in societies for name in society.match_names())


def _is_own_name(own: str, supplier: str) -> bool:
    # "Razon Social: 6727-CUENCA DEL SALADO S.A." is the buyer block read as the supplier.
    # Containment only for names long enough not to hit unrelated suppliers by chance.
    if len(own) < _MIN_CONTAINED_NAME:
        return own == supplier
    return own in supplier


def _compact(name: str) -> str:
    return _NON_ALPHANUMERIC.sub("", normalize_name(name))
