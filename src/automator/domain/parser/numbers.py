"""Voucher number extraction from AFIP invoice text."""

from __future__ import annotations

import re

_DEFAULT_SALES_POINT = "0000"
_DEFAULT_NUMBER = "00000000"
_COMP_NUMBER_LABEL = r"Comp(?:r(?:obante)?)?\.?\s*N[roº°]*\.?\s*[:;]?"
_ANCHORED_NUMBER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"Punto\s+de\s+Venta\s*:?\s*(\d{4,5}).{0,80}?" + _COMP_NUMBER_LABEL + r"\s*(\d{1,8})",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        _COMP_NUMBER_LABEL + r"\s*(\d{4,5})\s*[-–]?\s*(\d{1,8})",  # noqa: RUF001
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:N[uú]mero|Nro|N[º°])\s*:?\s*(\d{4,5})\s*[-–]\s*(\d{8})(?!-?\d)",  # noqa: RUF001
        re.IGNORECASE,
    ),
)
# "Factura  0009-8569": the title itself carries an unpadded number.
_TITLE_NUMBER = re.compile(r"\bFACTURA[ \t]+(\d{4,5})[ \t]*-[ \t]*(\d{1,8})(?![\d-])", re.IGNORECASE)
_SPLIT_POINT_OF_SALE = re.compile(r"Punto\s+de\s+venta\s*:?\s*(\d{4,5})", re.IGNORECASE)
_SPLIT_SEQUENCE = re.compile(r"C[oó]d\.?\s*\d{1,3}\s+(\d{8})(?!\d)", re.IGNORECASE)
_STANDALONE_NUMBER = re.compile(r"(?<![-\d])(\d{4,5})\s*[-–]\s*(\d{8})(?!-?\d)")  # noqa: RUF001
# Numbers of other documents share the voucher's shape: a delivery note ("Remito
# 0001-00069500"), the buyer's order ("ORD COMPRA NRO: 2026-00003684") or associated
# vouchers. A note also quotes the invoice it adjusts.
_REFERENCE_LABEL = re.compile(r"(?:Remito|Compra|Asociad)[^\d\n]{0,40}$", re.IGNORECASE)
_NOTE_REFERENCE_LABEL = re.compile(r"(?:Remito|Compra|Asociad|Factura)[^\d\n]{0,40}$", re.IGNORECASE)
_REFERENCE_LOOKBACK = 60


def detect_number(text: str, *, read_title: bool = True) -> tuple[str, str]:
    """Point of sale and number, or the filler default when not found unambiguously.

    `read_title` must be False for credit/debit notes: they quote the invoice they
    adjust ("Factura 0003-00001234"), which is never their own number.
    """
    reference = _REFERENCE_LABEL if read_title else _NOTE_REFERENCE_LABEL
    for pattern in _ANCHORED_NUMBER_PATTERNS:
        match = _first_own_match(pattern, text, reference)
        if match:
            return _padded(match)
    fallback = (_detect_title_number(text) if read_title else None) or _detect_split_number(text)
    return fallback or _detect_standalone_number(text, reference)


def default_number() -> tuple[str, str]:
    return _DEFAULT_SALES_POINT, _DEFAULT_NUMBER


def _first_own_match(pattern: re.Pattern[str], text: str, reference: re.Pattern[str]) -> re.Match[str] | None:
    return next((m for m in pattern.finditer(text) if not _is_reference(text, m.start(), reference)), None)


def _padded(match: re.Match[str]) -> tuple[str, str]:
    return match.group(1).zfill(4), match.group(2).zfill(8)


def _detect_title_number(text: str) -> tuple[str, str] | None:
    candidates = {_padded(match) for match in _TITLE_NUMBER.finditer(text)}
    return next(iter(candidates)) if len(candidates) == 1 else None


def _detect_split_number(text: str) -> tuple[str, str] | None:
    point_of_sale = _SPLIT_POINT_OF_SALE.search(text)
    sequence = _SPLIT_SEQUENCE.search(text)
    if point_of_sale and sequence:
        return point_of_sale.group(1).zfill(4), sequence.group(1).zfill(8)
    return None


def _detect_standalone_number(text: str, reference: re.Pattern[str]) -> tuple[str, str]:
    candidates = {
        _padded(match)
        for match in _STANDALONE_NUMBER.finditer(text)
        if not _is_reference(text, match.start(), reference)
    }
    if len(candidates) == 1:
        return next(iter(candidates))
    return default_number()


def _is_reference(text: str, start: int, reference: re.Pattern[str]) -> bool:
    preceding = text[max(0, start - _REFERENCE_LOOKBACK) : start]
    return reference.search(preceding) is not None
