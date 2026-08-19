"""Undo service tests. No display required."""

from __future__ import annotations

from pathlib import Path

import pytest

from automator.domain.models import ProcessOutcome, ProcessResult
from automator.services import file_ops
from automator.services.ledger import Ledger, LedgerRecord
from automator.services.undo import UndoOutcome, perform_undo


def _moved(destination: Path) -> ProcessResult:
    return ProcessResult(
        source=Path("descarga.pdf"),
        outcome=ProcessOutcome.MOVED,
        destination=destination,
        invoice=None,
        message="ok",
    )


def _record(*, destination: str | None) -> LedgerRecord:
    return LedgerRecord(
        id=1,
        ts="2026-08-14T10:00:00",
        source_name="factura.pdf",
        identity=None,
        supplier=None,
        voucher=None,
        outcome=ProcessOutcome.MOVED,
        destination=destination,
        message="ok",
        reverted=False,
    )


def test_perform_undo_moves_file_back_and_marks_reverted(tmp_path: Path) -> None:
    inbox = tmp_path / "entrada"
    inbox.mkdir()
    archived = tmp_path / "salida" / "factura.pdf"
    archived.parent.mkdir()
    archived.write_bytes(b"%PDF")
    ledger = Ledger(tmp_path / "history.db")
    ledger.record(_moved(archived))
    record = ledger.last_undoable()
    assert record is not None

    result = perform_undo(record, inbox, ledger)

    assert result.outcome is UndoOutcome.MOVED
    assert result.filename == "factura.pdf"
    assert (inbox / "factura.pdf").exists()
    assert not archived.exists()
    assert ledger.last_undoable() is None
    ledger.close()


def test_perform_undo_marks_missing_file_reverted(tmp_path: Path) -> None:
    inbox = tmp_path / "entrada"
    inbox.mkdir()
    missing = tmp_path / "salida" / "perdida.pdf"
    ledger = Ledger(tmp_path / "history.db")
    ledger.record(_moved(missing))
    record = ledger.last_undoable()
    assert record is not None

    result = perform_undo(record, inbox, ledger)

    assert result.outcome is UndoOutcome.MISSING
    assert result.filename == "perdida.pdf"
    assert ledger.last_undoable() is None
    ledger.close()


def test_perform_undo_failed_move_does_not_mark_reverted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inbox = tmp_path / "entrada"
    inbox.mkdir()
    archived = tmp_path / "salida" / "factura.pdf"
    archived.parent.mkdir()
    archived.write_bytes(b"%PDF")
    ledger = Ledger(tmp_path / "history.db")
    ledger.record(_moved(archived))
    record = ledger.last_undoable()
    assert record is not None
    monkeypatch.setattr(file_ops, "move_file", _raise_os_error)

    result = perform_undo(record, inbox, ledger)

    assert result.outcome is UndoOutcome.FAILED
    assert archived.exists()
    assert ledger.last_undoable() is not None
    ledger.close()


def test_perform_undo_without_destination_does_not_touch_ledger(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "history.db")
    result = perform_undo(_record(destination=None), tmp_path / "entrada", ledger)
    assert result.outcome is UndoOutcome.FAILED
    assert result.error == "Sin destino"
    assert ledger.recent() == []
    ledger.close()


def _raise_os_error(*_args: object, **_kwargs: object) -> Path:
    raise OSError("disk full")
