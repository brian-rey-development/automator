"""Shared CUIT helpers: normalization, AFIP check-digit validation and extraction.

Pure and fault-tolerant. Centralizes logic that config, the parser and the
supplier registry all rely on, so the rules for what counts as a CUIT live in a
single place.
"""

from __future__ import annotations

import re

CUIT_LENGTH = 11
_TYPE_LENGTH = 2  # Leading "type" block (20, 27, 30, ...); never zero-padded.
_BODY_LENGTH = 8  # DNI block, zero-padded to 8 in a canonical CUIT.
_MIN_RECOVERABLE = 9  # Below this, too many digits are missing to trust a rebuild.
_CHECK_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_NON_DIGITS = re.compile(r"\D")
_SEPARATORS = re.compile(r"[\s.\-]")
# A CUIT is 11 digits (2 + 8 + 1) with at most one optional separator between blocks.
# The digit boundaries (?<!\d)/(?!\d) stop it from matching inside a longer run (a CAE,
# two concatenated numbers), which would otherwise cause a false match and misfiling.
_CANDIDATE = re.compile(r"(?<!\d)\d{2}[\s.\-]?\d{8}[\s.\-]?\d(?!\d)")


def normalize_cuit(value: str) -> str:
    """Reduce a CUIT to its bare 11 digits, dropping any separators."""
    return _NON_DIGITS.sub("", value)


def coerce_cuit(value: str) -> str:
    """Recover a CUIT whose DNI block lost its leading zeros, when it is safe to.

    Some registries store the DNI without zero-padding, so the CUIT arrives with 9
    or 10 digits instead of 11. We rebuild it as type(2) + body zero-padded to 8 +
    check(1) and accept the result only if the AFIP check digit validates. An
    unrecoverable value is returned untouched so the caller still rejects it: this
    never invents a CUIT, it only restores padding a check digit can confirm.
    """
    digits = normalize_cuit(value)
    if len(digits) == CUIT_LENGTH or not (_MIN_RECOVERABLE <= len(digits) < CUIT_LENGTH):
        return digits
    rebuilt = digits[:_TYPE_LENGTH] + digits[_TYPE_LENGTH:-1].zfill(_BODY_LENGTH) + digits[-1]
    return rebuilt if is_valid_cuit(rebuilt) else digits


def is_valid_cuit(digits: str) -> bool:
    """Validate the CUIT check digit (AFIP modulo 11 algorithm)."""
    if len(digits) != CUIT_LENGTH or not digits.isdigit():
        return False
    total = sum(int(digit) * weight for digit, weight in zip(digits[:10], _CHECK_WEIGHTS, strict=True))
    expected = 11 - (total % 11)
    expected = 0 if expected == 11 else expected
    return expected != 10 and expected == int(digits[10])


def extract_cuits(text: str) -> set[str]:
    """Return the normalized 11-digit CUITs present in a text (no false substrings)."""
    return {_SEPARATORS.sub("", token) for token in _CANDIDATE.findall(text)}
