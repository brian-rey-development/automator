"""Pure filing policy tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from automator.domain.buyer import BuyerResolution
from automator.domain.filing import FilingFolders, decide_filing, is_reliable
from automator.domain.models import ParsedInvoice, ProcessOutcome, Voucher, VoucherKind


def _invoice(supplier: str = "ACME SA", number: str = "00000001") -> ParsedInvoice:
    return ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, "A"),
        sales_point="0001",
        number=number,
        supplier=supplier,
        buyer_cuit="30111111118",
    )


def _folders() -> FilingFolders:
    return FilingFolders(
        review=Path("/out/_PARA_REVISAR"),
        duplicates=Path("/out/_DUPLICADOS"),
        archive=Path("/out/EMPRESA/ACME"),
    )


def _exact_buyer() -> BuyerResolution:
    return BuyerResolution(cuit="30111111118", ambiguous=False, fuzzy=False, score=1.0)


def test_ambiguous_buyer_goes_to_review() -> None:
    decision = decide_filing(
        _invoice(),
        BuyerResolution(cuit=None, ambiguous=True, fuzzy=False, score=0.0),
        societies=(),
        is_duplicate=False,
        folders=_folders(),
    )
    assert decision.outcome is ProcessOutcome.NEEDS_REVIEW
    assert decision.base_folder == _folders().review


def test_duplicate_goes_to_duplicates_folder() -> None:
    decision = decide_filing(_invoice(), _exact_buyer(), societies=(), is_duplicate=True, folders=_folders())
    assert decision.outcome is ProcessOutcome.DUPLICATE
    assert decision.base_folder == _folders().duplicates


def test_known_buyer_is_moved() -> None:
    decision = decide_filing(_invoice(), _exact_buyer(), societies=(), is_duplicate=False, folders=_folders())
    assert decision.outcome is ProcessOutcome.MOVED
    assert decision.base_folder == _folders().archive


def test_unknown_buyer_is_unclassified() -> None:
    decision = decide_filing(
        _invoice(),
        BuyerResolution(cuit=None, ambiguous=False, fuzzy=False, score=0.0),
        societies=(),
        is_duplicate=False,
        folders=_folders(),
    )
    assert decision.outcome is ProcessOutcome.UNCLASSIFIED


@dataclass(frozen=True)
class _Society:
    cuit: str
    names: tuple[str, ...]

    def match_names(self) -> tuple[str, ...]:
        return self.names


def test_fuzzy_buyer_goes_to_review() -> None:
    decision = decide_filing(
        _invoice(),
        BuyerResolution(cuit="30111111118", ambiguous=False, fuzzy=True, score=0.93),
        societies=(),
        is_duplicate=False,
        folders=_folders(),
    )
    assert decision.outcome is ProcessOutcome.NEEDS_REVIEW
    assert decision.base_folder == _folders().review
    assert "93%" in decision.message


def test_own_society_trade_name_as_issuer_is_unreliable() -> None:
    society = _Society("30111111118", ("EMPRESA EJEMPLO SA", "Ejemplo"))
    assert is_reliable(_invoice("Ejemplo"), (society,)) is False


def test_unknown_supplier_is_unreliable() -> None:
    from automator.domain.models import UNKNOWN_SUPPLIER

    assert is_reliable(_invoice(UNKNOWN_SUPPLIER), ()) is False


def test_buyer_block_read_as_supplier_is_unreliable() -> None:
    # "Razon Social: 6727-CUENCA DEL SALADO S.A." is the customer block, not the issuer.
    society = _Society("30111111118", ("COMPRADORA UNO SA",))
    assert is_reliable(_invoice("6727-COMPRADORA UNO S.A."), (society,)) is False


def test_short_society_name_only_matches_exactly() -> None:
    society = _Society("30111111118", ("ACME",))
    assert is_reliable(_invoice("ACME INDUSTRIAL SRL"), (society,)) is True
