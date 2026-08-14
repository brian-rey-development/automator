"""Registro de auditoria persistente en SQLite.

Cada archivo procesado queda guardado (que era, a donde fue, cuando y con que
resultado). Es la base de tres funciones: historial buscable, deteccion de
duplicados y deshacer un movimiento. Usa solo la biblioteca estandar.
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

# Resultados cuyo archivo se puede devolver a la carpeta de entrada (tienen destino).
_UNDOABLE = (ProcessOutcome.MOVED, ProcessOutcome.UNCLASSIFIED, ProcessOutcome.DUPLICATE)
# Resultados que cuentan como "ya archivada" para detectar duplicados.
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
    """Una fila del historial, lista para mostrar o deshacer."""

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
    """Historial thread-safe: el worker escribe y la interfaz lee."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
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
        """True si ese archivo de origen ya fue procesado (para el modo copiar)."""
        with self._lock:
            cursor = self._conn.execute("SELECT 1 FROM processed_sources WHERE signature = ? LIMIT 1", (signature,))
            return cursor.fetchone() is not None

    def mark_source_seen(self, signature: str, timestamp: str | None = None) -> None:
        """Recuerda un archivo de origen ya procesado, para no reprocesarlo al copiar."""
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
