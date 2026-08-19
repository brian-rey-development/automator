"""Undo a filed invoice by moving it back to the input folder."""

from __future__ import annotations

import sqlite3
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
    if not file_ops.path_exists(source):
        ledger.mark_reverted(record.id)
        return UndoResult(UndoOutcome.MISSING, source.name)
    return _move_back(source, input_folder, ledger, record.id)


def _move_back(source: Path, input_folder: Path, ledger: Ledger, record_id: int) -> UndoResult:
    try:
        placed = file_ops.move_file(source, input_folder, source.name)
    except OSError as exc:
        return UndoResult(UndoOutcome.FAILED, source.name, str(exc))
    return _mark_or_restore(placed, source, ledger, record_id)


def _mark_or_restore(placed: Path, original: Path, ledger: Ledger, record_id: int) -> UndoResult:
    try:
        ledger.mark_reverted(record_id)
    except (OSError, sqlite3.Error) as exc:
        restored = _restore(placed, original)
        return UndoResult(UndoOutcome.FAILED, restored.name, str(exc))
    return UndoResult(UndoOutcome.MOVED, placed.name)


def _restore(placed: Path, original: Path) -> Path:
    try:
        return file_ops.move_file(placed, original.parent, original.name)
    except OSError:
        return placed
