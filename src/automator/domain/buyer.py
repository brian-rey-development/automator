"""Resolve which configured society is the buyer of a document.

Exact CUIT always wins. Only when no known CUIT is present does it fall back to
matching the printed buyer name against the society names, and even then it
refuses to guess: the match must clear a threshold AND be clearly ahead of the
runner-up, otherwise it is reported ambiguous and the document goes to review.
This keeps the invariant that no document is ever filed under the wrong company.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from automator.domain.models import ParsedInvoice

_FUZZY_THRESHOLD = 0.90  # Minimum name similarity to accept a fuzzy buyer match.
_FUZZY_MARGIN = 0.05  # The best match must beat the runner-up by at least this.


class SocietyLike(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def cuit(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BuyerResolution:
    """Outcome of deciding the buying company for a document."""

    cuit: str | None  # Resolved buyer CUIT, or None if it could not be decided.
    ambiguous: bool  # Several candidates are indistinguishable: send to review.
    fuzzy: bool  # Matched by name similarity, not by an exact CUIT.
    score: float  # Name similarity (0..1) for a fuzzy match; 1.0 for exact.


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
    scored = sorted(((_similarity(name, s.name), s) for s in societies), key=lambda pair: pair[0], reverse=True)
    best_score, best = scored[0]
    if best_score < _FUZZY_THRESHOLD:
        return BuyerResolution(cuit=None, ambiguous=False, fuzzy=False, score=best_score)
    if len(scored) > 1 and best_score - scored[1][0] < _FUZZY_MARGIN:
        return BuyerResolution(cuit=None, ambiguous=True, fuzzy=False, score=best_score)
    return BuyerResolution(cuit=best.cuit, ambiguous=False, fuzzy=True, score=best_score)


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left.casefold(), right.casefold()).ratio()
