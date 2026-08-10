"""Degree-level parsing for the ADVISORY education gate.

Scope, deliberately narrow: nothing here feeds the composite. `l4_gate` returns
advisory warnings only (engine.py builds the composite from `subscores` alone),
because every ATS platform surveyed enforces education through an
application-form question rather than through resume parsing. Telling a user to
"go get a Master's" is not actionable advice; telling them a form question is
coming is.

Both sides FAIL SILENT by construction:
  - an unrecognized resume degree returns None -> no warning
  - an unrecognized JD phrasing returns None -> no warning
  - "or equivalent experience" suppresses the line entirely
  - a JD stating several levels is read at its FLOOR (min), so
    "Bachelor's required, Master's preferred" never warns a bachelor's holder

A silent miss costs nothing. A false accusation that someone's real degree does
not qualify is the failure mode worth engineering against, so every ambiguity
resolves toward silence.
"""
import re

# Ordered ladder. Values are compared, never displayed.
ASSOCIATE, BACHELOR, MASTER, DOCTORATE = 1, 2, 3, 4

LEVEL_NAMES = {
    ASSOCIATE: "associate's",
    BACHELOR: "bachelor's",
    MASTER: "master's",
    DOCTORATE: "doctoral",
}

# Matched against dot-stripped, lowercased text with word boundaries. Ordered
# highest-first so "phd" wins before a stray "ms" inside the same string.
_DEGREE_TOKENS: list[tuple[int, tuple[str, ...]]] = [
    (DOCTORATE, ("phd", "dphil", "doctorate", "doctoral", "dsc", "scd", "edd")),
    (MASTER, ("ms", "msc", "ma", "mba", "mtech", "meng", "mfa", "mph", "mstat",
              "master", "masters")),
    (BACHELOR, ("bs", "bsc", "ba", "bba", "btech", "beng", "bcom",
                "bachelor", "bachelors")),
    (ASSOCIATE, ("associate", "associates")),
]

# Phrases that make a stated degree optional. Any of these on a JD line and the
# line stops being a requirement.
_EQUIVALENCE = (
    "or equivalent",
    "equivalent experience",
    "equivalent practical experience",
    "or relevant experience",
    "or comparable",
)


def _normalize(text: str) -> str:
    """Lowercase and strip the dots that make "Ph.D." and "M.S." unmatchable."""
    return re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower().replace(".", ""))


def _level_in(text: str) -> int | None:
    normalized = _normalize(text)
    tokens = set(normalized.split())
    for level, forms in _DEGREE_TOKENS:
        if any(form in tokens for form in forms):
            return level
    return None


def resume_degree_level(education: list) -> int | None:
    """Highest degree level readable from the resume, or None if none parses.

    Reads the `degree` field only — never institution (school prestige must not
    reach the score or any prompt) and never dates (graduation year is the one
    education field with live age-discrimination exposure).
    """
    levels = [
        level
        for entry in education or []
        if isinstance(entry, dict)
        if (level := _level_in(entry.get("degree"))) is not None
    ]
    return max(levels) if levels else None


def required_degree_level(requirement_lines: list[str]) -> int | None:
    """The FLOOR degree level the JD states, or None if it states none.

    Minimum, not maximum: a posting listing "Bachelor's required, Master's
    preferred" has a bachelor's floor, and warning its bachelor's-holding reader
    would be wrong.
    """
    levels: list[int] = []
    for line in requirement_lines or []:
        lowered = str(line).lower()
        if any(phrase in lowered for phrase in _EQUIVALENCE):
            continue
        # only treat a line as a degree requirement when it actually says so;
        # "MS Excel" or "BA in the loop" should not trip the gate
        if "degree" not in lowered and not re.search(
            r"\b(phd|ph\.d|doctorate|master|bachelor|associate)", lowered
        ):
            continue
        level = _level_in(line)
        if level is not None:
            levels.append(level)
    return min(levels) if levels else None
