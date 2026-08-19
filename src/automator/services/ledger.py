"""Persistent audit log backed by SQLite."""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from automator.domain.models import FILED_OUTCOMES, UNDOABLE_OUTCOMES, ProcessOutcome, ProcessResult
from automator.services.file_ops import file_signature, path_exists
from automator.services.persistence.migrations import apply_migrations
from automator.services.persistence.sqlite import connect_wal

logger = logging.getLogger(__name__)

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
    def __init__(self, path: Path) -> None:
        self._conn = connect_wal(path)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            apply_migrations(self._conn)
            self._conn.commit()

    def record(self, result: ProcessResult, timestamp: str | None = None) -> None:
        invoice = result.invoice
        row = (
            timestamp or datetime.now().isoformat(timespec="seconds"),
            result.source.name,
            invoice.identity if invoice else None,
            invoice.supplier if invoice else None,
            invoice.type_label if invoice else None,
            result.outcome.value,
            str(result.destination) if result.destination else None,
            result.message,
            invoice.issuer_cuit if invoice else None,
            invoice.issuer_identity if invoice else None,
            file_signature(result.source),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO records (ts, source_name, identity, supplier, voucher, outcome,"
                " destination, message, issuer_cuit, issuer_identity, source_signature)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            self._conn.commit()

    def archived_destination(self, identity: str, issuer_cuit: str | None = None) -> str | None:
        clauses = ["identity = ?"]
        params: list[object] = [*(o.value for o in FILED_OUTCOMES), identity]
        if issuer_cuit:
            suffix = _identity_suffix(identity)
            if suffix:
                clauses.append("issuer_identity = ?")
                params.append(f"{issuer_cuit}|{suffix}")
        in_list = ", ".join("?" for _ in FILED_OUTCOMES)
        query = (
            f"SELECT destination FROM records WHERE reverted = 0 AND destination IS NOT NULL"
            f" AND outcome IN ({in_list}) AND ({' OR '.join(clauses)}) ORDER BY id DESC LIMIT 1"
        )
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return row["destination"] if row else None

    def recent(self, limit: int = 200) -> list[LedgerRecord]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM records ORDER BY id DESC LIMIT ?", (limit,))
            return [_to_record(row) for row in cursor.fetchall()]

    def last_undoable(self) -> LedgerRecord | None:
        in_list = ", ".join("?" for _ in UNDOABLE_OUTCOMES)
        query = (
            f"SELECT * FROM records WHERE reverted = 0 AND destination IS NOT NULL"
            f" AND outcome IN ({in_list}) ORDER BY id DESC LIMIT 1"
        )
        with self._lock:
            row = self._conn.execute(query, tuple(o.value for o in UNDOABLE_OUTCOMES)).fetchone()
        return _to_record(row) if row else None

    def mark_reverted(self, record_id: int) -> None:
        with self._lock:
            row = self._conn.execute("SELECT source_signature FROM records WHERE id = ?", (record_id,)).fetchone()
            self._conn.execute("UPDATE records SET reverted = 1 WHERE id = ?", (record_id,))
            signature = row["source_signature"] if row else None
            if signature:
                self._conn.execute("DELETE FROM processed_sources WHERE signature = ?", (signature,))
            self._conn.commit()

    def source_seen(self, signature: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT destination FROM records WHERE source_signature = ? AND reverted = 0 ORDER BY id DESC LIMIT 1",
                (signature,),
            ).fetchone()
        if row is not None:
            destination = row["destination"]
            return destination is not None and path_exists(Path(destination))
        return self._legacy_source_seen(signature)

    def mark_source_seen(self, signature: str, timestamp: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO processed_sources (signature, ts) VALUES (?, ?)",
                (signature, timestamp or datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()

    def forget_source(self, signature: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM processed_sources WHERE signature = ?", (signature,))
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM records")
            self._conn.execute("DELETE FROM processed_sources")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _legacy_source_seen(self, signature: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("SELECT 1 FROM processed_sources WHERE signature = ? LIMIT 1", (signature,))
            return cursor.fetchone() is not None


_IDENTITY_PARTS = 3


def _identity_suffix(identity: str) -> str | None:
    parts = identity.rsplit("|", 2)
    if len(parts) != _IDENTITY_PARTS:
        return None
    return f"{parts[1]}|{parts[2]}"


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
