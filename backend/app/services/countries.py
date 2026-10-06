"""Country vocabulary: the ISO 3166-1 alpha-2 list and the ONE normalizer.

The list lives in `data/countries.yaml` (a vendored mapping `CODE: English
name`, not a dependency), the same data-not-enum contract as `markets.py`.
Anything that stores, compares or displays a country goes through here:
`normalize` is the only parser of free text ("us", "UK", "United States") into
a stored code, so no caller grows its own alias table.

Stored values are always upper-case ISO codes. "UK" and the other English
variants in `_ALIASES` are accepted as INPUT; they are never a code or a label
in the list, so `is_valid("UK")` is False. Names match without accents or
curly apostrophes ("Cote d'Ivoire", "Côte d’Ivoire").
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

_DATA_FILE = Path(__file__).parent / "data" / "countries.yaml"

# Input-only aliases, in `_fold` form. "UK" is the one everyone types; ISO says GB.
# A name the list already holds (Russia, Vietnam, Türkiye) needs no entry here.
_ALIASES = {
    "uk": "GB", "great britain": "GB", "britain": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB",
    "usa": "US", "u.s.": "US", "u.s.a.": "US", "us of a": "US", "america": "US",
    "united states of america": "US",
    "turkey": "TR",
    "czech republic": "CZ",
    "the netherlands": "NL", "holland": "NL",
    "uae": "AE",
    "korea": "KR", "republic of korea": "KR",
    "ivory coast": "CI",
    "viet nam": "VN",
}


def _fold(text: str) -> str:
    """Casefold, drop accents, and straighten curly apostrophes."""
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return plain.casefold().replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")


@lru_cache(maxsize=1)
def _load() -> dict[str, str]:
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8")) or {}
    return {str(code): str(name) for code, name in raw.items()}


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    """folded English name -> code."""
    return {_fold(name): code for code, name in _load().items()}


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

    Accepts a code in any case, an English name in any case and with or without
    accents, or one of the common variants in `_ALIASES` ("UK", "USA", "Holland").
    A miss is None, never a guess ("Remote", "XX", "Narnia").
    """
    text = (value or "").strip()
    if not text:
        return None
    if len(text) == 2 and text.isalpha() and text.upper() in _load():
        return text.upper()
    folded = _fold(text)
    return _ALIASES.get(folded) or _names().get(folded)
