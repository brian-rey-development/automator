"""Resolve which configured society is the buyer of a document.

Exact CUIT always wins. Fuzzy name matching never files: it only proposes a
candidate that filing policy sends to review.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from automator.domain.models import ParsedInvoice
from automator.domain.names import normalize_name

_FUZZY_THRESHOLD = 0.90
_FUZZY_MARGIN = 0.05


class SocietyLike(Protocol):
    @property
    def cuit(self) -> str: ...

    def match_names(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class BuyerResolution:
    cuit: str | None
    ambiguous: bool
    fuzzy: bool
    score: float


def resolve_buyer(invoice: ParsedInvoice, societies: list[SocietyLike]) -> BuyerResolution:
    if invoice.ambiguous_buyer:
        return BuyerResolution(cuit=None, ambiguous=True, fuzzy=False, score=0.0)
    if invoice.buyer_cuit is not None:
        return BuyerResolution(cuit=invoice.buyer_cuit, ambiguous=False, fuzzy=False, score=1.0)
    if invoice.buyer_name:
        return _fuzzy_match(invoice.buyer_name, societies)
    return BuyerResolution(cuit=None, ambiguous=False, fuzzy=False, score=0.0)


def _fuzzy_match(name: str, societies: list[SocietyLike]) -> BuyerResolution:
    if not societies:
        return BuyerResolution(cuit=None, ambiguous=False, fuzzy=False, score=0.0)
    scored = sorted(((_best_similarity(name, s), s) for s in societies), key=lambda pair: pair[0], reverse=True)
    best_score, best = scored[0]
    if best_score < _FUZZY_THRESHOLD:
        return BuyerResolution(cuit=None, ambiguous=False, fuzzy=False, score=best_score)
    if len(scored) > 1 and best_score - scored[1][0] < _FUZZY_MARGIN:
        return BuyerResolution(cuit=None, ambiguous=True, fuzzy=False, score=best_score)
    return BuyerResolution(cuit=best.cuit, ambiguous=False, fuzzy=True, score=best_score)


def _best_similarity(name: str, society: SocietyLike) -> float:
    return max(_similarity(name, candidate) for candidate in society.match_names())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio()
