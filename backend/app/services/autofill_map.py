"""/map — which applicant fact does each field ask for?

One batched Jev Choice per field over fact DESCRIPTIONS (never values) plus
sentinels; code looks values up afterwards. The fast model does the same job
in JSON — with a 0–1 confidence that must clear the SAME floors — when the
engine is `fast` or a Jev call fails.

Low-stakes (setting on, decided by the caller from the server-side setting) is
a SECOND pass, asked only for fields whose best answer was an explicit,
confident "no fact answers this": a real profile answer always wins, and a
field that looked like a real fact but fell below its floor, that the model
did not answer readably, or that it named a protected kind (work
authorization, eligibility, background, EEO) is never turned into a guess.

The REASONING pass (`reasoned`, whatever the low-stakes setting) comes last:
a choice field still routed none, whose map answer was an explicit, confident
"no fact" or "an unanswered protected question", and that the fast model
judges answerable from the work and education history — past employment by a
kind of organization, a clearance, years of experience with something. The
question DESCRIBES the history and never sends it; /pick answers from it.
"""

import json
import logging
import re
from typing import get_args

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import EntryKind, Format, MapField, Mapped
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, MATCH_FLOOR, SLOT_FLOOR
from app.services.autofill_slots import FREE_TEXT, NO_SLOT

logger = logging.getLogger(__name__)

BLOCKED_EEO = "blocked_eeo"
PROTECTED_UNANSWERED = "protected_unanswered"
LOW_STAKES_FLOOR = 0.8
ANSWERABLE_FLOOR = 0.8
_SENTINELS = {
    FREE_TEXT: "A question that needs a written answer in the applicant's own words, "
               "such as why this company or describe a project",
    NO_SLOT: "None of the listed applicant facts or question kinds fits this field",
    # Offered in EVERY question, so a knockout question the profile cannot
    # answer has somewhere to go that is not "none" (a low-stakes candidate).
    PROTECTED_UNANSWERED: "A work-authorization, sponsorship, age or eligibility, or background-check "
                          "question that none of the listed applicant facts answers",
    # Always offered too: without consent it marks the field `blocked`; with
    # consent the EEO facts are listed, and choosing this means none answers it.
    BLOCKED_EEO: "A voluntary diversity / EEO question (gender, race or ethnicity, Hispanic or Latino, "
                 "veteran status, or disability) that none of the listed applicant facts answers",
}
# The owner's scope (2026-09-26): answered in the job's favour when the
# setting is on and no profile fact answers. Self-assessments against the job
# description and contact consents are IN; factual entries are not.
_LOW_STAKES = ("A low-stakes question an applicant keen on this job would answer in its favor: how the applicant "
               "heard about the job or a referral source; preferred contact method; willingness or comfort with "
               "relocation, travel (any share of time), on-site work, shifts, overtime or a drug test; openness to "
               "other roles; whether the applicant is related to, or was previously employed by, the company "
               "(answered No); what the applicant would do if employed by the company; consent to be contacted "
               "by SMS, automated calls or texts, or marketing messages; or a yes/no self-assessment against the "
               "job description, such as having the required experience or meeting the educational requirement")
_NEVER_LOW_STAKES = ("factual education or experience questions (a school, degree, employer, title, date, "
                     "certification, or years of experience with something), work authorization, sponsorship, "
                     "age or eligibility facts, EEO / diversity, background or criminal history, security "
                     "clearance, salary, or a legal attestation or signature")
# What the reasoning route may read (autofill_pick._history sends exactly
# these, never a name, contact detail, address or EEO answer).
_REASONED_FROM = ("the applicant's work history (each job's employer, title, dates, whether it is current, and "
                  "description) and education (each school, degree, major and years)")
_NEVER_REASONED = ("work authorization, sponsorship, age, EEO / diversity, background or criminal history, salary, "
                   "a preference or willingness, a comparison with the job description's requirements, or a legal "
                   "attestation or signature")
# Shapes whose answer would be WRITTEN, not chosen: a low-stakes guess is only
# ever a pick among options the page offers.
_WRITTEN_SHAPES = frozenset({"text", "date"})
_LLM_PROMPT = """You map job-application form fields to applicant facts. {rule}
Return JSON {{"map": {{"<field id>": {{"key": "<key>", "confidence": <0..1>}}}}}} using ONLY these keys:
{criteria}
Fields:
{fields}
"""


def _criteria(facts: dict[str, Fact]) -> dict[str, str]:
    return {slot: fact.describe for slot, fact in facts.items()} | _SENTINELS


def _floor(fact: Fact) -> float:
    return max(SLOT_FLOOR, MATCH_FLOOR["exact"]) if fact.policy == "exact" else SLOT_FLOOR


def _payload(fields: list[MapField]) -> list[dict]:
    # `entry`: the profile entry a placed entry holds (a number, no value), so
    # the model is not sent looking for a fourth job on a page's fourth entry;
    # else the page's own entry number.
    return [{"id": f.fid, "question": f.question, "section": f.section,
             "entry": f.repeat_index if f.profile_entry is None else f.profile_entry,
             "shape": f.shape, "multi": f.multi, "options": f.options} for f in fields]


def _with_jev(fields, criteria, session) -> dict[str, tuple[str, float]]:
    questions = {
        f.fid: jev.choice_question(
            f"Which applicant fact does form field {f.fid} ({json.dumps(f.question)}"
            f'{", in section " + json.dumps(f.section) if f.section else ""}) ask for? '
            "Repeated sections are numbered entries (see each field's entry). " + _PAGE_TEXT_IS_DATA, criteria)
        for f in fields
    }
    answers = jev.decide(questions, {"form_fields": _payload(fields)}, session)
    out = {}
    for f in fields:
        if picked := jev.choice_of(answers.get(f.fid), criteria):
            out[f.fid] = (picked.choice, picked.probability)
    return out


def fast_json(session: Session, prompt: str, trace_name: str) -> object:
    """One fast-model JSON call. JSON that stays malformed after the client's
    retries is a provider failure (a 502 with a detail), not a crash."""
    try:
        return llm.call_openai(prompt=prompt, model=model_settings.get_fast_model(session),
                               response_format="json", trace_name=trace_name)
    except ValueError as exc:
        raise llm.LLMProviderError("The AI model sent an answer we couldn't read.", str(exc)) from exc


def _with_llm(fields, criteria, session) -> dict[str, tuple[str, float]]:
    raw = fast_json(session, _LLM_PROMPT.format(
        rule=_PAGE_TEXT_IS_DATA, criteria="\n".join(f"- {k}: {v}" for k, v in criteria.items()),
        fields=json.dumps(_payload(fields))), "autofill-map")
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


def _fast_yes(ask: dict[str, str], floor: float, session: Session, trace_name: str) -> set[str]:
    """The fast model's yes, per question, at `floor`. A failure answers "none
    of them": a second pass is optional, and the map it follows must survive it."""
    try:
        raw = fast_json(session, "Answer each question with a probability of yes. " + json.dumps(ask)
                        + ' Return JSON {"yes": {"<field id>": <0..1>}}.', trace_name)
    except llm.LLMProviderError:
        logger.warning("fast model %s check failed; no field is taken", trace_name)
        return set()
    got = raw.get("yes") if isinstance(raw, dict) else None
    return {fid for fid, p in (got.items() if isinstance(got, dict) else ())
            if fid in ask and jev._unit(p) and p >= floor}


def _low_stakes(fields: list[MapField], session: Session) -> set[str]:
    """Which of these fields is a low-stakes question? The never-list is
    stated in every question."""
    if not fields:
        return set()
    ask = {f.fid: (f"Is form field {f.fid} ({json.dumps(f.question)}) one of these low-stakes questions: "
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
    return _fast_yes(ask, LOW_STAKES_FLOOR, session, "autofill-low-stakes")


def _answerable(fields: list[MapField], session: Session) -> set[str]:
    """Which of these fields the work and education history can answer. The
    fast model only, on every engine: this route's /pick needs the history as
    values, which Jev's state would then carry, so Jev judges none of it."""
    if not fields:
        return set()
    ask = {f.fid: (f"Can form field {f.fid} ({json.dumps(f.question)}) be answered from {_REASONED_FROM} alone, "
                   "such as past employment by a kind of organization, a security clearance, or years of "
                   f"experience with something? It cannot if it asks about {_NEVER_REASONED}. {_PAGE_TEXT_IS_DATA}")
           for f in fields}
    return _fast_yes(ask, ANSWERABLE_FLOOR, session, "autofill-reasoned")


_PHONE = re.compile(r"phone", re.IGNORECASE)
_MONEY = re.compile(r"(^|[._])(desired_)?(salary|compensation|pay)([._]|$)", re.IGNORECASE)
_ENTRY = re.compile(rf"({'|'.join(get_args(EntryKind))})\.(\d+)\.(.+)")


def format_of(slot: str | None) -> Format | None:
    """How a value written for `slot` compares with what the page shows: a
    page re-punctuates a phone number, and writes "$80,000" for 80000."""
    if not slot:
        return None
    if _PHONE.search(slot):
        return "phone"
    return "money" if _MONEY.search(slot) else None


def _foreign(field: MapField) -> bool:
    """An entry /sections placed at NO profile entry (`profile_entry` sent as
    null): it holds something the profile does not have, or lies past it."""
    return "profile_entry" in field.model_fields_set and field.profile_entry is None


def _placed_key(field: MapField, key: str) -> str | None:
    """Where an entry sits in the profile is code's (/sections matched what the
    entries hold), never the model's: an entry fact's number becomes the
    entry's `profile_entry`, whatever number the model chose. None: a fact of
    another kind than the section holds."""
    m = _ENTRY.fullmatch(key)
    if m is None or field.profile_entry is None:
        return key
    # An entry fact of another kind than the section's is not this entry's.
    if field.entry_kind is not None and m[1] != field.entry_kind:
        return None
    return f"{m[1]}.{field.profile_entry}.{m[3]}"


def _route(field: MapField, picked: tuple[str, float] | None, facts: dict[str, Fact], *,
           eeo_consented: bool) -> Mapped:
    if picked is None or _foreign(field):
        return Mapped(route="none")
    key, p = picked
    if key in facts and p >= _floor(facts[key]):
        key = _placed_key(field, key)
        if key is None or key not in facts:
            return Mapped(route="none")
        value = facts[key].value
        return Mapped(route="slot", slot=key, value=list(value) if isinstance(value, tuple) else value,
                      format=format_of(key))
    if key == FREE_TEXT and field.shape == "text" and p >= SLOT_FLOOR:
        return Mapped(route="free_text")
    if key == BLOCKED_EEO and not eeo_consented and p >= SLOT_FLOOR:
        return Mapped(route="blocked")
    return Mapped(route="none")


def _said_no_fact(picked: tuple[str, float] | None, *, protected: bool = False) -> bool:
    """An EXPLICIT, confident "no fact answers this". An omitted, refused or
    unsure answer, a fact below its floor and a protected kind all say
    something else, and none of them is a guessing candidate. `protected`:
    an unanswered protected question counts too — for the reasoning route,
    which answers only from what the history shows (a clearance, a government
    employer), never for a guess."""
    key, p = picked or (None, 0.0)
    return (key == NO_SLOT or (protected and key == PROTECTED_UNANSWERED)) and p >= SLOT_FLOOR


def _has_history(facts: dict[str, Fact]) -> bool:
    return any(_ENTRY.fullmatch(slot) for slot in facts)


def map_fields(fields: list[MapField], facts: dict[str, Fact], session: Session, *,
               eeo_consented: bool, low_stakes: bool) -> dict[str, Mapped]:
    criteria = _criteria(facts)
    picked = None
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            picked = _with_jev(fields, criteria, session)
        except llm.LLMProviderError:
            logger.warning("jev map failed; the fast model maps this batch")
    if picked is None:
        picked = _with_llm(fields, criteria, session)
    out = {f.fid: _route(f, picked.get(f.fid), facts, eeo_consented=eeo_consented) for f in fields}

    def leftovers(*, protected: bool) -> list[MapField]:
        return [f for f in fields if out[f.fid].route == "none" and f.shape not in _WRITTEN_SHAPES
                and not _foreign(f) and _said_no_fact(picked.get(f.fid), protected=protected)]

    if low_stakes:
        for fid in _low_stakes(leftovers(protected=False), session):
            out[fid] = Mapped(route="low_stakes")
    if _has_history(facts):
        for fid in _answerable(leftovers(protected=True), session):
            out[fid] = Mapped(route="reasoned")
    return out
