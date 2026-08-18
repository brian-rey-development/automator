"""Tests for the SQLite supplier store and the in-memory registry snapshot."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from automator.domain.suppliers import Supplier
from automator.services.supplier_store import SupplierRegistryStore, SupplierStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SupplierStore]:
    instance = SupplierStore(tmp_path / "history.db")
    yield instance
    instance.close()


def _supplier(cuit: str, razon_social: str, **extra: object) -> Supplier:
    return Supplier(cuit=cuit, razon_social=razon_social, **extra)  # type: ignore[arg-type]


def test_bulk_upsert_creates_and_counts(store: SupplierStore) -> None:
    created, updated = store.bulk_upsert([_supplier("30999999995", "A"), _supplier("30707730214", "B")])
    assert (created, updated) == (2, 0)
    assert store.count() == 2


def test_bulk_upsert_updates_and_merges_aliases(store: SupplierStore) -> None:
    store.bulk_upsert([_supplier("30999999995", "A", extra_aliases=("x",))])
    created, updated = store.bulk_upsert([_supplier("30999999995", "A2", extra_aliases=("y",))])
    assert (created, updated) == (0, 1)
    stored = store.all()[0]
    assert set(stored.extra_aliases) == {"x", "y"}
    assert stored.razon_social == "A2"


def test_all_roundtrips_every_field(store: SupplierStore) -> None:
    store.bulk_upsert([_supplier("30999999995", "Nordica SA", nombre_fantasia="Nord", extra_aliases=("La Nordica",))])
    stored = store.all()[0]
    assert stored.razon_social == "Nordica SA"
    assert stored.nombre_fantasia == "Nord"
    assert stored.extra_aliases == ("La Nordica",)


def test_delete_removes_one_supplier(store: SupplierStore) -> None:
    store.bulk_upsert([_supplier("30999999995", "A"), _supplier("30707730214", "B")])
    store.delete("30999999995")
    assert [s.cuit for s in store.all()] == ["30707730214"]


def test_clear_empties_the_store(store: SupplierStore) -> None:
    store.bulk_upsert([_supplier("30999999995", "A")])
    store.clear()
    assert store.count() == 0


def test_registry_store_reload_reflects_new_suppliers(store: SupplierStore) -> None:
    registry_store = SupplierRegistryStore(store)
    assert len(registry_store.get()) == 0
    store.bulk_upsert([_supplier("30999999995", "A")])
    registry_store.reload()
    assert len(registry_store.get()) == 1
