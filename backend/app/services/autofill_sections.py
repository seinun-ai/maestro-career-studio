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
        out[s.sid] = SectionPlan(kind=kind, wanted=wanted(kind, facts))
    return out
