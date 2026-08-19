"""Tests for the supplier model and the matching registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from automator.domain.suppliers import Supplier, SupplierRegistry, merge_supplier


def _supplier(cuit: str, legal_name: str, **extra: object) -> Supplier:
    return Supplier(cuit=cuit, legal_name=legal_name, **extra)


def test_supplier_normalizes_and_validates_cuit() -> None:
    assert _supplier("30-99999999-5", "X").cuit == "30999999995"


def test_supplier_recovers_a_cuit_missing_its_leading_zeros() -> None:
    # DNI stored without its padding zeros (10 digits): rebuilt to the canonical CUIT.
    assert _supplier("2012345675", "X").cuit == "20012345675"


def test_supplier_rejects_bad_check_digit() -> None:
    with pytest.raises(ValidationError):
        _supplier("30999999990", "X")


def test_supplier_rejects_empty_legal_name() -> None:
    with pytest.raises(ValidationError):
        _supplier("30999999995", "   ")


def test_aliases_are_normalized_from_all_names() -> None:
    supplier = _supplier("30999999995", "Café del Sur SA", trade_name="CafeSur", extra_aliases=("Cafe del Sur",))
    aliases = supplier.aliases()
    assert "cafe del sur sa" in aliases
    assert "cafesur" in aliases
    assert "cafe del sur" in aliases


def test_registry_matches_by_cuit() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "PROVEEDOR EJEMPLO SRL")])
    match = registry.match("bla CUIT 30-99999999-5 bla", exclude_cuits=set())
    assert match is not None
    assert match.legal_name == "PROVEEDOR EJEMPLO SRL"


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


def test_search_finds_by_partial_name() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "Distribuidora Nordica SA")])
    assert [s.cuit for s in registry.search("nord", limit=10)] == ["30999999995"]


def test_len_reports_supplier_count() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "A"), _supplier("30707730214", "B")])
    assert len(registry) == 2


def test_shared_alias_does_not_guess_a_supplier() -> None:
    registry = SupplierRegistry(
        [
            _supplier("30999999995", "Acme Norte SA", extra_aliases=("acme sa",)),
            _supplier("30707730214", "Acme Sur SA", extra_aliases=("acme sa",)),
        ]
    )
    assert registry.match("Factura ACME SA total 100", exclude_cuits=set()) is None


def test_name_fallback_skipped_when_unknown_cuit_is_present() -> None:
    registry = SupplierRegistry([_supplier("30999999995", "Distribuidora Nordica SA")])
    text = "CUIT 30-70773021-4 Proveedor: DISTRIBUIDORA NORDICA SA"
    assert registry.match(text, exclude_cuits=set()) is None


def test_name_fallback_excludes_buyer_supplier() -> None:
    registry = SupplierRegistry(
        [
            _supplier("30111111118", "Distribuidora Nordica SA"),
            _supplier("30999999995", "Otra Firma Distinta SA"),
        ]
    )
    assert registry.match("Proveedor: DISTRIBUIDORA NORDICA SA", exclude_cuits={"30111111118"}) is None


def test_merge_supplier_keeps_previous_legal_name_as_alias() -> None:
    existing = _supplier("30999999995", "Nombre Viejo SA", trade_name="Viejo")
    incoming = _supplier("30999999995", "Nombre Nuevo SA", trade_name="Nuevo")
    merged = merge_supplier(existing, incoming)
    assert merged.legal_name == "Nombre Nuevo SA"
    assert "Nombre Viejo SA" in merged.extra_aliases
    assert "Viejo" in merged.extra_aliases
    assert merged.trade_name == "Nuevo"


def test_short_alias_does_not_match_every_invoice() -> None:
    registry = SupplierRegistry(
        [_supplier("30999999995", "Proveedor Ejemplo SA", extra_aliases=("SA",))],
    )
    assert registry.match("FACTURA A SA COMPROBANTE", exclude_cuits=set()) is None
