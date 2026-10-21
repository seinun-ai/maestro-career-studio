"""Country vocabulary: the ISO 3166-1 alpha-2 list and the ONE normalizer.

The list lives in `data/countries.yaml` (a vendored mapping `CODE: English
name`, not a dependency), the same data-not-enum contract as `markets.py`.
Anything that stores, compares or displays a country goes through here:
`normalize` is the only parser of free text ("us", "UK", "United States") into
a stored code, so no caller grows its own alias table.

Stored values are always upper-case ISO codes. "UK" and the other English
variants in `_ALIASES` are accepted as INPUT; they are never a code or a label
in the list. Names match without accents or curly apostrophes
("Cote d'Ivoire", "Côte d’Ivoire").

`named_in` reads a place line ("Toronto, ON, Canada") and `for_job` is the one
rule for a job's `country_code`: its country field, else its location. Each
country's currency is data too (`data/country_currencies.yaml`, read by
`currency`); a country with no entry has no currency, never a guessed one.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

_DATA_FILE = Path(__file__).parent / "data" / "countries.yaml"
_CURRENCY_FILE = Path(__file__).parent / "data" / "country_currencies.yaml"

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


@lru_cache(maxsize=1)
def _currencies() -> dict[str, str]:
    """code -> ISO 4217 currency, for the countries that have one."""
    raw = yaml.safe_load(_CURRENCY_FILE.read_text(encoding="utf-8")) or {}
    return {str(code): str(currency) for code, currency in raw.items()}


def labels() -> dict[str, str]:
    """code -> English name, in file order."""
    return dict(_load())


def label(code: str | None) -> str | None:
    """A stored code's English name ("GB" -> "United Kingdom"); None for anything that is not a
    code in the list, the input-only "UK" included."""
    return _load().get((code or "").strip().upper())


def currency(code: str | None) -> str | None:
    """The ISO 4217 currency a country's pay is posted in ("CA" -> "CAD"), from data. None when
    the code is not a country or the data names no single currency for it (Antarctica)."""
    return _currencies().get((code or "").strip().upper())


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


# A place line splits into parts at commas, slashes, brackets and spaced dashes; "and" never
# splits, or "Bosnia and Herzegovina" would be two places.
_PLACE_PARTS = re.compile(r"[,/;|()\[\]]+|\s[-\u2013\u2014]\s")
# A US state with a country's name: "Atlanta, Georgia" is not in Tbilisi.
_AMBIGUOUS_PLACES = {"georgia"}


def named_in(place: str | None) -> str | None:
    """The one country a free-text place names ("Toronto, ON, Canada" -> "CA"), else None.

    The whole text first (`normalize`, so a bare code counts), then each part by name or alias
    only: a two-letter part is a state as often as a country ("San Francisco, CA" is California),
    so it never counts unless it is an alias such as "UK". Two different countries named, or
    none, is None, never a pick.
    """
    text = (place or "").strip()
    if not text or _fold(text) in _AMBIGUOUS_PLACES:
        return None
    whole = normalize(text)
    if whole:
        return whole
    found: set[str] = set()
    for part in _PLACE_PARTS.split(text):
        word = part.strip()
        folded = _fold(word)
        if folded in _AMBIGUOUS_PLACES:
            continue
        code = _ALIASES.get(folded) or (_names().get(folded) if len(word) > 2 else None)
        if code:
            found.add(code)
    return found.pop() if len(found) == 1 else None


def for_job(country: str | None, location: str | None) -> str | None:
    """A job's `country_code`: the country the extraction named ("Georgia" there is the country),
    else the one its location line names. The capture path (`routers/jobs._apply_extraction`)
    and the backfill migration both use this, so a job's code has one rule."""
    return normalize(country) or named_in(country) or named_in(location)
