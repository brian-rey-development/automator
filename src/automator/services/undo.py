"""Undo a filed invoice by moving it back to the input folder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from automator.services import file_ops
from automator.services.ledger import Ledger, LedgerRecord


class UndoOutcome(StrEnum):
    MOVED = "moved"
    MISSING = "missing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UndoResult:
    outcome: UndoOutcome
    filename: str
    error: str = ""


def perform_undo(record: LedgerRecord, input_folder: Path, ledger: Ledger) -> UndoResult:
    if record.destination is None:
        return UndoResult(UndoOutcome.FAILED, record.source_name, "Sin destino")
    source = Path(record.destination)
    if not source.exists():
        ledger.mark_reverted(record.id)
        return UndoResult(UndoOutcome.MISSING, source.name)
    return _move_back(source, input_folder, ledger, record.id)


def _move_back(source: Path, input_folder: Path, ledger: Ledger, record_id: int) -> UndoResult:
    try:
        file_ops.move_file(source, input_folder, source.name)
    except OSError as exc:
        return UndoResult(UndoOutcome.FAILED, source.name, str(exc))
    ledger.mark_reverted(record_id)
    return UndoResult(UndoOutcome.MOVED, source.name)
