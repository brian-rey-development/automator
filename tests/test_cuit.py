"""Tests for the shared CUIT utilities."""

from __future__ import annotations

import pytest

from automator.domain.cuit import CUIT_LENGTH, coerce_cuit, extract_cuits, is_valid_cuit, normalize_cuit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30-71234567-8", "30712345678"),
        ("30.712.345.678", "30712345678"),
        ("  30 712345678 ", "30712345678"),
        ("30712345678", "30712345678"),
    ],
)
def test_normalize_cuit_strips_non_digits(raw: str, expected: str) -> None:
    assert normalize_cuit(raw) == expected


def test_cuit_length_is_eleven() -> None:
    assert CUIT_LENGTH == 11


def test_is_valid_cuit_accepts_a_correct_check_digit() -> None:
    assert is_valid_cuit("30111111118") is True


def test_is_valid_cuit_rejects_a_wrong_check_digit() -> None:
    assert is_valid_cuit("30111111110") is False


def test_extract_cuits_finds_both_parties_normalized() -> None:
    text = "CUIT: 30-99999999-5\nCUIT: 30-11111111-8"
    assert extract_cuits(text) == {"30999999995", "30111111118"}


def test_extract_cuits_ignores_a_longer_number_that_contains_a_cuit() -> None:
    # A CAE is a long digit run; an 11-digit CUIT embedded in it must not match.
    assert extract_cuits("CAE 30111111118999") == set()


def test_coerce_cuit_keeps_a_full_valid_cuit_unchanged() -> None:
    assert coerce_cuit("30-11111111-8") == "30111111118"


@pytest.mark.parametrize(
    ("short", "recovered"),
    [
        ("2012345675", "20012345675"),  # DNI stored without one leading zero (10 digits)
        ("202345677", "20002345677"),  # DNI stored without two leading zeros (9 digits)
        ("30-2345672", "30002345672"),  # separators plus missing padding
    ],
)
def test_coerce_cuit_recovers_a_dni_missing_its_leading_zeros(short: str, recovered: str) -> None:
    result = coerce_cuit(short)
    assert result == recovered
    assert is_valid_cuit(result)


def test_coerce_cuit_leaves_an_unrecoverable_value_untouched() -> None:
    # Padding the body does not yield a valid check digit: it must not be invented.
    assert coerce_cuit("2012345670") == "2012345670"


def test_coerce_cuit_never_pads_an_empty_value() -> None:
    assert coerce_cuit("") == ""
