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

RECONCILED FIRST. An entry already holding data keeps it, and /map places
entries by page order (entry n ↔ profile entry n). So an Add is safe only when
every entry holding data holds the profile entry of ITS position — matched on
the employer (a job; and its title, when two jobs share an employer) or the
school, normalized. Otherwise the added entry
would repeat a profile entry already on the page: nothing is added (`wanted`
is at most the entries there) and the plan says why, value-free. What the
entries hold (`held`) comes to this local backend for that match only.
"""

import json
import logging
import re

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
    """How many entries of `kind` the profile can fill. Languages and
    certifications have no facts yet (languages arrive with the profile's
    Languages list, fill-engine plan Task 10), so none is ever added."""
    if kind == "websites":
        return sum(slot in facts for slot in _WEBSITES)
    needs = _NEEDS.get(kind)
    if not needs:
        return 0
    entries = {m[1] for slot in facts if (m := re.fullmatch(rf"{kind}\.(\d+)\.\w+", slot))}
    return sum(all(f"{kind}.{i}.{need}" in facts for need in needs) for i in entries)


# What names a profile entry, per kind: the value an entry holding it must show.
_NAMED_BY = {"experience": "employer", "education": "school"}
_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp)\b")


def _norm(text: str) -> str:
    """Casefold, no punctuation, no Inc/LLC/Ltd/Corp, single spaces."""
    return " ".join(_SUFFIX.sub(" ", re.sub(r"[^\w\s]", " ", text.casefold())).split())


def _in_place(section: PageSection, kind: str, facts: dict[str, Fact]) -> bool:
    """Whether every entry holding data holds the profile entry of its own
    position (by the value that names it). A kind named by nothing (websites)
    is not placed by position, so there is nothing to check."""
    key = _NAMED_BY.get(kind)
    if not key:
        return True
    for j in range(section.entries):
        held = section.held[j] if j < len(section.held) else []
        filled = (section.filled[j] if j < len(section.filled) else False) or bool(held)
        if not filled:
            continue
        name = facts.get(f"{kind}.{j}.{key}")
        values = {_norm(h) for h in held}
        if name is None or _norm(str(name.value)) not in values:
            return False
        # Two profile jobs at one employer: the employer cannot say which one
        # the entry holds, so its title must match too.
        if kind == "experience" and _shares_employer(j, facts):
            title = facts.get(f"experience.{j}.title")
            if title is None or _norm(str(title.value)) not in values:
                return False
    return True


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
        want = wanted(kind, facts)
        if want > s.entries and not _in_place(s, kind, facts):
            out[s.sid] = SectionPlan(kind=kind, wanted=s.entries, reason="held_out_of_order")
        else:
            out[s.sid] = SectionPlan(kind=kind, wanted=want)
    return out
