"""Name normalization for aliases and text matching.

The single source of truth for reducing a legal or trade name to a comparable
key: accents stripped, case folded, whitespace collapsed. Used both to build the
alias index and to scan invoice text for a known party.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated

from pydantic import AfterValidator

_WHITESPACE = re.compile(r"\s+")


def normalize_name(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", without_accents).strip().casefold()


def require_legal_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("La razon social no puede estar vacia.")
    return stripped


LegalName = Annotated[str, AfterValidator(require_legal_name)]
