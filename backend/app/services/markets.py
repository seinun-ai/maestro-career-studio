"""Market vocabulary, loaded from data rather than compiled as an enum.

Why this exists: locale behaviour was scattered and US-shaped. `home_currency`
defaulted to USD with no way to say which country the user actually applies in;
the EEO question set was a hardcoded four-field US list
(`veteran_status`/`disability_status`/`gender`/`hispanic_latino` — the first is
US protected-veteran status, the last is the EEO-1's two-part ethnicity
structure); and the work-auth vocabulary is a US visa taxonomy (`opt`,
`stem_opt`, `h1b`, `tn`).

One `market` setting now drives all three, and the vocabulary lives in
`data/markets.yaml` so adding a market needs no code change — the same contract
`role_categories.yaml` already declares for roles.

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
        entries[key] = {
            "key": key,
            "label": str(entry.get("label") or key),
            "currency": str(entry.get("currency") or "USD").strip().upper(),
            "date_format": str(entry.get("date_format") or "DMY").strip().upper(),
            "eeo_module": entry.get("eeo_module") or None,
            "work_auth_vocab": str(entry.get("work_auth_vocab") or "generic"),
        }
    return entries


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


def eeo_module(key: str | None) -> str | None:
    return get(key)["eeo_module"]


def work_auth_vocab(key: str | None) -> str:
    return get(key)["work_auth_vocab"]
