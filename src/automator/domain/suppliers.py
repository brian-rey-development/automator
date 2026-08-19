"""Issuer registry. Match never guesses: 0 or 2+ hits means no match."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from automator.domain.cuit import Cuit, extract_cuits
from automator.domain.names import LegalName, normalize_name

# The text fallback ignores very short aliases (an "SA" would hit every invoice).
_MIN_TEXT_ALIAS = 5


class Supplier(BaseModel):
    model_config = ConfigDict(frozen=True)

    cuit: Cuit
    legal_name: LegalName
    trade_name: str | None = None
    extra_aliases: tuple[str, ...] = ()

    def aliases(self) -> frozenset[str]:
        raw = (self.legal_name, self.trade_name, *self.extra_aliases)
        return frozenset(normalize_name(name) for name in raw if name and normalize_name(name))


class SupplierRegistry:
    """Immutable in-memory index over a set of suppliers for O(1) CUIT matching."""

    def __init__(self, suppliers: list[Supplier] | tuple[Supplier, ...]) -> None:
        self._suppliers = tuple(suppliers)
        by_cuit: dict[str, list[Supplier]] = {}
        by_name: dict[str, list[Supplier]] = {}
        for supplier in self._suppliers:
            by_cuit.setdefault(supplier.cuit, []).append(supplier)
            for alias in supplier.aliases():
                by_name.setdefault(alias, []).append(supplier)
        self._by_cuit = by_cuit
        self._by_name = by_name

    def __len__(self) -> int:
        return len(self._suppliers)

    def match(self, text: str, exclude_cuits: set[str]) -> Supplier | None:
        leftover = extract_cuits(text) - exclude_cuits
        by_cuit = self._match_cuit(leftover)
        if by_cuit is not None:
            return by_cuit
        if leftover:
            return None
        return self._match_text(text, exclude_cuits)

    def search(self, query: str, limit: int) -> list[Supplier]:
        needle = normalize_name(query)
        matches = [s for s in self._suppliers if any(needle in alias for alias in s.aliases())]
        return sorted(matches, key=lambda s: s.legal_name)[:limit]

    def _match_cuit(self, leftover: set[str]) -> Supplier | None:
        candidates: set[Supplier] = set()
        for cuit in leftover:
            candidates.update(self._by_cuit.get(cuit, ()))
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _match_text(self, text: str, exclude_cuits: set[str]) -> Supplier | None:
        haystack = normalize_name(text)
        matches: set[Supplier] = set()
        for alias, suppliers in self._by_name.items():
            if len(alias) >= _MIN_TEXT_ALIAS and alias in haystack:
                matches.update(s for s in suppliers if s.cuit not in exclude_cuits)
        return next(iter(matches)) if len(matches) == 1 else None


def merge_supplier(existing: Supplier, incoming: Supplier) -> Supplier:
    aliases = [*existing.extra_aliases, *incoming.extra_aliases]
    if incoming.legal_name != existing.legal_name:
        aliases.append(existing.legal_name)
    if existing.trade_name and existing.trade_name != incoming.trade_name:
        aliases.append(existing.trade_name)
    return incoming.model_copy(
        update={
            "extra_aliases": tuple(dict.fromkeys(alias for alias in aliases if alias)),
            "trade_name": incoming.trade_name or existing.trade_name,
        }
    )
