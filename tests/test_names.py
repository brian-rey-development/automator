"""Tests for name normalization used by aliases and text matching."""

from __future__ import annotations

import pytest

from automator.domain.names import normalize_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Distribuidora Nórdica", "distribuidora nordica"),
        ("  COCA   COLA  SA ", "coca cola sa"),
        ("Té & Café S.R.L.", "te & cafe s.r.l."),
        ("MAYÚSCULAS", "mayusculas"),
    ],
)
def test_normalize_name_strips_accents_and_folds(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_normalize_name_of_empty_is_empty() -> None:
    assert normalize_name("   ") == ""
