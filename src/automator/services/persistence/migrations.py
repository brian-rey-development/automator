"""Additive SQLite schema migrations. Never drop or rename user data."""

from __future__ import annotations

import sqlite3

_V1 = 1
_V2 = 2
_CURRENT = 3


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    current = _read_version(conn)
    if current < _V1:
        _set_version(conn, _V1)
        current = _V1
    if current < _V2:
        _add_column(conn, "records", "issuer_cuit", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_issuer_cuit ON records(issuer_cuit)")
        _set_version(conn, _V2)
        current = _V2
    if current < _CURRENT:
        _add_column(conn, "records", "issuer_identity", "TEXT")
        _add_column(conn, "records", "source_signature", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_issuer_identity ON records(issuer_identity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_source_signature ON records(source_signature)")
        _set_version(conn, _CURRENT)


def _read_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
    value = row["version"] if row is not None else None
    return int(value) if value is not None else 0


def _set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in columns:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
