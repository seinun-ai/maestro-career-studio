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
    "wales": "GB", "northern ireland": "GB",
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


def aliases_for(code: str | None) -> list[str]:
    """The input-only variants that read as this code, folded ("GB" -> ["uk", "great britain", ...]),
    in table order; none for a code with no variant. A question names a country by these as often
    as by its name (`autofill_country`)."""
    wanted = (code or "").strip().upper()
    return [alias for alias, target in _ALIASES.items() if target == wanted]


def currency_codes() -> frozenset[str]:
    """Every ISO 4217 code the data names, for telling "45 USD" from "45 WPM"."""
    return frozenset(_currencies().values())


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


# Place names that hold a country's name and are no country: a US state ("New Mexico"), an Australian
# one ("New South Wales"), a region ("Latin America"). A sentence reads them as nothing.
_NOT_COUNTRIES = (
    "new mexico", "new jersey", "new south wales", "latin america", "south america",
    "north america", "central america",
)
# Two capital letters count in a sentence only for the codes everyone writes as a word ("in the US",
# "the UK"): "CA", "DE" and "IN" are US states, and "us" in lower case is a word.
_SENTENCE_CODES = {"US": "US", **{alias.upper(): code for alias, code in _ALIASES.items() if len(alias) == 2}}


@lru_cache(maxsize=1)
def _sentence_table() -> tuple[re.Pattern[str], dict[str, str | None]]:
    """Every name and alias (and a dotted alias without its last dot, "u.s"), longest first, so
    "Northern Ireland" is read before "Ireland" and "Papua New Guinea" before "Guinea"; each folded
    word's code, None for a place that is no country."""
    words: dict[str, str | None] = {**_names(), **_ALIASES}
    words.update({alias.rstrip("."): code for alias, code in _ALIASES.items() if alias.endswith(".")})
    words.update(dict.fromkeys((*_NOT_COUNTRIES, *_AMBIGUOUS_PLACES)))
    names = sorted((w for w in words if len(w) > 2), key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)"), words


def mentioned_in(text: str | None) -> set[str]:
    """Every country a sentence names ("Can you work in Germany or the Netherlands?" -> {"DE",
    "NL"}), by its English name or an alias, whole words, without accents, in any case; a code only
    as "US" or "UK" in capitals. A place that holds a country's name and is none ("New Mexico",
    "Georgia") names nothing. A sentence, not a place line: `named_in` reads a job's location."""
    if not text:
        return set()
    pattern, words = _sentence_table()
    found = {words[m.group(1)] for m in pattern.finditer(_fold(text))}
    found |= {code for word, code in _SENTENCE_CODES.items() if re.search(rf"(?<![\w$]){word}(?![\w$])", text)}
    found.discard(None)
    return found


def for_job(country: str | None, location: str | None) -> str | None:
    """A job's `country_code`: the country the extraction named ("Georgia" there is the country),
    else the one its location line names. The capture path (`routers/jobs._apply_extraction`)
    and the backfill migration both use this, so a job's code has one rule."""
    return normalize(country) or named_in(country) or named_in(location)
