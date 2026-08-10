"""Role-category vocabulary, loaded from data rather than compiled as an enum.

Why this exists: `role_category` used to be a closed 6-value `Literal` covering
four data/AI roles plus `other`/`unknown`. Every role outside that taxonomy —
BI developer, product analyst, research scientist, and all of non-tech — was
forced to `other`, and analytics groups on that column, so unrelated roles piled
into one meaningless bucket.

Three vocabularies had drifted apart:
  * the `RoleCategory` Literal (what could be stored),
  * `title_families.yaml`'s title-cased keys (what the ATS title tier looked
    up — and never matched, making the "adjacent" tier dead in production),
  * `ROLE_CATEGORY_LABELS` (which carried a `hybrid` entry the Literal could
    not produce, and no label for `other`/`unknown`).

All three now derive from `ats/data/role_categories.yaml`. The extraction
prompt's option list is generated from it too, so the prompt cannot drift from
the code. Adding a category for another domain requires no code change.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DATA_FILE = Path(__file__).parent / "ats" / "data" / "role_categories.yaml"

# Always available, never declared in the YAML.
OTHER = "other"
UNKNOWN = "unknown"
RESERVED: dict[str, str] = {OTHER: "Other", UNKNOWN: "Unknown"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_")


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8")) or {}
    entries = raw.get("categories") or []

    labels: dict[str, str] = {}
    families: dict[str, list[str]] = {}
    alias_to_key: dict[str, str] = {}

    for entry in entries:
        key = _slug(entry.get("key"))
        if not key or key in RESERVED:
            continue
        labels[key] = str(entry.get("label") or key.replace("_", " ").title())
        families[key] = [str(t) for t in (entry.get("adjacent") or [])]
        # A key is its own alias, plus its label and any declared aliases.
        for alias in [key, labels[key], *(entry.get("aliases") or [])]:
            alias_to_key.setdefault(_slug(alias), key)

    def _terms(values) -> tuple[str, ...]:
        return tuple(
            term
            for term in (
                " ".join(str(t or "").strip().lower().split()) for t in (values or [])
            )
            if term
        )

    raw_seniority = raw.get("seniority") or {}
    # Tolerate the pre-2026-08-06 flat-list shape: a hand-edited or older YAML
    # must degrade to "everything is always-strip" rather than raising, which
    # would take the whole engine down at import.
    if isinstance(raw_seniority, list):
        always, prefix_only = _terms(raw_seniority), ()
    else:
        always = _terms(raw_seniority.get("always"))
        prefix_only = _terms(raw_seniority.get("prefix_only"))

    return {
        "labels": labels,
        "families": families,
        "aliases": alias_to_key,
        "seniority": always + prefix_only,
        "seniority_always": always,
        "seniority_prefix_only": prefix_only,
    }


def keys() -> list[str]:
    """Declared category keys, in file order. Excludes `other`/`unknown`."""
    return list(_load()["labels"].keys())


def all_keys() -> list[str]:
    """Every storable value: declared categories plus the reserved two."""
    return [*keys(), OTHER, UNKNOWN]


def labels() -> dict[str, str]:
    """key -> display label, including `other`/`unknown`."""
    return {**_load()["labels"], **RESERVED}


def label_for(key: str | None) -> str:
    """Display label for a stored value.

    Never raises and never returns an empty string: an unrecognized value is
    humanized (`bi_developer` -> `Bi Developer`) rather than dropped, so a row
    written before a category was renamed still renders.
    """
    if not key:
        return RESERVED[UNKNOWN]
    return labels().get(key) or str(key).replace("_", " ").title()


def title_families() -> dict[str, list[str]]:
    """role_category key -> adjacent title strings, for the ATS L3 title tier."""
    return dict(_load()["families"])


def seniority_terms() -> tuple[str, ...]:
    """Rank markers that qualify how senior a role is without changing what it is.

    Lowercased and whitespace-collapsed; entries may be multi-word ("entry
    level"). Two consumers compose this differently and must not be merged:
    the ATS L3 title tier strips ONLY these, so that "Senior Data Scientist"
    matches a "Data Scientist" resume; `role_titles.generic_role_title` layers
    management level and niche modifiers on top for its display labels.

    Management titles (`manager`, `director`, `head`, `vp`) deliberately do NOT
    belong here — they name a different job, and stripping them would score
    "Engineering Manager" as a direct match for "Engineer".

    Hashed into the ATS `config_version` (see `ats/config.py::load_config`), so
    editing the YAML invalidates stored scores rather than silently changing
    what a fixed version means.

    This is the COMBINED list. Consumers that strip titles want
    `seniority_always()` and `seniority_prefix_only()` instead — see those.
    """
    return _load()["seniority"]


def seniority_always() -> tuple[str, ...]:
    """Rank markers safe to remove wherever they appear in a title.

    These are never a job on their own: "Senior" and "IV" are not roles.
    """
    return _load()["seniority_always"]


def seniority_prefix_only() -> tuple[str, ...]:
    """Rank markers removed ONLY when they lead the title.

    `associate`, `principal`, `staff` and `lead` double as head nouns —
    "Sales Associate", "Tech Lead", "Team Lead" are the job, not a rank applied
    to one. Stripping them in the suffix position reduced those titles to
    "sales" / "tech" / "team", which match nothing, so the title tier collapsed
    to `none`. Leading them ("Lead Engineer", "Associate Data Scientist") is a
    genuine rank and still strips.
    """
    return _load()["seniority_prefix_only"]


def normalize(value: str | None) -> str:
    """Coerce any inbound value to a canonical key.

    Unrecognized non-empty input becomes `other` rather than being stored
    verbatim — that keeps analytics groupable while the YAML stays the only
    place the vocabulary grows.
    """
    if value is None:
        return UNKNOWN
    slug = _slug(value)
    if not slug:
        return UNKNOWN
    if slug in RESERVED:
        return slug
    return _load()["aliases"].get(slug, OTHER)


def prompt_options() -> str:
    """Pipe-joined option list for the extraction prompt's JSON skeleton."""
    return "|".join([*keys(), OTHER])


def propose_from_resume(data: dict) -> str:
    """Propose a role from resume content — or `unknown` when unsure.

    Deliberately deterministic and deliberately timid. An earlier design wanted
    an LLM inference pass here; it was rejected with proof: the `adjacent` lists
    are one-directional and overlap (``data engineer`` appears under both
    ``data_engineer`` and ``analytics_engineer``; ``research scientist`` under
    both ``data_scientist`` and ``research_scientist``), so any single-winner
    scheme decides ties by YAML file order.

    So this only proposes when the answer is UNAMBIGUOUS — exactly one category
    matches the most recent role title. Anything else returns ``unknown``, which
    the UI shows as "Role not set" with a one-click picker. A visible blank beats
    a plausible wrong answer; the user confirms either way.
    """
    experience = data.get("experience") or []
    titles = [str((e or {}).get("role") or "") for e in experience[:2]]
    if not any(titles):
        return UNKNOWN

    loaded = _load()
    haystack = " ".join(_slug(t).replace("_", " ") for t in titles if t)
    if not haystack.strip():
        return UNKNOWN

    hits: set[str] = set()
    for key, members in loaded["families"].items():
        for member in members:
            if member and member.lower() in haystack:
                hits.add(key)
                break

    # Exactly one category, or nothing. Never a tie-break.
    return next(iter(hits)) if len(hits) == 1 else UNKNOWN
