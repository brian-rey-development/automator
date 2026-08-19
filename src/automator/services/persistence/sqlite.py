"""SQLite connections used by the ledger and supplier store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_TIMEOUT_S = 30.0


def connect_wal(path: Path, timeout: float = _TIMEOUT_S) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
