"""Tests for file operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from automator.services import file_ops
from automator.services.file_ops import copy_file, is_pdf, move_file, unique_destination, wait_until_stable


def _force_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate Windows on macOS/Linux: win platform and paths treated as absolute.
    monkeypatch.setattr(file_ops.sys, "platform", "win32")
    monkeypatch.setattr(file_ops.os.path, "isabs", lambda _text: True)


def test_os_path_prefixes_long_local_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_windows(monkeypatch)
    assert file_ops._os_path(Path("C:\\dir\\f.pdf")) == "\\\\?\\C:\\dir\\f.pdf"


def test_os_path_uses_unc_form_for_network_share(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_windows(monkeypatch)
    # UNC requires \\?\UNC\servidor\recurso, not a raw prepended prefix.
    assert file_ops._os_path(Path("\\\\servidor\\recurso\\f.pdf")) == "\\\\?\\UNC\\servidor\\recurso\\f.pdf"


@pytest.mark.parametrize(
    ("name", "expected"),
    [("factura.pdf", True), ("FACTURA.PDF", True), ("Factura.Pdf", True), ("nota.txt", False), ("sinext", False)],
)
def test_is_pdf_is_case_insensitive(name: str, expected: bool) -> None:
    assert is_pdf(Path(name)) is expected


def test_unique_destination_returns_same_path_when_free(tmp_path: Path) -> None:
    target = tmp_path / "archivo.pdf"
    assert unique_destination(target) == target


def test_unique_destination_appends_counter_on_collision(tmp_path: Path) -> None:
    target = tmp_path / "archivo.pdf"
    target.write_text("uno")
    (tmp_path / "archivo (2).pdf").write_text("dos")
    assert unique_destination(target) == tmp_path / "archivo (3).pdf"


def test_move_file_creates_folders_and_moves(tmp_path: Path) -> None:
    source = tmp_path / "origen.pdf"
    source.write_text("contenido")
    destination = move_file(source, tmp_path / "sub" / "carpeta", "final.pdf")
    assert destination == tmp_path / "sub" / "carpeta" / "final.pdf"
    assert destination.exists()
    assert not source.exists()


def test_move_file_does_not_overwrite(tmp_path: Path) -> None:
    target_dir = tmp_path / "destino"
    target_dir.mkdir()
    (target_dir / "final.pdf").write_text("existente")
    source = tmp_path / "origen.pdf"
    source.write_text("nuevo")
    destination = move_file(source, target_dir, "final.pdf")
    assert destination == target_dir / "final (2).pdf"


def test_move_file_onto_itself_is_a_no_op(tmp_path: Path) -> None:
    # Reprocessing a review file lands it in the same folder with the same name:
    # it must stay put, never be renamed to a " (2)" duplicate of itself.
    source = tmp_path / "carpeta" / "factura.pdf"
    source.parent.mkdir()
    source.write_text("contenido")
    destination = move_file(source, tmp_path / "carpeta", "factura.pdf")
    assert destination == source
    assert source.exists()
    assert not (tmp_path / "carpeta" / "factura (2).pdf").exists()


def test_copy_file_keeps_source_and_creates_copy(tmp_path: Path) -> None:
    source = tmp_path / "origen.pdf"
    source.write_text("contenido")
    destination = copy_file(source, tmp_path / "sub" / "carpeta", "final.pdf")
    assert destination == tmp_path / "sub" / "carpeta" / "final.pdf"
    assert destination.read_text() == "contenido"
    assert source.exists()


def test_copy_file_does_not_overwrite(tmp_path: Path) -> None:
    target_dir = tmp_path / "destino"
    target_dir.mkdir()
    (target_dir / "final.pdf").write_text("existente")
    source = tmp_path / "origen.pdf"
    source.write_text("nuevo")
    destination = copy_file(source, target_dir, "final.pdf")
    assert destination == target_dir / "final (2).pdf"


def test_wait_until_stable_true_for_static_file(tmp_path: Path) -> None:
    path = tmp_path / "estable.pdf"
    path.write_bytes(b"datos")
    assert wait_until_stable(path, timeout_s=1.0, poll_interval_s=0.01) is True


def test_wait_until_stable_false_for_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "inexistente.pdf"
    assert wait_until_stable(path, timeout_s=0.05, poll_interval_s=0.01) is False
