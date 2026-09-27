"""Decoding of the AFIP/ARCA QR printed on every electronic voucher (RG 4892/2020).

The QR is a URL whose `p` parameter is base64-encoded JSON with the issuer CUIT,
point of sale, number, voucher code and receiver document. Unlike the printed text,
it is machine-generated and survives pre-printed forms whose header is an image, so
it is the authoritative source when present. Pure and never raises.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, urlsplit

from automator.domain.cuit import is_valid_cuit
from automator.domain.models import Voucher
from automator.domain.parser.afip_codes import voucher_for_code

_AFIP_HOSTS = ("afip.gob.ar", "arca.gob.ar")
_PAYLOAD_PARAM = "p"
_CUIT_DOCUMENT_TYPE = 80
_MAX_SALES_POINT = 99_999
_MAX_NUMBER = 99_999_999
_MAX_CODE = 999
_BYTE_ORDER_MARK = "\ufeff"


@dataclass(frozen=True, slots=True)
class AfipQr:
    issuer_cuit: str
    sales_point: int
    number: int
    voucher: Voucher | None
    receiver_cuit: str | None
    issue_date: date | None


def unique_afip_qr(payloads: Iterable[str]) -> AfipQr | None:
    """The single voucher the QRs describe; None when there is none or several differ."""
    decoded = {qr for qr in map(parse_afip_qr, payloads) if qr is not None}
    return next(iter(decoded)) if len(decoded) == 1 else None


def parse_afip_qr(payload: str) -> AfipQr | None:
    data = _decode_payload(payload)
    if data is None:
        return None
    issuer = _cuit(data.get("cuit"))
    sales_point = _bounded_int(data.get("ptovta"), _MAX_SALES_POINT)
    number = _bounded_int(data.get("nrocmp"), _MAX_NUMBER)
    if issuer is None or sales_point is None or number is None:
        return None
    return AfipQr(
        issuer_cuit=issuer,
        sales_point=sales_point,
        number=number,
        voucher=_voucher(data.get("tipocmp")),
        receiver_cuit=_receiver_cuit(data),
        issue_date=_iso_date(data.get("fecha")),
    )


def _decode_payload(payload: str) -> Mapping[str, object] | None:
    url = urlsplit(payload.strip().lstrip(_BYTE_ORDER_MARK))
    host = (url.hostname or "").casefold()
    if not any(host == known or host.endswith(f".{known}") for known in _AFIP_HOSTS):
        return None
    encoded = parse_qs(url.query).get(_PAYLOAD_PARAM, [""])[0]
    try:
        raw = json.loads(_b64decode(encoded))
    except (binascii.Error, ValueError):
        return None
    # Issuers disagree on key casing ("tipoCodAut" vs "tipocodAut", "ctz" vs "CTZ").
    return {str(key).casefold(): value for key, value in raw.items()} if isinstance(raw, dict) else None


def _b64decode(encoded: str) -> bytes:
    # parse_qs turns an unescaped "+" into a space; padding is often dropped.
    cleaned = encoded.replace(" ", "+")
    return base64.b64decode(cleaned + "=" * (-len(cleaned) % 4), altchars=b"-_" if _is_urlsafe(cleaned) else None)


def _is_urlsafe(encoded: str) -> bool:
    return "-" in encoded or "_" in encoded


def _bounded_int(value: object, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if 1 <= number <= maximum else None


def _cuit(value: object) -> str | None:
    digits = str(value) if isinstance(value, int | str) and not isinstance(value, bool) else ""
    return digits if is_valid_cuit(digits) else None


def _receiver_cuit(data: Mapping[str, object]) -> str | None:
    if _bounded_int(data.get("tipodocrec"), _MAX_CODE) != _CUIT_DOCUMENT_TYPE:
        return None
    return _cuit(data.get("nrodocrec"))


def _voucher(value: object) -> Voucher | None:
    code = _bounded_int(value, _MAX_CODE)
    return voucher_for_code(code) if code is not None else None


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
