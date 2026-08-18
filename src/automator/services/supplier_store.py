"""Persistent supplier registry backed by SQLite, plus its in-memory snapshot.

Suppliers can number in the hundreds or more, so they live in their own indexed
table (in the same history.db) instead of bloating config.json. The worker never
queries SQLite on the hot path: it reads an immutable SupplierRegistry snapshot,
rebuilt (reload) after each import or edit. Mirrors the ConfigStore concurrency model.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from automator.domain.suppliers import Supplier, SupplierRegistry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    cuit TEXT PRIMARY KEY,
    razon_social TEXT NOT NULL,
    nombre_fantasia TEXT,
    aliases TEXT NOT NULL DEFAULT '[]'
);
"""


class SupplierStore:
    """Thread-safe SQLite store of suppliers, keyed by CUIT."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def bulk_upsert(self, suppliers: list[Supplier]) -> tuple[int, int]:
        """Insert or update suppliers by CUIT, merging aliases. Returns (created, updated)."""
        created = updated = 0
        with self._lock:
            for supplier in suppliers:
                existing = self._find(supplier.cuit)
                merged = _merge(existing, supplier)
                self._conn.execute(
                    "INSERT OR REPLACE INTO suppliers (cuit, razon_social, nombre_fantasia, aliases)"
                    " VALUES (?, ?, ?, ?)",
                    _row(merged),
                )
                created, updated = (created, updated + 1) if existing else (created + 1, updated)
            self._conn.commit()
        return created, updated

    def all(self) -> list[Supplier]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM suppliers ORDER BY razon_social")
            return [_to_supplier(row) for row in cursor.fetchall()]

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0])

    def delete(self, cuit: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM suppliers WHERE cuit = ?", (cuit,))
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM suppliers")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _find(self, cuit: str) -> Supplier | None:
        row = self._conn.execute("SELECT * FROM suppliers WHERE cuit = ?", (cuit,)).fetchone()
        return _to_supplier(row) if row else None


class SupplierRegistryStore:
    """Holds the immutable SupplierRegistry the worker reads; rebuilt on demand."""

    def __init__(self, store: SupplierStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._registry = SupplierRegistry(store.all())

    def get(self) -> SupplierRegistry:
        with self._lock:
            return self._registry

    def reload(self) -> None:
        registry = SupplierRegistry(self._store.all())
        with self._lock:
            self._registry = registry


def _merge(existing: Supplier | None, incoming: Supplier) -> Supplier:
    if existing is None:
        return incoming
    aliases = tuple(dict.fromkeys((*existing.extra_aliases, *incoming.extra_aliases)))
    return incoming.model_copy(
        update={"extra_aliases": aliases, "nombre_fantasia": incoming.nombre_fantasia or existing.nombre_fantasia}
    )


def _row(supplier: Supplier) -> tuple[str, str, str | None, str]:
    return (supplier.cuit, supplier.razon_social, supplier.nombre_fantasia, json.dumps(list(supplier.extra_aliases)))


def _to_supplier(row: sqlite3.Row) -> Supplier:
    return Supplier(
        cuit=row["cuit"],
        razon_social=row["razon_social"],
        nombre_fantasia=row["nombre_fantasia"],
        extra_aliases=tuple(json.loads(row["aliases"])),
    )
