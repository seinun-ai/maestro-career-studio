"""/sections — which profile list does each repeating section hold, and how
many of its entries can the profile fill?

A repeating section (Work Experience, Education, Websites…) grows only when
its own Add button is pressed, and an added entry's fields are REQUIRED
(notes §5): an entry the profile cannot fill blocks the page. So the loop adds
entries only up to `wanted` — the profile entries of the section's kind that
hold every fact the new entry would require.

One batched Jev Choice per section over code-owned KIND keys (the heading is
page text, offered as data); the fast model does the same job in JSON with a
confidence that must clear the same floor, when the engine is `fast` or a Jev
call fails. Below the floor, refused or unreadable: `none`, and nothing is
added. The model sees headings and entry counts only; the counts come from the
fact catalog here, so no value leaves the machine.

PLACED BY WHAT THE ENTRIES HOLD. An entry already holding data keeps it, and
is matched to the profile entry it holds — on the employer (a job; and its
title, when two jobs share an employer) or the school, normalized. Empty
entries (and entries to add) take the profile entries no entry holds, lowest
first, in page order. `order` says so per entry, and /map writes each entry's
facts from ITS profile entry (`MapField.profile_entry`), so an entry pre-filled
out of profile order is never given a job the page already shows. An Add is
safe only when every entry holding data holds a different profile entry.
An entry holding something the profile does not have may be a profile entry
spelled another way, so its WHOLE section is placed nowhere and nothing is
added (`held_unmatched`, reported even when nothing was to be added); two
entries holding the same one add nothing (`held_twice`). The plan says
why, value-free. What the entries hold (`held`) comes to this
local backend for that match only.
"""

import json
import logging
import re
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import PageSection, SectionKind, SectionPlan
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, SLOT_FLOOR
from app.services.autofill_map import fast_json

logger = logging.getLogger(__name__)

NONE: SectionKind = "none"
KINDS: dict[SectionKind, str] = {
    "experience": "Work experience or employment history: one entry per job the applicant held",
    "education": "Education: one entry per school, college or university the applicant attended",
    "languages": "Languages: one entry per language the applicant speaks",
    "websites": "Websites or links: one entry per personal website, portfolio or GitHub profile",
    "certifications": "Certifications or licenses: one entry per certificate the applicant holds",
    NONE: "None of these: not a list of the applicant's jobs, schools, languages, websites or "
          "certifications, or the heading does not say which",
}
# The facts an added entry cannot be saved without (its REQUIRED fields), per
# kind. An entry missing one is not wanted: Add would leave a required box empty.
_NEEDS: dict[str, tuple[str, ...]] = {"experience": ("employer", "title"), "education": ("school",)}
# One entry each, when the profile holds it. LinkedIn is not here: it has its
# own box (Social Network URLs), never a Websites entry.
_WEBSITES = ("personal.website", "personal.github")
_LLM_PROMPT = """You classify the repeating sections of a job-application form. {rule}
Return JSON {{"sections": {{"<section id>": {{"key": "<key>", "confidence": <0..1>}}}}}} using ONLY these keys:
{kinds}
Sections:
{sections}
"""


def wanted(kind: str, facts: dict[str, Fact]) -> int:
    """How many entries of a kind NOT placed by profile entry the profile can
    fill (jobs and schools are counted by `plan`, from their placement).
    Languages and certifications have no facts yet (languages arrive with the
    profile's Languages list, fill-engine plan Task 10), so none is ever added."""
    if kind == "websites":
        return sum(slot in facts for slot in _WEBSITES)
    return 0


# What names a profile entry, per kind: the value an entry holding it must show.
_NAMED_BY = {"experience": "employer", "education": "school"}
_SUFFIX = re.compile(r"\b(inc|llc|llp|ltd|limited|corp|corporation|co|company|plc|gmbh)\b")


def _norm(text: str) -> str:
    """Casefold, no company suffix (Inc, LLC, Co., GmbH… — dots dropped
    first, so "L.L.C." is "llc"), no punctuation, single spaces."""
    return " ".join(_SUFFIX.sub(" ", re.sub(r"[^\w\s]", " ", text.casefold().replace(".", ""))).split())


def _entries(kind: str, facts: dict[str, Fact]) -> list[int]:
    """The profile's entries of `kind`, by catalog index."""
    return sorted({int(m[1]) for slot in facts if (m := re.fullmatch(rf"{kind}\.(\d+)\..+", slot))})


def _complete(kind: str, i: int, facts: dict[str, Fact]) -> bool:
    return all(f"{kind}.{i}.{need}" in facts for need in _NEEDS[kind])


def _match(kind: str, values: set[str], facts: dict[str, Fact], taken: set[int]) -> int | None:
    """The profile entry an entry holding `values` (normalized) holds, by the
    value that names it: the first not already `taken` when several do. When
    every hit is taken, a TAKEN one is returned — not None — so the caller
    sees a second holding of one entry (a duplicate) rather than a foreign
    entry. None: the profile has no such entry."""
    key = _NAMED_BY[kind]
    hits = []
    for i in _entries(kind, facts):
        name = facts.get(f"{kind}.{i}.{key}")
        if name is None or _norm(str(name.value)) not in values:
            continue
        # Two profile jobs at one employer: the employer cannot say which one
        # the entry holds, so its title must match too.
        if kind == "experience" and _shares_employer(i, facts):
            title = facts.get(f"experience.{i}.title")
            if title is None or _norm(str(title.value)) not in values:
                continue
        hits.append(i)
    return next((i for i in hits if i not in taken), hits[0] if hits else None)


class Placement(NamedTuple):
    """Per page entry, the profile entry it holds or is given (None: a second
    holding of one, past the profile, or every entry of a section holding a
    foreign one); the profile entries no entry holds or is given, left for
    entries to add; whether every entry holding data holds a different
    profile entry; and whether one holds something the profile does not have."""

    order: list[int | None]
    free: list[int]
    safe: bool
    foreign: bool


def place(section: PageSection, kind: str, facts: dict[str, Fact]) -> Placement:
    held: dict[int, int | None] = {}
    taken: set[int] = set()
    foreign = False
    for j in range(section.entries):
        values = section.held[j] if j < len(section.held) else []
        if not ((section.filled[j] if j < len(section.filled) else False) or values):
            continue
        # A value that normalizes to nothing ("Inc.") names nothing.
        i = _match(kind, {_norm(v) for v in values} - {""}, facts, taken)
        foreign = foreign or i is None
        if i is None or i in taken:
            held[j] = None
        else:
            held[j] = i
            taken.add(i)
    if foreign:
        return Placement([None] * section.entries, [], False, True)
    free = [i for i in _entries(kind, facts) if i not in taken]
    order: list[int | None] = []
    for j in range(section.entries):
        if j in held:
            order.append(held[j])
        elif free:
            order.append(free[0])
            free = free[1:]
        else:
            order.append(None)
    return Placement(order, free, None not in held.values(), False)


def _shares_employer(j: int, facts: dict[str, Fact]) -> bool:
    employers = {slot: _norm(str(f.value)) for slot, f in facts.items()
                 if re.fullmatch(r"experience\.\d+\.employer", slot)}
    mine = employers.get(f"experience.{j}.employer")
    return sum(e == mine for e in employers.values()) > 1


def _payload(sections: list[PageSection]) -> list[dict]:
    return [{"id": s.sid, "heading": s.heading, "entries": s.entries} for s in sections]


def _with_jev(sections: list[PageSection], session: Session) -> dict[str, tuple[str, float]]:
    questions = {
        s.sid: jev.choice_question(
            f"Which list of the applicant's does the repeating form section {s.sid} (headed "
            f"{json.dumps(s.heading)}) hold? Each entry of it holds one item of that kind. Answer none "
            "unless the heading names one. " + _PAGE_TEXT_IS_DATA, dict(KINDS))
        for s in sections
    }
    answers = jev.decide(questions, {"sections": _payload(sections)}, session)
    out = {}
    for s in sections:
        if picked := jev.choice_of(answers.get(s.sid), KINDS):
            out[s.sid] = (picked.choice, picked.probability)
    return out


def _with_llm(sections: list[PageSection], session: Session) -> dict[str, tuple[str, float]]:
    raw = fast_json(session, _LLM_PROMPT.format(
        rule=_PAGE_TEXT_IS_DATA, kinds="\n".join(f"- {k}: {v}" for k, v in KINDS.items()),
        sections=json.dumps(_payload(sections))), "autofill-sections")
    got = raw.get("sections") if isinstance(raw, dict) else None
    asked = {s.sid for s in sections}
    out = {}
    for sid, entry in (got.items() if isinstance(got, dict) else ()):
        if sid not in asked or not isinstance(entry, dict):
            continue
        key, conf = entry.get("key"), entry.get("confidence")
        if isinstance(key, str) and key in KINDS and jev._unit(conf):
            out[sid] = (key, float(conf))
    return out


def plan(sections: list[PageSection], facts: dict[str, Fact], session: Session) -> dict[str, SectionPlan]:
    picked = None
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            picked = _with_jev(sections, session)
        except llm.LLMProviderError:
            logger.warning("jev sections failed; the fast model classifies them")
    if picked is None:
        picked = _with_llm(sections, session)
    out = {}
    for s in sections:
        kind, p = picked.get(s.sid, (NONE, 0.0))
        kind = kind if p >= SLOT_FLOOR else NONE
        if kind not in _NAMED_BY:
            out[s.sid] = SectionPlan(kind=kind, wanted=wanted(kind, facts))
            continue
        placed = place(s, kind, facts)
        # Added entries take the free profile entries that hold every fact an
        # entry requires, in order: one missing a fact is skipped (placed by
        # profile entry, a gap is no wall).
        add = [i for i in placed.free if _complete(kind, i, facts)]
        if placed.foreign:
            out[s.sid] = SectionPlan(kind=kind, wanted=s.entries, reason="held_unmatched", order=placed.order)
        elif add and not placed.safe:
            out[s.sid] = SectionPlan(kind=kind, wanted=s.entries, reason="held_twice", order=placed.order)
        else:
            out[s.sid] = SectionPlan(kind=kind, wanted=s.entries + len(add), order=placed.order + add)
    return out
