"""Extraction of AFIP invoice data from plain text.

All functions are pure and fault-tolerant: they never raise exceptions on
unexpected text, always returning the best possible result with deterministic
default values.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from automator.domain.cuit import extract_cuits
from automator.domain.models import UNKNOWN_SUPPLIER, DocumentType, ParsedInvoice, Voucher, VoucherKind

_DEFAULT_LETTER = "A"
_DEFAULT_SALES_POINT = "0000"
_DEFAULT_NUMBER = "00000000"

# The AFIP voucher code is the most reliable signal of the type and letter.
_AFIP_CODES: dict[str, tuple[VoucherKind, str]] = {
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
}

# The `(?!\d)` avoids capturing the first digits of a longer number (for
# example a CAE), which would produce an incorrect voucher type.
_CODE_PATTERN = re.compile(r"\bC[oó]d(?:igo)?\.?\s*(\d{1,3})(?!\d)", re.IGNORECASE)

# Order matters: notes are detected before "FACTURA".
_KIND_PATTERNS: tuple[tuple[re.Pattern[str], VoucherKind], ...] = (
    (re.compile(r"NOTA\s+DE\s+CR[EÉ]DITO", re.IGNORECASE), VoucherKind.CREDIT_NOTE),
    (re.compile(r"NOTA\s+DE\s+D[EÉ]BITO", re.IGNORECASE), VoucherKind.DEBIT_NOTE),
    (re.compile(r"FACTURA", re.IGNORECASE), VoucherKind.INVOICE),
)

_LETTER_PATTERN = re.compile(
    r"(?:FACTURA|NOTA\s+DE\s+\w+)\s*\n?\s*([ABCEM])\b",
    re.IGNORECASE,
)

# AFIP numbers are a 4-5 digit point of sale plus an 8-digit sequence. Suppliers print
# them in many ways, so patterns are tried in order of confidence: the anchored ones
# (tied to a label) win before the guarded standalone fallback. "Comp(robante)?" covers
# both the "Comp." abbreviation and the full word "Comprobante".
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
    # Inline label ("Numero", "Nro", "Nº/N°", also inside "FACTURA A Nº") with the point
    # of sale, a dash and the 8-digit sequence. The trailing guard rejects an IIBB or
    # CUIT check digit (e.g. "90230-69746598-3"); requiring 8 digits rejects phones.
    re.compile(
        r"(?:N[uú]mero|Nro|N[º°])\s*:?\s*(\d{4,5})\s*[-–]\s*(\d{8})(?!-?\d)",  # noqa: RUF001
        re.IGNORECASE,
    ),
)

# Point of sale and sequence in separate cells: the point of sale after its label and
# the sequence after a "Cod. NN" line.
_SPLIT_POINT_OF_SALE = re.compile(r"Punto\s+de\s+venta\s*:?\s*(\d{4,5})", re.IGNORECASE)
_SPLIT_SEQUENCE = re.compile(r"C[oó]d\.?\s*\d{1,3}\s+(\d{8})(?!\d)", re.IGNORECASE)

# Last resort: a bare point-of-sale-dash-8-digit number with no label. The lookbehind
# rejects an order number ("N-2026-..."), the lookahead an IIBB/CUIT check digit. Only
# accepted when a single distinct candidate exists: two or more mean "do not guess".
_STANDALONE_NUMBER = re.compile(r"(?<![-\d])(\d{4,5})\s*[-–]\s*(\d{8})(?!-?\d)")  # noqa: RUF001

# Purchase order (Orden de Compra). "ORD COMPRA", "ORDEN COMPRA", "ORDEN DE COMPRA".
_ORDER_PATTERN = re.compile(r"\bORD(?:EN)?\.?\s+(?:DE\s+)?COMPRA\b", re.IGNORECASE)
# The OC number is printed as year-sequence, e.g. "ORD COMPRA NRO: 2026-00004046".
_ORDER_NUMBER_PATTERN = re.compile(
    r"ORD(?:EN)?\.?\s+(?:DE\s+)?COMPRA\s+N[roº°]*\.?\s*:?\s*(\d{4})\s*-\s*(\d+)",
    re.IGNORECASE,
)
_PROVEEDOR_PATTERN = re.compile(r"Proveedor\s*:?\s*(.+)", re.IGNORECASE)
_SOCIEDAD_PATTERN = re.compile(r"Sociedad\s*:?\s*(.+)", re.IGNORECASE)

# A run of two or more spaces separates columns in layout-extracted text.
_COLUMN_GAP = re.compile(r"\s{2,}")
_SUPPLIER_PATTERN = re.compile(r"Raz[oó]n\s+Social\s*:?\s*(.+)", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"Fecha\s+de\s+Emisi[oó]n\s*:?\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)


def parse_invoice(text: str, known_cuits: Iterable[str] = ()) -> ParsedInvoice:
    """Extract the relevant data of a document (invoice or purchase order)."""
    if _ORDER_PATTERN.search(text):
        return _parse_order(text, known_cuits)
    return _parse_factura(text, known_cuits)


def _parse_factura(text: str, known_cuits: Iterable[str]) -> ParsedInvoice:
    sales_point, number = _detect_number(text)
    buyer_cuit, ambiguous = _detect_cuit(text, known_cuits)
    return ParsedInvoice(
        voucher=_detect_voucher(text),
        sales_point=sales_point,
        number=number,
        supplier=_detect_supplier(text),
        buyer_cuit=buyer_cuit,
        ambiguous_buyer=ambiguous,
        issue_date=_detect_date(text),
    )


def _parse_order(text: str, known_cuits: Iterable[str]) -> ParsedInvoice:
    sales_point, number = _detect_order_number(text)
    buyer_cuit, ambiguous = _detect_cuit(text, known_cuits)
    return ParsedInvoice(
        # A purchase order has no fiscal voucher; type_label reports "OC" regardless.
        voucher=Voucher(VoucherKind.INVOICE, _DEFAULT_LETTER),
        sales_point=sales_point,
        number=number,
        supplier=_detect_order_supplier(text),
        buyer_cuit=buyer_cuit,
        ambiguous_buyer=ambiguous,
        issue_date=_detect_date(text),
        document_type=DocumentType.ORDEN_COMPRA,
        buyer_name=_detect_buyer_name(text),
    )


def _detect_order_number(text: str) -> tuple[str, str]:
    match = _ORDER_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1).zfill(4), match.group(2).zfill(8)
    return _DEFAULT_SALES_POINT, _DEFAULT_NUMBER


def _detect_order_supplier(text: str) -> str:
    # A purchase order labels the supplier as "Proveedor:" (not "Razon Social:").
    match = _PROVEEDOR_PATTERN.search(text)
    if match and _first_column(match.group(1)):
        return _first_column(match.group(1))
    return UNKNOWN_SUPPLIER


def _detect_buyer_name(text: str) -> str | None:
    # The buying company is printed as "Sociedad:"; kept for fuzzy society matching.
    match = _SOCIEDAD_PATTERN.search(text)
    return _first_column(match.group(1)) or None if match else None


def _detect_date(text: str) -> date | None:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None  # Date with day/month out of range: ignored without breaking.


def _detect_voucher(text: str) -> Voucher:
    by_code = _detect_by_afip_code(text)
    if by_code is not None:
        return by_code
    kind = _detect_kind(text) or VoucherKind.INVOICE
    letter = _detect_letter(text) or _DEFAULT_LETTER
    return Voucher(kind, letter)


def _detect_by_afip_code(text: str) -> Voucher | None:
    for match in _CODE_PATTERN.finditer(text):
        code = f"{int(match.group(1)):02d}"
        if code in _AFIP_CODES:
            kind, letter = _AFIP_CODES[code]
            return Voucher(kind, letter)
    return None


def _detect_kind(text: str) -> VoucherKind | None:
    for pattern, kind in _KIND_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def _detect_letter(text: str) -> str | None:
    match = _LETTER_PATTERN.search(text)
    return match.group(1).upper() if match else None


def _detect_number(text: str) -> tuple[str, str]:
    for pattern in _ANCHORED_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).zfill(4), match.group(2).zfill(8)
    split = _detect_split_number(text)
    if split is not None:
        return split
    return _detect_standalone_number(text)


def _detect_split_number(text: str) -> tuple[str, str] | None:
    point_of_sale = _SPLIT_POINT_OF_SALE.search(text)
    sequence = _SPLIT_SEQUENCE.search(text)
    if point_of_sale and sequence:
        return point_of_sale.group(1).zfill(4), sequence.group(1).zfill(8)
    return None


def _detect_standalone_number(text: str) -> tuple[str, str]:
    # Only trust a bare number when it is unique: two or more candidates are ambiguous
    # and the invoice must go to review rather than be filed under a guessed number.
    candidates = {(m.group(1).zfill(4), m.group(2).zfill(8)) for m in _STANDALONE_NUMBER.finditer(text)}
    if len(candidates) == 1:
        return next(iter(candidates))
    return _DEFAULT_SALES_POINT, _DEFAULT_NUMBER


def _detect_supplier(text: str) -> str:
    # Only the explicitly labeled legal name is trusted. Guessing from the
    # first line (logo, "ORIGINAL", etc.) would archive the invoice under a made-up
    # name; when in doubt, the sentinel is returned and it is sent to review.
    match = _SUPPLIER_PATTERN.search(text)
    if match and _first_column(match.group(1)):
        return _first_column(match.group(1))
    return UNKNOWN_SUPPLIER


def _first_column(value: str) -> str:
    # Layout extraction can append a neighbouring column on the same line (separated by
    # a run of spaces). Keep only the first column so a label does not swallow the next.
    return _COLUMN_GAP.split(value, maxsplit=1)[0].strip()


def _detect_cuit(text: str, known_cuits: Iterable[str]) -> tuple[str | None, bool]:
    """Return (buyer_cuit, ambiguous).

    If two or more own companies appear (typical in invoices between companies of
    the same group) the buyer cannot be reliably distinguished from the issuer:
    it is marked ambiguous to send to review instead of guessing and archiving wrong.
    """
    found = extract_cuits(text)
    present = [cuit for cuit in known_cuits if cuit and cuit in found]
    if not present:
        return None, False
    if len(present) > 1:
        return None, True
    return present[0], False
