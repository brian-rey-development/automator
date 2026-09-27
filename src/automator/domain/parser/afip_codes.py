"""AFIP voucher codes and kind/letter detection."""

from __future__ import annotations

import re

from automator.domain.models import Voucher, VoucherKind

DEFAULT_LETTER = "A"
_CODE_PATTERN = re.compile(r"\bC[oó]d(?:igo)?\.?\s*(\d{1,3})(?!\d)", re.IGNORECASE)
_KIND_PATTERNS: tuple[tuple[re.Pattern[str], VoucherKind], ...] = (
    (re.compile(r"NOTA\s+DE\s+CR[EÉ]DITO", re.IGNORECASE), VoucherKind.CREDIT_NOTE),
    (re.compile(r"NOTA\s+DE\s+D[EÉ]BITO", re.IGNORECASE), VoucherKind.DEBIT_NOTE),
    (re.compile(r"FACTURA", re.IGNORECASE), VoucherKind.INVOICE),
)
_LETTER_PATTERN = re.compile(
    r"(?:FACTURA|NOTA\s+DE\s+\w+)\s*\n?\s*([ABCEM])\b",
    re.IGNORECASE,
)
AFIP_CODES: dict[str, tuple[VoucherKind, str]] = {
    "01": (VoucherKind.INVOICE, "A"),
    "02": (VoucherKind.DEBIT_NOTE, "A"),
    "03": (VoucherKind.CREDIT_NOTE, "A"),
    "06": (VoucherKind.INVOICE, "B"),
    "07": (VoucherKind.DEBIT_NOTE, "B"),
    "08": (VoucherKind.CREDIT_NOTE, "B"),
    "11": (VoucherKind.INVOICE, "C"),
    "12": (VoucherKind.DEBIT_NOTE, "C"),
    "13": (VoucherKind.CREDIT_NOTE, "C"),
    "19": (VoucherKind.INVOICE, "E"),
    "20": (VoucherKind.DEBIT_NOTE, "E"),
    "21": (VoucherKind.CREDIT_NOTE, "E"),
    "51": (VoucherKind.INVOICE, "M"),
    "52": (VoucherKind.DEBIT_NOTE, "M"),
    "53": (VoucherKind.CREDIT_NOTE, "M"),
    # Factura de Credito Electronica MiPyME (FCE): same kinds and letters.
    "201": (VoucherKind.INVOICE, "A"),
    "202": (VoucherKind.DEBIT_NOTE, "A"),
    "203": (VoucherKind.CREDIT_NOTE, "A"),
    "206": (VoucherKind.INVOICE, "B"),
    "207": (VoucherKind.DEBIT_NOTE, "B"),
    "208": (VoucherKind.CREDIT_NOTE, "B"),
    "211": (VoucherKind.INVOICE, "C"),
    "212": (VoucherKind.DEBIT_NOTE, "C"),
    "213": (VoucherKind.CREDIT_NOTE, "C"),
}


def detect_voucher(text: str) -> Voucher:
    by_code = _detect_by_afip_code(text)
    if by_code is not None:
        return by_code
    kind = _detect_kind(text) or VoucherKind.INVOICE
    letter = _detect_letter(text) or DEFAULT_LETTER
    return Voucher(kind, letter)


def voucher_for_code(code: int) -> Voucher | None:
    known = AFIP_CODES.get(f"{code:02d}")
    return Voucher(*known) if known is not None else None


def _detect_by_afip_code(text: str) -> Voucher | None:
    for match in _CODE_PATTERN.finditer(text):
        voucher = voucher_for_code(int(match.group(1)))
        if voucher is not None:
            return voucher
    return None


def _detect_kind(text: str) -> VoucherKind | None:
    for pattern, kind in _KIND_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def _detect_letter(text: str) -> str | None:
    match = _LETTER_PATTERN.search(text)
    return match.group(1).upper() if match else None
