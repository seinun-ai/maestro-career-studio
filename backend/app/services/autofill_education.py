"""The highest education level the applicant has completed (`derived.education_level`), and a threshold list answered
from it in code.

A form that asks "Which best describes your education?" lists thresholds ("Bachelor's degree or higher",
"Combination of relevant education, experience, and training", "None of the above") that no single saved degree
matches word for word. A level is met by any level above it, so the answer is the highest threshold the applicant
meets; "None of the above" and a combination of experience are never it, and when no threshold is met the user
answers. The level comes from the profile's own degree words (`answer_flags.degree_level`), never inferred from a
school or a job; a degree still in progress (a candidate, a student, an end date ahead, "present") is not completed.
An option counts only when it names a level and nothing else (a degree TYPE such as "BA", or a field such as
"in Computer Science or related field", is not a threshold), a denial ("I do not have a Bachelor's") is never a
level, an option naming two levels is met at the lowest, and a list whose winning level has several options or a
field-tied one is left to the ordinary path (nothing is claimed).

A list of degree TYPES ("Degree": Associate's Degree, Bachelor's Degree, Master of Business Administration (M.B.A.),
Master's Degree, …) is read the same way from the saved degree's own words (`degree_type`): a saved Masters, MS, M.S.
or M.Sc takes the generic "Master's Degree"; the MBA option only when the saved degree says Business Administration or
MBA. The generic option is true of any degree at that level, so it is a match, not a guess."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.answer_flags import _LEVEL_ONLY_RE, _NO_FIELD, _WITH_FIELD_RE, _fold
from app.services.autofill_catalog import ym

SLOT = "derived.education_level"
_LEVELS = ("high school", "associate", "bachelor", "master", "doctorate")   # lowest first
_NAMES = {"high school": "High school diploma", "associate": "Associate degree", "bachelor": "Bachelor's degree",
          "master": "Master's degree", "doctorate": "Doctorate"}
_END_KEYS = ("end_year", "end_date", "graduation_date")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# Study that is not a completed level: a denial, a student or candidate, an unfinished or ongoing degree, a ceiling.
_NOT_COMPLETED = re.compile(
    r"\bno\b|\bnot\b|\bwithout\b|\bnever\b|n['\u2019]t\b|\bsome\b|\bless\s+than\b|\bup\s+to\b|"
    r"\bor\s+(?:lower|below|less)\b|\bstudents?\b|\bcandidates?\b|\bin\s+progress\b|\bcurrent(?:ly)?\b|"
    r"\bpresent\b|\bongoing\b|\bpursu\w*|\benroll\w*|\bexpect\w*|\bincomplete\b|\bunfinished\b|"
    r"\bworking\s+toward|\battending\b|\bdrop(?:ped)?[\s-]?out\b", re.IGNORECASE)
# The option says a level and every level above it meets it.
_OR_HIGHER = re.compile(r"\bor\s+(?:higher|above|more|greater|equivalent)\b|\band\s+(?:above|higher|up)\b|"
                        r"\+|\bat\s+least\b|\bminimum\b|\bplus\b", re.IGNORECASE)
# Words an option may add to a level and still be the level alone.
_PLAIN = _NO_FIELD | {"higher", "above", "more", "greater", "up", "plus", "at", "least", "minimum", "experience", "i",
                      "have", "has", "hold", "completed", "earned", "with"}
# Engineering degrees the shared reader has no word for. Case-sensitive on the profile's own degree text only: "be"
# and "me" are English.
_PROFILE_EXTRA = (("bachelor", re.compile(r"(?<![\w.'-])B\.?\s?E\.?(?!\w)")),
                  ("master", re.compile(r"(?<![\w.'-])M\.?\s?E\.?(?!\w)|(?<![\w.'-])(?i:M\.?\s?Tech)\b")))


def _levels_named(text: str) -> list[str]:
    return [lv for lv in _LEVELS if _LEVEL_ONLY_RE[lv].search(text)
            or (lv in _WITH_FIELD_RE and _WITH_FIELD_RE[lv].search(text))]


def _plain(text: str) -> bool:
    """Whether `text` says a level and nothing else: no field, no degree type, no abbreviation that carries a field."""
    if any(rx.search(text) for rx in _WITH_FIELD_RE.values()):
        return False
    for rx in _LEVEL_ONLY_RE.values():
        text = rx.sub(" ", text)
    return all(word in _PLAIN for word in _fold(text).split())


def _profile_level(degree: Any) -> str | None:
    """The level a profile's degree words name (the lowest, if they name several), None for a degree still in progress."""
    text = str(degree or "")
    if _NOT_COMPLETED.search(text):
        return None
    named = _levels_named(text) + [lv for lv, rx in _PROFILE_EXTRA if rx.search(text)]
    return min(named, key=_LEVELS.index) if named else None


def _finished(entry: dict, today: date) -> bool:
    """Whether the entry's end has come: a month (2026-12) compares by month, a year alone counts this year, no end at
    all counts (the profile's degree is the claim), and "present" or the like does not."""
    for key in _END_KEYS:
        raw = str(entry.get(key) or "")
        if not raw.strip():
            continue
        if _NOT_COMPLETED.search(raw):
            return False
        if (month := ym(raw)) and len(month) == 7:
            return month <= today.strftime("%Y-%m")
        if year := _YEAR.search(raw):
            return int(year[0]) <= today.year
    return True


def highest_completed(education: Any, today: date) -> str | None:
    """The fact's value: the highest level named by a finished degree, else None."""
    entries = [education] if isinstance(education, dict) else education
    ranks = [_LEVELS.index(level) for entry in (entries if isinstance(entries, list) else [])
             if isinstance(entry, dict) and (level := _profile_level(entry.get("degree"))) and _finished(entry, today)]
    return _NAMES[_LEVELS[max(ranks)]] if ranks else None


@dataclass(frozen=True)
class Decision:
    oid: str | None       # the option to pick; None: none is
    reason: str           # "matched" | "closest" | "abstained"
    saw_levels: bool      # whether the list named any completed level (a list that names none is not ours to read)


def decide(value: str, options: list[tuple[str, str]], *, complete: bool = True) -> Decision:
    """The option of `options` (id, text) for an applicant whose highest completed level is `value`: the highest
    level the applicant meets. `matched` when it is the applicant's own level or says "or higher"; `closest`
    otherwise (a list with no option for the applicant's own level), which a partial list never makes. A winning
    level with several options, or whose option names a field or a degree type, is nobody's pick."""
    named = []   # (oid, rank of the lowest level named, plain, or higher)
    for oid, text in options:
        if _NOT_COMPLETED.search(text) or not (levels := _levels_named(text)):
            continue
        named.append((oid, min(_LEVELS.index(lv) for lv in levels), _plain(text), bool(_OR_HIGHER.search(text))))
    mine = _levels_named(value)
    if not mine or not named:
        return Decision(None, "abstained", bool(named))
    rank = _LEVELS.index(mine[0])
    met = [n for n in named if n[1] <= rank]
    if not met:
        return Decision(None, "abstained", True)
    top = max(n[1] for n in met)
    winners = [n for n in met if n[1] == top]
    if len(winners) != 1 or not winners[0][2]:
        return Decision(None, "abstained", True)
    oid, _, _, or_higher = winners[0]
    if top == rank or or_higher:
        return Decision(oid, "matched", True)
    return Decision(oid, "closest", True) if complete else Decision(None, "abstained", True)


_MBA = re.compile(r"(?<![\w.'-])M\.?\s?B\.?\s?A\b|business\s+administration", re.IGNORECASE)


def _level_named(text: str) -> list[str]:
    """The levels a degree text names (a profile's or an option's), engineering abbreviations included."""
    return sorted({*_levels_named(text), *(lv for lv, rx in _PROFILE_EXTRA if rx.search(text))}, key=_LEVELS.index)


def degree_type(value: str, options: list[tuple[str, str]], *, complete: bool = True) -> Decision | None:
    """The option of a degree-TYPE list for the saved degree `value`, or None when this rule has no say (no option
    names only one level, as "Master's Degree" does: the ordinary pick decides). The generic option for the saved
    level; an MBA option only when `value` says MBA or Business Administration (else the generic one, or on a
    partial list nobody: the MBA may be unseen). Ambiguous (several generic options for the level, or a degree that
    names several levels) abstains."""
    generic: dict[str, list[str]] = {}
    mba: list[str] = []
    for oid, text in options:
        if _NOT_COMPLETED.search(text) or len(levels := _level_named(text)) != 1:
            continue
        if _plain(text):
            generic.setdefault(levels[0], []).append(oid)
        elif levels[0] == "master" and _MBA.search(text):
            mba.append(oid)
    if not generic:
        return None
    mine = _level_named(value)
    if len(mine) != 1 or len(generic.get(mine[0], [])) > 1:
        return Decision(None, "abstained", True)
    if mine[0] == "master" and _MBA.search(value):
        if mba:
            return Decision(mba[0], "matched", True) if len(mba) == 1 else Decision(None, "abstained", True)
        if not complete:
            return Decision(None, "abstained", True)
    return Decision(generic[mine[0]][0], "matched", True) if mine[0] in generic else None
