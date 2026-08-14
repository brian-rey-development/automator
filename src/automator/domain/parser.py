"""Extraccion de datos de facturas AFIP a partir de texto plano.

Todas las funciones son puras y tolerantes a fallos: nunca lanzan excepciones
por texto inesperado, siempre devuelven el mejor resultado posible con valores
por defecto deterministas.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from automator.domain.models import UNKNOWN_SUPPLIER, ParsedInvoice, Voucher, VoucherKind

_DEFAULT_LETTER = "A"
_DEFAULT_SALES_POINT = "0000"
_DEFAULT_NUMBER = "00000000"

# El codigo AFIP de comprobante es la senal mas confiable del tipo y la letra.
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

# El `(?!\d)` evita capturar los primeros digitos de un numero mas largo (por
# ejemplo un CAE), que produciria un tipo de comprobante incorrecto.
_CODE_PATTERN = re.compile(r"\bC[oó]d(?:igo)?\.?\s*(\d{1,3})(?!\d)", re.IGNORECASE)

# Orden importante: las notas se detectan antes que "FACTURA".
_KIND_PATTERNS: tuple[tuple[re.Pattern[str], VoucherKind], ...] = (
    (re.compile(r"NOTA\s+DE\s+CR[EÉ]DITO", re.IGNORECASE), VoucherKind.CREDIT_NOTE),
    (re.compile(r"NOTA\s+DE\s+D[EÉ]BITO", re.IGNORECASE), VoucherKind.DEBIT_NOTE),
    (re.compile(r"FACTURA", re.IGNORECASE), VoucherKind.INVOICE),
)

_LETTER_PATTERN = re.compile(
    r"(?:FACTURA|NOTA\s+DE\s+\w+)\s*\n?\s*([ABCEM])\b",
    re.IGNORECASE,
)

# El layout real de AFIP muestra el punto de venta y el numero por separado, por
# eso ese patron tiene prioridad; el formato combinado "0000-00000000" es el respaldo.
_NUMBER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"Punto\s+de\s+Venta\s*:?\s*(\d{4,5}).{0,60}?"
        r"Comp\.?\s*N[roº°]*\.?\s*:?\s*(\d{1,8})",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"Comp\.?\s*N[roº°]*\.?\s*:?\s*(\d{4,5})\s*[-–]?\s*(\d{1,8})", re.IGNORECASE),  # noqa: RUF001
)

_SUPPLIER_PATTERN = re.compile(r"Raz[oó]n\s+Social\s*:?\s*(.+)", re.IGNORECASE)
_CUIT_SEPARATORS = re.compile(r"[\s.\-]")
_DATE_PATTERN = re.compile(r"Fecha\s+de\s+Emisi[oó]n\s*:?\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)


def parse_invoice(text: str, known_cuits: Iterable[str] = ()) -> ParsedInvoice:
    """Extrae los datos relevantes de una factura desde su texto."""
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


def _detect_date(text: str) -> date | None:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None  # Fecha con dia/mes fuera de rango: se ignora sin romper.


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
    for pattern in _NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).zfill(4), match.group(2).zfill(8)
    return _DEFAULT_SALES_POINT, _DEFAULT_NUMBER


def _detect_supplier(text: str) -> str:
    # Solo se confia en la razon social explicitamente etiquetada. Adivinar con la
    # primera linea (logo, "ORIGINAL", etc.) archivaria la factura bajo un nombre
    # inventado; ante la duda, se devuelve el centinela y se envia a revision.
    match = _SUPPLIER_PATTERN.search(text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return UNKNOWN_SUPPLIER


def _detect_cuit(text: str, known_cuits: Iterable[str]) -> tuple[str | None, bool]:
    """Devuelve (cuit_comprador, ambiguo).

    Si aparecen dos o mas sociedades propias (tipico en facturas entre empresas del
    mismo grupo) no se puede distinguir de forma confiable al comprador del emisor:
    se marca ambiguo para enviar a revision en lugar de adivinar y archivar mal.
    """
    # Se normaliza el texto quitando separadores para tolerar CUIT con guiones o puntos.
    normalized = _CUIT_SEPARATORS.sub("", text)
    present = [cuit for cuit in known_cuits if cuit and cuit in normalized]
    if not present:
        return None, False
    if len(present) > 1:
        return None, True
    return present[0], False
