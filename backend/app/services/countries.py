"""Country vocabulary: the ISO 3166-1 alpha-2 list and the ONE normalizer.

The list lives in `data/countries.yaml` (a vendored mapping `CODE: English
name`, not a dependency), the same data-not-enum contract as `markets.py`.
Anything that stores, compares or displays a country goes through here:
`normalize` is the only parser of free text ("us", "UK", "United States") into
a stored code, so no caller grows its own alias table.

Stored values are always upper-case ISO codes. "UK" is accepted as INPUT and
maps to GB; it is never a code in the list, so `is_valid("UK")` is False.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_DATA_FILE = Path(__file__).parent / "data" / "countries.yaml"

# Input-only aliases (casefolded). "UK" is the one everyone types; ISO says GB.
_ALIASES = {"uk": "GB"}


@lru_cache(maxsize=1)
def _load() -> dict[str, str]:
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8")) or {}
    return {str(code): str(name) for code, name in raw.items()}


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    """casefolded English name -> code."""
    return {name.casefold(): code for code, name in _load().items()}


def labels() -> dict[str, str]:
    """code -> English name, in file order."""
    return dict(_load())


def is_valid(code: str) -> bool:
    """True only for an exact upper-case ISO code in the list."""
    return code in _load()


def name_for(code: str) -> str:
    """English name for a code; KeyError for a code not in the list."""
    return _load()[code]


def normalize(value: str | None) -> str | None:
    """Free text -> ISO code, or None when it names no country.

    Accepts a code in any case, the alias "UK", or an English name in any case.
    A miss is None, never a guess ("Remote", "XX", "Narnia").
    """
    text = (value or "").strip()
    if not text:
        return None
    if len(text) == 2 and text.isalpha() and text.upper() in _load():
        return text.upper()
    folded = text.casefold()
    return _ALIASES.get(folded) or _names().get(folded)
