"""Tests for buyer resolution: exact CUIT first, guarded fuzzy fallback."""

from __future__ import annotations

from automator.config import SocietyMapping
from automator.domain.buyer import resolve_buyer
from automator.domain.models import DocumentType, ParsedInvoice, Voucher, VoucherKind
from tests.conftest import CUIT_ONE, CUIT_TWO


def _order(buyer_cuit: str | None = None, buyer_name: str | None = None, ambiguous: bool = False) -> ParsedInvoice:
    return ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, "A"),
        sales_point="2026",
        number="00004046",
        supplier="FERRETERIA EJEMPLO SRL",
        buyer_cuit=buyer_cuit,
        ambiguous_buyer=ambiguous,
        document_type=DocumentType.ORDEN_COMPRA,
        buyer_name=buyer_name,
    )


def _society(cuit: str, name: str, nombre_fantasia: str | None = None, aliases: tuple[str, ...] = ()) -> SocietyMapping:
    return SocietyMapping(cuit=cuit, name=name, nombre_fantasia=nombre_fantasia, aliases=aliases)


def test_exact_cuit_wins() -> None:
    resolution = resolve_buyer(_order(buyer_cuit=CUIT_ONE), [_society(CUIT_ONE, "COMPRADORA UNO SA")])
    assert resolution.cuit == CUIT_ONE
    assert not resolution.fuzzy
    assert not resolution.ambiguous


def test_ambiguous_buyer_is_not_resolved() -> None:
    resolution = resolve_buyer(_order(ambiguous=True), [_society(CUIT_ONE, "COMPRADORA UNO SA")])
    assert resolution.cuit is None
    assert resolution.ambiguous


def test_fuzzy_matches_near_identical_name() -> None:
    societies = [_society(CUIT_ONE, "COMPRADORA UNO SA"), _society(CUIT_TWO, "TOTALMENTE DISTINTA SRL")]
    resolution = resolve_buyer(_order(buyer_name="COMPRADORA UNO S.A."), societies)
    assert resolution.cuit == CUIT_ONE
    assert resolution.fuzzy
    assert resolution.score >= 0.90


def test_fuzzy_matches_via_alias() -> None:
    societies = [
        _society(CUIT_ONE, "COMPRADORA UNO SA", aliases=("La Uno Distribuciones",)),
        _society(CUIT_TWO, "TOTALMENTE DISTINTA SRL"),
    ]
    resolution = resolve_buyer(_order(buyer_name="La Uno Distribuciones"), societies)
    assert resolution.cuit == CUIT_ONE
    assert resolution.fuzzy


def test_fuzzy_matches_via_nombre_fantasia() -> None:
    societies = [
        _society(CUIT_ONE, "COMPRADORA UNO SA", nombre_fantasia="Compradora Uno"),
        _society(CUIT_TWO, "TOTALMENTE DISTINTA SRL"),
    ]
    resolution = resolve_buyer(_order(buyer_name="Compradora Uno"), societies)
    assert resolution.cuit == CUIT_ONE
    assert resolution.fuzzy


def test_fuzzy_below_threshold_is_not_matched() -> None:
    resolution = resolve_buyer(_order(buyer_name="OTRA EMPRESA CUALQUIERA"), [_society(CUIT_ONE, "COMPRADORA UNO SA")])
    assert resolution.cuit is None
    assert not resolution.fuzzy
    assert not resolution.ambiguous


def test_fuzzy_two_close_candidates_is_ambiguous() -> None:
    societies = [_society(CUIT_ONE, "COMPRADORA UNO SA"), _society(CUIT_TWO, "COMPRADORA UNO SB")]
    resolution = resolve_buyer(_order(buyer_name="COMPRADORA UNO SC"), societies)
    assert resolution.cuit is None
    assert resolution.ambiguous


def test_no_cuit_and_no_name_stays_unresolved() -> None:
    resolution = resolve_buyer(_order(), [_society(CUIT_ONE, "COMPRADORA UNO SA")])
    assert resolution.cuit is None
    assert not resolution.ambiguous
