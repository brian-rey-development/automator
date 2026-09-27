"""Small text helpers used while scanning AFIP PDF text."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from automator.domain.cuit import extract_cuits

_COLUMN_GAP = re.compile(r"\s{2,}")
# Only AFIP-authorized vouchers carry a 14-digit CAE (or CAEA); a purchase order never does.
_CAE_PATTERN = re.compile(r"\bC\.?A\.?E\.?A?\.?(?![A-Za-z])[^\d\n]{0,40}\d{14}(?!\d)", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"Fecha\s+de\s+Emisi[oó]n\s*:?\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)


def first_column(value: str) -> str:
    return _COLUMN_GAP.split(value, maxsplit=1)[0].strip()


def has_cae(text: str) -> bool:
    return _CAE_PATTERN.search(text) is not None


def detect_date(text: str) -> date | None:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def detect_buyer_cuit(text: str, known_cuits: Iterable[str]) -> tuple[str | None, bool]:
    found = extract_cuits(text)
    present = [cuit for cuit in known_cuits if cuit and cuit in found]
    if not present:
        return None, False
    if len(present) > 1:
        return None, True
    return present[0], False
