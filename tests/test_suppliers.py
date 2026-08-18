"""Tests for the supplier model and the matching registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from automator.domain.suppliers import Supplier, SupplierRegistry


def _supplier(cuit: str, razon_social: str, **extra: object) -> Supplier:
    return Supplier(cuit=cuit, razon_social=razon_social, **extra)  # type: ignore[arg-type]


def test_supplier_normalizes_and_validates_cuit() -> None:
    assert _supplier("30-99999999-5", "X").cuit == "30999999995"


def test_supplier_recovers_a_cuit_missing_its_leading_zeros() -> None:
    # DNI stored without its padding zeros (10 digits): rebuilt to the canonical CUIT.
    assert _supplier("2012345675", "X").cuit == "20012345675"


def test_supplier_rejects_bad_check_digit() -> None:
    with pytest.raises(ValidationError):
        _supplier("30999999990", "X")


def test_supplier_rejects_empty_razon_social() -> None:
    with pytest.raises(ValidationError):
        _supplier("30999999995", "   ")


def test_aliases_are_normalized_from_all_names() -> None:
    supplier = _supplier("30999999995", "Café del Sur SA", nombre_fantasia="CafeSur", extra_aliases=("Cafe del Sur",))
    aliases = supplier.aliases()
    assert "cafe del sur sa" in aliases
    assert "cafesur" in aliases
    assert "cafe del sur" in aliases


def test_registry_matches_by_cuit() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "PROVEEDOR EJEMPLO SRL")])
    match = registry.match("bla CUIT 30-99999999-5 bla", exclude_cuits=set())
    assert match is not None
    assert match.razon_social == "PROVEEDOR EJEMPLO SRL"


def test_registry_excludes_buyer_cuit() -> None:
    registry = SupplierRegistry([_supplier("30111111118", "SOY EL COMPRADOR")])
    assert registry.match("CUIT 30-11111111-8", exclude_cuits={"30111111118"}) is None


def test_registry_two_supplier_cuits_is_not_resolved() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "A"), _supplier("30707730214", "B")])
    assert registry.match("CUIT 30-99999999-5 y CUIT 30-70773021-4", exclude_cuits=set()) is None


def test_registry_falls_back_to_name_when_no_cuit() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "Distribuidora Nordica SA")])
    match = registry.match("Proveedor: DISTRIBUIDORA NÓRDICA SA - Total 100", exclude_cuits=set())
    assert match is not None
    assert match.cuit == "30999999995"


def test_registry_name_fallback_ignores_unknown_text() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "Distribuidora Nordica SA")])
    assert registry.match("Proveedor: OTRA COSA CUALQUIERA", exclude_cuits=set()) is None


def test_canonical_name_is_razon_social() -> None:
    supplier = _supplier("30999999995", "Distribuidora Nordica SA", nombre_fantasia="NordSur")
    registry = SupplierRegistry([supplier])
    assert registry.canonical_name(supplier) == "Distribuidora Nordica SA"


def test_search_finds_by_partial_name() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "Distribuidora Nordica SA")])
    assert [s.cuit for s in registry.search("nord", limit=10)] == ["30999999995"]


def test_len_reports_supplier_count() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "A"), _supplier("30707730214", "B")])
    assert len(registry) == 2
