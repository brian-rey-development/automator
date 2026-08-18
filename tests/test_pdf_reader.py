"""Tests for PDF text extraction: prefer layout mode, fall back to plain."""

from __future__ import annotations

from pathlib import Path

import pytest

from automator.services import pdf_reader


class _FakePage:
    def __init__(self, layout: str, plain: str, raise_on_layout: bool = False) -> None:
        self._layout = layout
        self._plain = plain
        self._raise_on_layout = raise_on_layout

    def extract_text(self, extraction_mode: str = "plain") -> str:
        if extraction_mode == "layout":
            if self._raise_on_layout:
                raise ValueError("layout not supported")
            return self._layout
        return self._plain


class _FakeReader:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-1.4")
    return path


def _patch(monkeypatch: pytest.MonkeyPatch, pages: list[_FakePage]) -> None:
    monkeypatch.setattr(pdf_reader, "PdfReader", lambda _stream: _FakeReader(pages))


def test_prefers_layout_text(pdf: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_FakePage("00002-00031708 LAYOUT", "0 0 0 0 2 broken plain")])
    assert pdf_reader.extract_text(pdf) == "00002-00031708 LAYOUT"


def test_falls_back_to_plain_when_layout_is_empty(pdf: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_FakePage("   \n  ", "Punto de venta: 0022 real plain text")])
    assert pdf_reader.extract_text(pdf) == "Punto de venta: 0022 real plain text"


def test_layout_failure_on_a_page_falls_back_to_plain(pdf: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [_FakePage("", "plain content", raise_on_layout=True)])
    assert pdf_reader.extract_text(pdf) == "plain content"
