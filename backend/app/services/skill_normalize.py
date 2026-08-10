"""Canonicalize skill names and constrain skill categories to a fixed enum.

Shared by the JobSkill store path (`routers/jobs.py::_insert_skills`) and the
explore aggregations so casing/spelling variants collapse consistently.
Mirrors the `_coerce_enum` style in
`schemas/job_extraction.py`. Keep the alias map conservative: a bad entry
silently merges two distinct skills.
"""

from __future__ import annotations

from typing import Literal

SkillCategory = Literal[
    "language",
    "framework",
    "library",
    "ml_modeling",
    "nlp_genai",
    "cloud",
    "data_engineering",
    "database",
    "bi_visualization",
    "methodology",
    "tool",
    "domain",
    "soft_skills",
    "certification",
    "other",
]

# Runtime tuple backing the Literal above (single source of truth for membership).
SKILL_CATEGORIES: tuple[str, ...] = (
    "language",
    "framework",
    "library",
    "ml_modeling",
    "nlp_genai",
    "cloud",
    "data_engineering",
    "database",
    "bi_visualization",
    "methodology",
    "tool",
    "domain",
    "soft_skills",
    "certification",
    "other",
)

_CATEGORY_SET = frozenset(SKILL_CATEGORIES)

# Conservative alias map keyed on the already-normalized (casefold + collapsed
# whitespace) name. Only collapse variants that are unambiguously one skill.
_NAME_ALIASES: dict[str, str] = {
    "llm": "large language models",
    "llms": "large language models",
    "large language model": "large language models",
}


def _normalize(value: object) -> str:
    text = str(value or "").strip().casefold()
    # Collapse runs of internal whitespace to a single space.
    return " ".join(text.split())


def coerce_skill_category(cat: object) -> str:
    """Constrain a category to the enum; bucket anything unknown to ``other``."""
    normalized = _normalize(cat)
    if normalized in _CATEGORY_SET:
        return normalized
    return "other"


def canonicalize_skill_name(name: object) -> str:
    """Casefold + strip + collapse whitespace, then apply a conservative alias map."""
    normalized = _normalize(name)
    return _NAME_ALIASES.get(normalized, normalized)
