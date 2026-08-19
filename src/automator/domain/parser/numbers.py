"""Voucher number extraction from AFIP invoice text."""

from __future__ import annotations

import re

_DEFAULT_SALES_POINT = "0000"
_DEFAULT_NUMBER = "00000000"
_ANCHORED_NUMBER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"Punto\s+de\s+Venta\s*:?\s*(\d{4,5}).{0,80}?"
        r"Comp(?:robante)?\.?\s*N[roº°]*\.?\s*:?\s*(\d{1,8})",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"Comp(?:robante)?\.?\s*N[roº°]*\.?\s*:?\s*(\d{4,5})\s*[-–]?\s*(\d{1,8})",  # noqa: RUF001
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:N[uú]mero|Nro|N[º°])\s*:?\s*(\d{4,5})\s*[-–]\s*(\d{8})(?!-?\d)",  # noqa: RUF001
        re.IGNORECASE,
    ),
)
_SPLIT_POINT_OF_SALE = re.compile(r"Punto\s+de\s+venta\s*:?\s*(\d{4,5})", re.IGNORECASE)
_SPLIT_SEQUENCE = re.compile(r"C[oó]d\.?\s*\d{1,3}\s+(\d{8})(?!\d)", re.IGNORECASE)
_STANDALONE_NUMBER = re.compile(r"(?<![-\d])(\d{4,5})\s*[-–]\s*(\d{8})(?!-?\d)")  # noqa: RUF001


def detect_number(text: str) -> tuple[str, str]:
    for pattern in _ANCHORED_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).zfill(4), match.group(2).zfill(8)
    split = _detect_split_number(text)
    if split is not None:
        return split
    return _detect_standalone_number(text)


def default_number() -> tuple[str, str]:
    return _DEFAULT_SALES_POINT, _DEFAULT_NUMBER


def _detect_split_number(text: str) -> tuple[str, str] | None:
    point_of_sale = _SPLIT_POINT_OF_SALE.search(text)
    sequence = _SPLIT_SEQUENCE.search(text)
    if point_of_sale and sequence:
        return point_of_sale.group(1).zfill(4), sequence.group(1).zfill(8)
    return None


def _detect_standalone_number(text: str) -> tuple[str, str]:
    candidates = {(m.group(1).zfill(4), m.group(2).zfill(8)) for m in _STANDALONE_NUMBER.finditer(text)}
    if len(candidates) == 1:
        return next(iter(candidates))
    return default_number()
