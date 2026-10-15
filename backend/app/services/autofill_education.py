"""The highest education level the applicant has completed (`derived.education_level`), and a threshold list answered
from it in code.

A form that asks "Which best describes your education?" lists thresholds ("Bachelor's degree or higher",
"Combination of relevant education, experience, and training", "None of the above") that no single saved degree
matches word for word. A level is met by any level above it, so the answer is the highest threshold the applicant
meets; "None of the above" and a combination of experience are never it, and when no threshold is met the user
answers. The level comes from the profile's own degree words (`answer_flags.degree_level`), never inferred from a
school or a job; a degree whose end year is still ahead is not completed."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.answer_flags import degree_level

SLOT = "derived.education_level"
_LEVELS = ("high school", "associate", "bachelor", "master", "doctorate")   # lowest first
_NAMES = {"high school": "High school diploma", "associate": "Associate degree", "bachelor": "Bachelor's degree",
          "master": "Master's degree", "doctorate": "Doctorate"}
_END_KEYS = ("end_year", "end_date", "graduation_date")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# An option about study that is not a completed level, or a ceiling instead of a floor.
_NOT_COMPLETED = re.compile(
    r"\bsome\b|\bless\s+than\b|\bin\s+progress\b|\bcurrently\b|\bpursuing\b|\benrolled\b|\bstudying\b|\bincomplete\b|"
    r"\bno\s+degree\b|\bnot\s+(?:yet\s+)?(?:completed|finished)\b|\bexpected\b|\bworking\s+toward|\battending\b|"
    r"\bor\s+(?:lower|below|less)\b", re.IGNORECASE)
# The option says a level and every level above it meets it.
_OR_HIGHER = re.compile(r"\bor\s+(?:higher|above|more|greater|equivalent)\b|\band\s+(?:above|higher|up)\b|"
                        r"\+|\bat\s+least\b|\bminimum\b|\bplus\b", re.IGNORECASE)


def highest_completed(education: Any, today: date) -> str | None:
    """The fact's value: the highest level named by a degree that is finished (an end year in the future is not;
    no year at all counts, the profile's degree is the claim), else None."""
    entries = [education] if isinstance(education, dict) else education
    ranks = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or (level := degree_level(entry.get("degree") or "")) is None:
            continue
        year = next((m[0] for key in _END_KEYS if (m := _YEAR.search(str(entry.get(key) or "")))), None)
        if year is None or int(year) <= today.year:
            ranks.append(_LEVELS.index(level))
    return _NAMES[_LEVELS[max(ranks)]] if ranks else None


@dataclass(frozen=True)
class Decision:
    oid: str | None       # the option to pick; None: none is
    reason: str           # "matched" | "closest" | "abstained"
    saw_levels: bool      # whether the list named any completed level (a list that names none is not ours to read)


def decide(value: str, options: list[tuple[str, str]], *, complete: bool = True) -> Decision:
    """The option of `options` (id, text) for an applicant whose highest completed level is `value`: the highest
    level the applicant meets. `matched` when it is the applicant's own level or says "or higher"; `closest`
    otherwise (a list with no option for the applicant's own level), which a partial list never makes."""
    mine = degree_level(value)
    named = [(oid, _LEVELS.index(level), bool(_OR_HIGHER.search(text))) for oid, text in options
             if not _NOT_COMPLETED.search(text) and (level := degree_level(text)) is not None]
    if mine is None or not named:
        return Decision(None, "abstained", bool(named))
    met = [n for n in named if n[1] <= _LEVELS.index(mine)]
    if not met:
        return Decision(None, "abstained", True)
    oid, rank, or_higher = max(met, key=lambda n: n[1])   # max keeps the first of equals
    if rank == _LEVELS.index(mine) or or_higher:
        return Decision(oid, "matched", True)
    return Decision(oid, "closest", True) if complete else Decision(None, "abstained", True)
