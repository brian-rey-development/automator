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


def _pdf_with_qr(path: Path, payload: str, copies: int = 1) -> Path:
    import zxingcpp
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    qr = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode).to_image(scale=4)
    height, width = memoryview(qr).shape
    image = ImageReader(Image.frombytes("L", (width, height), bytes(memoryview(qr))))
    pdf = canvas.Canvas(str(path))
    for _ in range(copies):
        pdf.drawString(72, 750, "FACTURA")
        pdf.drawImage(image, 72, 500, width=120, height=120)
        pdf.showPage()
    pdf.save()
    return path


def test_reads_qr_from_embedded_image(tmp_path: Path) -> None:
    pdf_path = _pdf_with_qr(tmp_path / "qr.pdf", "https://www.afip.gob.ar/fe/qr/?p=abc")
    assert pdf_reader.read_qr_payloads(pdf_path) == ("https://www.afip.gob.ar/fe/qr/?p=abc",)


def test_reads_the_repeated_qr_of_a_duplicate_copy(tmp_path: Path) -> None:
    pdf_path = _pdf_with_qr(tmp_path / "qr.pdf", "https://www.afip.gob.ar/fe/qr/?p=abc", copies=2)
    assert len(pdf_reader.read_qr_payloads(pdf_path)) == 2


def test_qr_reader_never_raises_on_a_broken_pdf(pdf: Path) -> None:
    assert pdf_reader.read_qr_payloads(pdf) == ()
    assert pdf_reader.read_qr_payloads(pdf.parent / "no_existe.pdf") == ()
