"""Persistent audit log backed by SQLite.

Every processed file is stored (what it was, where it went, when and with what
result). It backs three features: searchable history, duplicate detection and
undoing a move. Uses only the standard library.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from automator.domain.models import ProcessOutcome, ProcessResult

logger = logging.getLogger(__name__)

# Outcomes whose file can be returned to the input folder (they have a destination).
_UNDOABLE = (ProcessOutcome.MOVED, ProcessOutcome.UNCLASSIFIED, ProcessOutcome.DUPLICATE)
# Outcomes that count as "already archived" for detecting duplicates.
_ARCHIVED = (ProcessOutcome.MOVED, ProcessOutcome.UNCLASSIFIED)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source_name TEXT NOT NULL,
    identity TEXT,
    supplier TEXT,
    voucher TEXT,
    outcome TEXT NOT NULL,
    destination TEXT,
    message TEXT,
    reverted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_records_identity ON records(identity);
CREATE TABLE IF NOT EXISTS processed_sources (
    signature TEXT PRIMARY KEY,
    ts TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    """A history row, ready to display or undo."""

    id: int
    ts: str
    source_name: str
    identity: str | None
    supplier: str | None
    voucher: str | None
    outcome: ProcessOutcome
    destination: str | None
    message: str
    reverted: bool


class Ledger:
    """Thread-safe history: the worker writes and the interface reads."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            # WAL survives a crash mid-write far better than the default rollback
            # journal, and NORMAL avoids an fsync on every append (safe under WAL:
            # only the last transaction can be lost on an OS/power crash).
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def record(self, result: ProcessResult, timestamp: str | None = None) -> None:
        identity = result.invoice.identity if result.invoice else None
        supplier = result.invoice.supplier if result.invoice else None
        voucher = result.invoice.voucher.label if result.invoice else None
        destination = str(result.destination) if result.destination else None
        row = (
            timestamp or datetime.now().isoformat(timespec="seconds"),
            result.source.name,
            identity,
            supplier,
            voucher,
            result.outcome.value,
            destination,
            result.message,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO records"
                " (ts, source_name, identity, supplier, voucher, outcome, destination, message)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            self._conn.commit()

    def identity_exists(self, identity: str) -> bool:
        placeholders = ", ".join("?" for _ in _ARCHIVED)
        query = f"SELECT 1 FROM records WHERE identity = ? AND reverted = 0 AND outcome IN ({placeholders}) LIMIT 1"
        with self._lock:
            cursor = self._conn.execute(query, (identity, *(o.value for o in _ARCHIVED)))
            return cursor.fetchone() is not None

    def recent(self, limit: int = 200) -> list[LedgerRecord]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM records ORDER BY id DESC LIMIT ?", (limit,))
            return [_to_record(row) for row in cursor.fetchall()]

    def last_undoable(self) -> LedgerRecord | None:
        placeholders = ", ".join("?" for _ in _UNDOABLE)
        query = (
            f"SELECT * FROM records WHERE reverted = 0 AND destination IS NOT NULL"
            f" AND outcome IN ({placeholders}) ORDER BY id DESC LIMIT 1"
        )
        with self._lock:
            cursor = self._conn.execute(query, tuple(o.value for o in _UNDOABLE))
            row = cursor.fetchone()
        return _to_record(row) if row else None

    def mark_reverted(self, record_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE records SET reverted = 1 WHERE id = ?", (record_id,))
            self._conn.commit()

    def source_seen(self, signature: str) -> bool:
        """True if that source file was already processed (for copy mode)."""
        with self._lock:
            cursor = self._conn.execute("SELECT 1 FROM processed_sources WHERE signature = ? LIMIT 1", (signature,))
            return cursor.fetchone() is not None

    def mark_source_seen(self, signature: str, timestamp: str | None = None) -> None:
        """Remembers an already-processed source file, to avoid reprocessing it when copying."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO processed_sources (signature, ts) VALUES (?, ?)",
                (signature, timestamp or datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _to_record(row: sqlite3.Row) -> LedgerRecord:
    return LedgerRecord(
        id=row["id"],
        ts=row["ts"],
        source_name=row["source_name"],
        identity=row["identity"],
        supplier=row["supplier"],
        voucher=row["voucher"],
        outcome=ProcessOutcome(row["outcome"]),
        destination=row["destination"],
        message=row["message"],
        reverted=bool(row["reverted"]),
    )
