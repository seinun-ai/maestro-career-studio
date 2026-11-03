"""Market vocabulary, loaded from data rather than compiled as an enum.

Why this exists: locale behaviour was scattered and US-shaped. `home_currency`
defaulted to USD with no way to say which country the user actually applies in;
the EEO question set was a hardcoded four-field US list
(`veteran_status`/`disability_status`/`gender`/`hispanic_latino` — the first is
US protected-veteran status, the last is the EEO-1's two-part ethnicity
structure); and the work-auth vocabulary is a US visa taxonomy (`opt`,
`stem_opt`, `h1b`, `tn`).

The market setting (`home`, where the user lives, plus `apply_in`, every market
they apply in; `schemas/market_settings.py`) drives all three, and the
vocabulary lives in `data/markets.yaml` so adding a market needs no code change
— the same contract `role_categories.yaml` already declares for roles. Keys are
the setting's own ("UK"); `country_code` / `for_country` bridge them to the ISO
codes jobs and base resumes store ("GB").

**The EEO posture is the load-bearing part.** `eeo_module` is null for every
market whose question set has not been verified against a primary source, and
`offers_eeo()` is the only gate the UI should consult. Categories are not
interchangeable across countries, so a guessed module does not produce a rough
answer — it produces a false one under the user's name.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.services import countries

_DATA_FILE = Path(__file__).parent / "data" / "markets.yaml"

DEFAULT_MARKET = "US"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8")) or {}
    entries: dict[str, dict[str, Any]] = {}
    for entry in raw.get("markets") or []:
        key = str(entry.get("key") or "").strip().upper()
        if not key:
            continue
        label = str(entry.get("label") or key)
        entries[key] = {
            "key": key,
            "label": label,
            # The name as a sentence uses it ("Asked by forms in the Netherlands."): declared by the
            # names that take "the", the label for the rest.
            "in_text": str(entry.get("in_text") or label),
            "currency": str(entry.get("currency") or "USD").strip().upper(),
            "date_format": str(entry.get("date_format") or "DMY").strip().upper(),
            "eeo_module": entry.get("eeo_module") or None,
            "work_auth_vocab": str(entry.get("work_auth_vocab") or "generic"),
            # Undeclared reads as today's rule (a state counted, called "State"); every market declares both.
            "asks_state": entry.get("asks_state") is not False,
            "state_label": str(entry.get("state_label") or "State"),
            # The form questions' country data (form_questions.yaml); every market declares each,
            # and undeclared reads as today's rule: no pack, no status list, a postal code counted.
            "packs": _packs(key, entry.get("packs")),
            "work_status": _text(entry.get("work_status")),
            "asks_postcode": entry.get("asks_postcode") is not False,
            "pay": _pay(key, entry.get("pay")),
        }
    return entries


def _text(value: Any) -> str | None:
    return str(value) if value else None


def _packs(key: str, raw: Any) -> list[str]:
    """A market's packs, a YAML list: a bare `packs: gulf` would read as its letters, so it
    fails, naming the market."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"markets.yaml: {key}'s packs must be a list, got {raw!r}")
    return [str(p) for p in raw]


_PAY_PERIODS = ("year", "month")


def _pay(key: str, raw: Any) -> dict[str, str | None]:
    """How a market words expected pay: a label, a hint where its basis needs one, and what a figure
    there is per (`period`, a year when undeclared). Any other period fails, naming the market: a
    misspelt "monthly" read as a year would take a monthly figure for a yearly one."""
    pay = raw if isinstance(raw, dict) else {}
    period = str(pay.get("period") or "year")
    if period not in _PAY_PERIODS:
        raise ValueError(f"markets.yaml: {key}'s pay period must be year or month, got {period!r}")
    return {
        "label": str(pay.get("label") or "Expected salary"),
        "hint": _text(pay.get("hint")),
        "period": period,
    }


def keys() -> list[str]:
    """Supported market keys, in file order."""
    return list(_load().keys())


def labels() -> dict[str, str]:
    """key -> display label."""
    return {k: v["label"] for k, v in _load().items()}


def is_supported(key: str | None) -> bool:
    return bool(key) and str(key).strip().upper() in _load()


def get(key: str | None) -> dict[str, Any]:
    """Resolve a market, falling back to the default.

    Never raises: a stored value for a market later removed from the YAML must
    still render something rather than 500 the profile page. Validation of
    HUMAN input belongs at the API boundary (422), not here — same split as
    `role_categories.normalize` vs the base-resume identity validator.
    """
    resolved = str(key or "").strip().upper()
    entries = _load()
    return entries.get(resolved) or entries[DEFAULT_MARKET]


def country_code(key: str | None) -> str | None:
    """A market key's ISO 3166-1 alpha-2 code ("UK" -> "GB"); None for an unknown key.

    Keys stay as the setting stores them ("UK"); jobs and base resumes store ISO codes, and
    `countries.normalize` is the one bridge (a test pins every key to a country).
    """
    if not is_supported(key):
        return None
    return countries.normalize(str(key).strip().upper())


def for_country(code: str | None) -> str | None:
    """The market for an ISO country code ("GB" -> "UK"), or None when no market covers it."""
    wanted = str(code or "").strip().upper()
    if not wanted:
        return None
    return next((key for key in _load() if country_code(key) == wanted), None)


def currency_for(key: str | None) -> str:
    """Default ISO 4217 code for a market."""
    return get(key)["currency"]


def offers_eeo(key: str | None) -> bool:
    """Whether a VERIFIED EEO question set exists for this market.

    False is the honest answer for most markets and must be surfaced as "not
    offered here", never as an empty form or a silent fallback to the US set.
    A US answer reused on a UK form is factually wrong, not merely imprecise.
    """
    return get(key)["eeo_module"] is not None
