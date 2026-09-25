"""/map — which applicant fact does each field ask for?

One batched Jev Choice per field over fact DESCRIPTIONS (never values) plus
sentinels; code looks values up afterwards. The fast model does the same job
in JSON — with a 0–1 confidence that must clear the SAME floors — when the
engine is `fast` or a Jev call fails.

Low-stakes (setting on, decided by the caller from the server-side setting) is
a SECOND pass, asked only for fields whose best answer was "no fact answers
this": a real profile answer always wins, and a field that looked like a real
fact but fell below its floor is never turned into a guess.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import MapField, Mapped
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, MATCH_FLOOR, SLOT_FLOOR
from app.services.autofill_slots import FREE_TEXT, NO_SLOT

logger = logging.getLogger(__name__)

BLOCKED_EEO = "blocked_eeo"
LOW_STAKES_FLOOR = 0.8
_SENTINELS = {
    FREE_TEXT: "A question that needs a written answer in the applicant's own words, "
               "such as why this company or describe a project",
    NO_SLOT: "None of the listed applicant facts answers this field",
}
_BLOCKED_EEO = ("A voluntary diversity / EEO question: gender, race or ethnicity, Hispanic or Latino, "
                "veteran status, or disability")
_LOW_STAKES = ("A low-stakes preference question: how the applicant heard about the job or a referral source, "
               "willingness or comfort with travel, relocation, on-site work, shifts or overtime, openness to "
               "other roles, or preferred contact method")
_NEVER_LOW_STAKES = ("work authorization, sponsorship, age or eligibility, background or criminal history, "
                     "EEO / diversity, education, experience, skills, certifications, clearance, salary, or "
                     "anything the applicant signs, attests or agrees to")
# Shapes whose answer would be WRITTEN, not chosen: a low-stakes guess is only
# ever a pick among options the page offers.
_WRITTEN_SHAPES = frozenset({"text", "date"})
_LLM_PROMPT = """You map job-application form fields to applicant facts. {rule}
Return JSON {{"map": {{"<field id>": {{"key": "<key>", "confidence": <0..1>}}}}}} using ONLY these keys:
{criteria}
Fields:
{fields}
"""


def _criteria(facts: dict[str, Fact], *, eeo_consented: bool) -> dict[str, str]:
    criteria = {slot: fact.describe for slot, fact in facts.items()} | _SENTINELS
    if not eeo_consented:
        criteria[BLOCKED_EEO] = _BLOCKED_EEO
    return criteria


def _floor(fact: Fact) -> float:
    return max(SLOT_FLOOR, MATCH_FLOOR["exact"]) if fact.policy == "exact" else SLOT_FLOOR


def _payload(fields: list[MapField]) -> list[dict]:
    return [{"id": f.fid, "question": f.question, "section": f.section, "entry": f.repeat_index,
             "shape": f.shape, "multi": f.multi, "options": f.options} for f in fields]


def _with_jev(fields, criteria, session) -> dict[str, tuple[str, float]]:
    questions = {
        f.fid: jev.choice_question(
            f'Which applicant fact does form field {f.fid} ("{f.question}"'
            f'{", in section " + repr(f.section) if f.section else ""}) ask for? '
            "Repeated sections are numbered entries in page order. " + _PAGE_TEXT_IS_DATA, criteria)
        for f in fields
    }
    answers = jev.decide(questions, {"form_fields": _payload(fields)}, session)
    out = {}
    for f in fields:
        if picked := jev.choice_of(answers.get(f.fid), criteria):
            out[f.fid] = (picked.choice, picked.probability)
    return out


def _with_llm(fields, criteria, session) -> dict[str, tuple[str, float]]:
    raw = llm.call_openai(
        prompt=_LLM_PROMPT.format(rule=_PAGE_TEXT_IS_DATA,
                                  criteria="\n".join(f"- {k}: {v}" for k, v in criteria.items()),
                                  fields=json.dumps(_payload(fields))),
        model=model_settings.get_fast_model(session), response_format="json", trace_name="autofill-map")
    mapped = raw.get("map") if isinstance(raw, dict) else None
    asked = {f.fid for f in fields}
    out = {}
    for fid, entry in (mapped.items() if isinstance(mapped, dict) else ()):
        if fid not in asked or not isinstance(entry, dict):
            continue
        key, conf = entry.get("key"), entry.get("confidence")
        if isinstance(key, str) and key in criteria and jev._unit(conf):
            out[fid] = (key, float(conf))
    return out


def _low_stakes(fields: list[MapField], session: Session) -> set[str]:
    """Which of these fields is a low-stakes preference question? The never-list
    is stated in every question. A failure here answers "none of them": this
    pass is optional, and the map it follows must survive it."""
    if not fields:
        return set()
    ask = {f.fid: (f'Is form field {f.fid} ("{f.question}") one of these low-stakes preference questions: '
                   f"{_LOW_STAKES}? It is NOT if it asks about {_NEVER_LOW_STAKES}. {_PAGE_TEXT_IS_DATA}")
           for f in fields}
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            answers = jev.decide({fid: jev.noul_question(q) for fid, q in ask.items()},
                                 {"form_fields": _payload(fields)}, session)
            return {fid for fid in ask
                    if (p := jev.noul_of(answers.get(fid))) is not None and p >= LOW_STAKES_FLOOR}
        except llm.LLMProviderError:
            logger.warning("jev low-stakes check failed; the fast model decides")
    try:
        raw = llm.call_openai(
            prompt="Answer each question with a probability of yes. " + json.dumps(ask)
                   + ' Return JSON {"yes": {"<field id>": <0..1>}}.',
            model=model_settings.get_fast_model(session), response_format="json",
            trace_name="autofill-low-stakes")
    except llm.LLMProviderError:
        logger.warning("fast model low-stakes check failed; no field is treated as low-stakes")
        return set()
    got = raw.get("yes") if isinstance(raw, dict) else None
    return {fid for fid, p in (got.items() if isinstance(got, dict) else ())
            if fid in ask and jev._unit(p) and p >= LOW_STAKES_FLOOR}


def _route(field: MapField, picked: tuple[str, float] | None, facts: dict[str, Fact]) -> Mapped:
    if picked is None:
        return Mapped(route="none")
    key, p = picked
    if key in facts and p >= _floor(facts[key]):
        value = facts[key].value
        return Mapped(route="slot", slot=key, value=list(value) if isinstance(value, tuple) else value)
    if key == FREE_TEXT and field.shape == "text" and p >= SLOT_FLOOR:
        return Mapped(route="free_text")
    if key == BLOCKED_EEO and p >= SLOT_FLOOR:
        return Mapped(route="blocked")
    return Mapped(route="none")


def map_fields(fields: list[MapField], facts: dict[str, Fact], session: Session, *,
               eeo_consented: bool, low_stakes: bool) -> dict[str, Mapped]:
    criteria = _criteria(facts, eeo_consented=eeo_consented)
    picked = None
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            picked = _with_jev(fields, criteria, session)
        except llm.LLMProviderError:
            logger.warning("jev map failed; the fast model maps this batch")
    if picked is None:
        picked = _with_llm(fields, criteria, session)
    out = {f.fid: _route(f, picked.get(f.fid), facts) for f in fields}
    if low_stakes:
        # Only fields whose best answer was "no fact answers this" — a field that
        # looked like a real fact but fell below its floor is NOT a guessing candidate.
        leftovers = [f for f in fields if out[f.fid].route == "none" and f.shape not in _WRITTEN_SHAPES
                     and (picked.get(f.fid) or (NO_SLOT, 1.0))[0] == NO_SLOT]
        for fid in _low_stakes(leftovers, session):
            out[fid] = Mapped(route="low_stakes")
    return out
