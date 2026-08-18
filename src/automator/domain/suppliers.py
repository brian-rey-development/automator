"""Supplier registry: identify the invoice issuer by CUIT (or name) and canonicalize it.

The registry is the source of truth. Instead of trusting a fragile "Razon Social:"
label on the PDF, we look for a known supplier's identifiers inside the invoice text.
The CUIT is the strong signal (O(1) index lookup); the normalized name is a
best-effort fallback. Matching never guesses: two candidate suppliers -> no match.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from automator.domain.cuit import CUIT_LENGTH, coerce_cuit, extract_cuits, is_valid_cuit
from automator.domain.names import normalize_name

# The text fallback ignores very short aliases (an "SA" would hit every invoice).
_MIN_TEXT_ALIAS = 5


class Supplier(BaseModel):
    """A known invoice issuer: CUIT (match key), legal name and optional aliases."""

    model_config = ConfigDict(frozen=True)

    cuit: str
    razon_social: str
    nombre_fantasia: str | None = None
    extra_aliases: tuple[str, ...] = ()

    @field_validator("cuit")
    @classmethod
    def _normalize_cuit(cls, value: str) -> str:
        digits = coerce_cuit(value)
        if len(digits) != CUIT_LENGTH:
            raise ValueError(f"El CUIT debe tener {CUIT_LENGTH} digitos: '{value}'")
        if not is_valid_cuit(digits):
            raise ValueError(f"El CUIT no es valido (digito verificador incorrecto): '{value}'")
        return digits

    @field_validator("razon_social")
    @classmethod
    def _razon_social_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La razon social no puede estar vacia.")
        return value.strip()

    def aliases(self) -> frozenset[str]:
        """Normalized set of every name this supplier may be recognized by."""
        raw = (self.razon_social, self.nombre_fantasia, *self.extra_aliases)
        return frozenset(normalize_name(name) for name in raw if name and normalize_name(name))


class SupplierRegistry:
    """Immutable in-memory index over a set of suppliers for O(1) CUIT matching."""

    def __init__(self, suppliers: list[Supplier] | tuple[Supplier, ...]) -> None:
        self._suppliers = tuple(suppliers)
        self._by_cuit = {supplier.cuit: supplier for supplier in self._suppliers}
        self._by_name = {alias: supplier for supplier in self._suppliers for alias in supplier.aliases()}

    def __len__(self) -> int:
        return len(self._suppliers)

    def match(self, text: str, exclude_cuits: set[str]) -> Supplier | None:
        """Resolve the issuing supplier: CUIT first, normalized-name fallback."""
        by_cuit = self._match_cuit(text, exclude_cuits)
        if by_cuit is not None:
            return by_cuit
        return self._match_text(text)

    def canonical_name(self, supplier: Supplier) -> str:
        return supplier.razon_social

    def search(self, query: str, limit: int) -> list[Supplier]:
        needle = normalize_name(query)
        matches = [s for s in self._suppliers if any(needle in alias for alias in s.aliases())]
        return sorted(matches, key=lambda s: s.razon_social)[:limit]

    def _match_cuit(self, text: str, exclude_cuits: set[str]) -> Supplier | None:
        candidates = {self._by_cuit[cuit] for cuit in extract_cuits(text) - exclude_cuits if cuit in self._by_cuit}
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _match_text(self, text: str) -> Supplier | None:
        haystack = normalize_name(text)
        matches = {
            supplier for alias, supplier in self._by_name.items() if len(alias) >= _MIN_TEXT_ALIAS and alias in haystack
        }
        return next(iter(matches)) if len(matches) == 1 else None
