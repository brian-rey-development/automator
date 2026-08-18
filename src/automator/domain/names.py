"""Name normalization for aliases and text matching.

The single source of truth for reducing a legal or trade name to a comparable
key: accents stripped, case folded, whitespace collapsed. Used both to build the
alias index and to scan invoice text for a known party.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_name(text: str) -> str:
    """Strip accents, fold case and collapse whitespace to a comparable key."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", without_accents).strip().casefold()
