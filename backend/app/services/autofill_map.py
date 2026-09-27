"""/map — which applicant fact does each field ask for?

One batched Jev Choice per field over fact DESCRIPTIONS (never values) plus
sentinels; code looks values up afterwards. The fast model does the same job
in JSON — with a 0–1 confidence that must clear the SAME floors — when the
engine is `fast` or a Jev call fails, and as ONE second opinion (on the
request's `Budget`) for the fields Jev was unsure of: no readable answer, "no
fact", or a fact under its floor. Jev's protected, history, EEO and free-text
answers are its own and never asked again.

Low-stakes (setting on, decided by the caller from the server-side setting) is
a SECOND pass, asked only for fields whose best answer was an explicit,
confident "no fact answers this": a real profile answer always wins, and a
field that looked like a real fact but fell below its floor, that the model
did not answer readably, or that it named a protected kind (work
authorization, eligibility, background, EEO) is never turned into a guess.

The REASONING pass (`reasoned`, whatever the low-stakes setting) comes last:
a choice field still routed none, whose map answer was an explicit, confident
"no fact" or "a history question no fact answers" (its own sentinel, apart
from the protected one: a protected, EEO or shaky-fact field is never a
candidate), and that the fast model judges answerable from the work and
education history — past employment by a kind of organization, a clearance,
years of experience with something. The question DESCRIBES the history and
never sends it; /pick answers from it.

Both extra passes are optional and share a time budget: past
OPTIONAL_PASS_BUDGET_S since the map began, a pass is skipped, and one that
runs gets what is left of REQUEST_BUDGET_S as a real request timeout with no
retries, so /map answers inside the loop's 10 s wait.

When the work history lists the company applied to (`derived.previously_employed_here`),
"previously employed by the company, answered No" leaves the low-stakes scope
and joins its never-list for that request (`low_stakes_scope`).
"""

import json
import logging
import re
import time
from collections.abc import Callable
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
HISTORY_UNANSWERED = "history_unanswered"
LOW_STAKES_FLOOR = 0.8
ANSWERABLE_FLOOR = 0.8
# Seconds since the request began after which no optional pass starts, and
# the whole request's budget (the loop waits 10 s for /map, /pick and /step; one
# fast-model call is typically 1–3 s). An optional call's timeout is what is
# left of the budget, never under MIN_CALL_S.
OPTIONAL_PASS_BUDGET_S = 6.0
REQUEST_BUDGET_S = 9.0
MIN_CALL_S = 1.0
# The fast second opinion on Jev's unsure answers (/map, /pick, /step) never
# takes longer than this, and where an optional pass may follow it leaves that
# pass MIN_CALL_S before OPTIONAL_PASS_BUDGET_S to start in.
SECOND_OPINION_MAX_S = 4.0
_clock = time.monotonic
WORKED_HERE = "derived.previously_employed_here"
_SENTINELS = {
    FREE_TEXT: "A question that needs a written answer in the applicant's own words, "
               "such as why this company or describe a project",
    NO_SLOT: "None of the listed applicant facts or question kinds fits this field",
    # Offered in EVERY question, so a knockout question the profile cannot
    # answer has somewhere to go that is not "none" (a low-stakes candidate).
    PROTECTED_UNANSWERED: "A work-authorization, sponsorship, age or eligibility, or background-check "
                          "question that none of the listed applicant facts answers",
    # Offered in every question too, so a question the work history may answer
    # has somewhere to go that is neither a protected question nor "none".
    HISTORY_UNANSWERED: "A question about past employment by a KIND of organization (a government agency, a "
                        "federal contractor), a security clearance, or years of experience with something, "
                        "which none of the listed applicant facts answers",
    # Always offered too: without consent it marks the field `blocked`; with
    # consent the EEO facts are listed, and choosing this means none answers it.
    BLOCKED_EEO: "A voluntary diversity / EEO question (gender, race or ethnicity, Hispanic or Latino, "
                 "veteran status, or disability) that none of the listed applicant facts answers",
}
# The owner's scope (2026-09-26): answered in the job's favour when the
# setting is on and no profile fact answers. Self-assessments against the job
# description and contact consents are IN; factual entries are not.
_LOW_STAKES_TEMPLATE = (
    "A low-stakes question an applicant keen on this job would answer in its favor: how the applicant heard "
    "about the job or a referral source; preferred contact method; willingness or comfort with relocation, "
    "travel (any share of time), on-site work, shifts, overtime or a drug test; openness to other roles; "
    "{conflict}; what the applicant would do if employed by the company; consent to be contacted by SMS, "
    "automated calls or texts, or marketing messages; or a yes/no self-assessment against the job description as "
    "a whole, such as having the required experience or meeting the educational requirement (one naming a number "
    "of years with a specific skill or tool is a factual experience question instead)")
# A list of noun phrases: every question states it after "is about anything
# on this never-list:". A self-assessment naming a number of years with a
# specific skill or tool ("5+ years of SQL?") is a factual experience question
# (the example names no real tool: it would be a value the model must not see)
# (owner, 2026-09-27); the job description's generic "required experience" is not.
_NEVER_LOW_STAKES_TEMPLATE = (
    "a factual education or experience question (a school, degree, employer, title, date or certification, or "
    "a number of years of experience with a specific skill or tool, such as \"5+ years of <a named tool>?\", even asked as "
    "yes or no), work authorization, sponsorship, age or eligibility facts, EEO / diversity, background or "
    "criminal history, security clearance, salary, {worked}or a legal attestation or signature")
_CONFLICT = "whether the applicant is related to, or was previously employed by, the company (answered No)"
# The history lists the company applied to: "previously employed here" is a
# fact now, and a keen No would contradict it.
_CONFLICT_WORKED_HERE = "whether the applicant is related to someone at the company (answered No)"
_WORKED_HERE_NEVER = "whether the applicant worked for this company (their history says they did), "


def low_stakes_scope(facts: dict[str, Fact]) -> tuple[str, str]:
    """The low-stakes kinds and the never-list for THIS request's facts."""
    worked = WORKED_HERE in facts
    return (_LOW_STAKES_TEMPLATE.format(conflict=_CONFLICT_WORKED_HERE if worked else _CONFLICT),
            _NEVER_LOW_STAKES_TEMPLATE.format(worked=_WORKED_HERE_NEVER if worked else ""))


_LOW_STAKES, _NEVER_LOW_STAKES = low_stakes_scope({})


# Which way a keen answer goes. Said outright: with only the conflict No in
# the brackets, Jev read "No" as the answer to a self-assessment ("do you have
# the required experience?") — evaluation 2026-09-27. Scoped to the low-stakes
# kinds: unscoped, "shows they fit" is also No to a felony, No to sponsorship
# and Yes to a clearance, if /map ever mis-routes one of those here.
_KEEN_WAY = "for a question in that scope, the answer that shows they fit and want this job"


def keen(facts: dict[str, Fact]) -> str:
    """The low-stakes answer (/pick, /step), and which way a conflict question
    goes. When the history lists the company applied to, "previously employed
    here" is a fact and a keen No would contradict it, so only a relative is a No."""
    if WORKED_HERE in facts:
        return f"an applicant keen on this job would choose ({_KEEN_WAY}; No to being related to someone at the company)"
    return (f"an applicant keen on this job would choose ({_KEEN_WAY}; No to being related to, or previously "
            "employed by, the company)")


def low_stakes_rule(facts: dict[str, Fact], refuse: str, subject: str = "the field") -> str:
    """What a low-stakes field never is, THEN what it is, as /pick and /step ask
    it. The exclusion comes first, as a condition with its own refusal, and the
    scope is a definition, never an assertion that this field is in it: /map
    may have mis-routed a protected question here, and nothing but this
    wording stands between it and a keen answer (owner: no code-level refusal).
    The caller finishes the sentence with the keen answer."""
    scope, never = low_stakes_scope(facts)
    return (f"If {subject} is about anything on this never-list, {refuse}: {never}. "
            f"Otherwise a low_stakes field is {scope[0].lower()}{scope[1:]}")


# What the reasoning route may read (autofill_reasoned.history sends exactly
# these, never a name, contact detail, address or EEO answer).
REASONED_FROM = ("the applicant's work history (each job's employer, title, dates, whether it is current, and "
                 "description) and education (each school, degree, major and years)")
NEVER_REASONED = ("work authorization, sponsorship, age, EEO / diversity, background or criminal history, salary, "
                  "a preference or willingness, a comparison with the job description's requirements, whether "
                  "the applicant worked for, or is related to someone at, the company applied to, or a legal "
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


def fast_json(session: Session, prompt: str, trace_name: str, *, timeout: float | None = None) -> object:
    """One fast-model JSON call. JSON that stays malformed after the client's
    retries is a provider failure (a 502 with a detail), not a crash.
    `timeout`: an optional call on a budget — one request, that long, no retries."""
    budget = {"timeout": timeout, "max_retries": 0} if timeout is not None else {}
    try:
        return llm.call_openai(prompt=prompt, model=model_settings.get_fast_model(session),
                               response_format="json", trace_name=trace_name, **budget)
    except ValueError as exc:
        raise llm.LLMProviderError("The AI model sent an answer we couldn't read.", str(exc)) from exc


def _with_llm(fields, criteria, session, trace_name="autofill-map", *,
              timeout: float | None = None) -> dict[str, tuple[str, float]]:
    raw = fast_json(session, _LLM_PROMPT.format(
        rule=_PAGE_TEXT_IS_DATA, criteria="\n".join(f"- {k}: {v}" for k, v in criteria.items()),
        fields=json.dumps(_payload(fields))), trace_name, timeout=timeout)
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


class Budget:
    """One request's time (/map, /pick, /step): created when the request begins,
    asked before each optional call. `clock` is injectable; by default this
    module's `_clock`, read at each call so one patch reaches every request."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock
        self._started = self._now()

    def _now(self) -> float:
        return (self._clock or _clock)()

    def left(self, cap: float | None = None, *, reserve: float = 0.0) -> float | None:
        """The timeout an optional call may take, or None once none should start.
        `cap`: at most that long. `reserve`: end that long before
        OPTIONAL_PASS_BUDGET_S, so a later optional call can still start."""
        elapsed = self._now() - self._started
        if elapsed >= OPTIONAL_PASS_BUDGET_S:
            return None
        timeout = REQUEST_BUDGET_S - elapsed
        if cap is not None:
            timeout = min(timeout, cap)
        if reserve:
            timeout = min(timeout, OPTIONAL_PASS_BUDGET_S - elapsed - reserve)
        return max(MIN_CALL_S, timeout)

    def rest(self) -> float:
        """The timeout a request's MAIN call takes (not optional: it always
        runs): what is left of REQUEST_BUDGET_S, never under MIN_CALL_S."""
        return max(MIN_CALL_S, REQUEST_BUDGET_S - (self._now() - self._started))


def _fast_yes(ask: dict[str, str], floor: float, session: Session, trace_name: str, timeout: float) -> set[str]:
    """The fast model's yes, per question, at `floor`. A failure answers "none
    of them": a second pass is optional, and the map it follows must survive it."""
    try:
        raw = fast_json(session, "Answer each question with a probability of yes. " + json.dumps(ask)
                        + ' Return JSON {"yes": {"<field id>": <0..1>}}.', trace_name, timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model %s check failed; no field is taken", trace_name)
        return set()
    got = raw.get("yes") if isinstance(raw, dict) else None
    return {fid for fid, p in (got.items() if isinstance(got, dict) else ())
            if fid in ask and jev._unit(p) and p >= floor}


def _low_stakes(fields: list[MapField], facts: dict[str, Fact], session: Session, budget: Budget) -> set[str]:
    """Which of these fields is a low-stakes question? The never-list is
    stated in every question."""
    timeout = budget.left()
    if not fields or timeout is None:
        return set()
    scope, never = low_stakes_scope(facts)
    ask = {f.fid: (f"Is form field {f.fid} ({json.dumps(f.question)}) one of these low-stakes questions: "
                   f"{scope}? It is NOT if it is about anything on this never-list: {never}. {_PAGE_TEXT_IS_DATA}")
           for f in fields}
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            answers = jev.decide({fid: jev.noul_question(q) for fid, q in ask.items()},
                                 {"form_fields": _payload(fields)}, session)
            return {fid for fid in ask
                    if (p := jev.noul_of(answers.get(fid))) is not None and p >= LOW_STAKES_FLOOR}
        except llm.LLMProviderError:
            logger.warning("jev low-stakes check failed; the fast model decides")
        if (timeout := budget.left()) is None:
            return set()
    return _fast_yes(ask, LOW_STAKES_FLOOR, session, "autofill-low-stakes", timeout)


def _answerable(fields: list[MapField], session: Session, budget: Budget) -> set[str]:
    """Which of these fields the work and education history can answer. The
    fast model only, on every engine: this route's /pick needs the history as
    values, which Jev's state would then carry, so Jev judges none of it."""
    timeout = budget.left()
    if not fields or timeout is None:
        return set()
    ask = {f.fid: (f"Can form field {f.fid} ({json.dumps(f.question)}) be answered from {REASONED_FROM} alone, "
                   "such as past employment by a kind of organization, a security clearance, or years of "
                   f"experience with something? It cannot if it asks about {NEVER_REASONED}. {_PAGE_TEXT_IS_DATA}")
           for f in fields}
    return _fast_yes(ask, ANSWERABLE_FLOOR, session, "autofill-reasoned", timeout)


_PHONE = re.compile(r"phone", re.IGNORECASE)
_MONEY = re.compile(r"(^|[._])(desired_)?(salary|compensation|pay)([._]|$)", re.IGNORECASE)
_ENTRY = re.compile(rf"({'|'.join(get_args(EntryKind))})\.(\d+)\.(.+)")
# The entry kinds that are the applicant's HISTORY (autofill_reasoned reads
# exactly these); a language is placed like them but is no history.
_HISTORY_KINDS = ("experience", "education")


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
    another kind than the section holds, or a language fact outside a placed
    Languages entry."""
    m = _ENTRY.fullmatch(key)
    # A language fact means nothing without its language: only a placed Languages entry's field gets one.
    if m is not None and m[1] == "languages" and field.entry_kind != "languages":
        return None
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


def _said_no_fact(picked: tuple[str, float] | None, *, history: bool = False) -> bool:
    """An EXPLICIT, confident "no fact answers this". An omitted, refused or
    unsure answer, a fact below its floor, a protected or EEO kind all say
    something else, and none of them is a candidate for either pass.
    `history`: a history question no fact answers counts too — for the
    reasoning route only, never for a low-stakes guess."""
    key, p = picked or (None, 0.0)
    return (key == NO_SLOT or (history and key == HISTORY_UNANSWERED)) and p >= SLOT_FLOOR


def _unsure(field: MapField, picked: tuple[str, float] | None, facts: dict[str, Fact]) -> bool:
    """Jev left this field to no one: no readable answer, "no fact", or a fact
    under its floor. Its protected, history, EEO and free-text answers are
    classifications, not doubts, and a foreign entry is code's none."""
    if _foreign(field):
        return False
    if picked is None:
        return True
    key, p = picked
    return key == NO_SLOT or (key in facts and p < _floor(facts[key]))


def _second_opinion(fields: list[MapField], criteria: dict[str, str], session: Session,
                    budget: Budget) -> dict[str, tuple[str, float]]:
    """ONE fast-model map of the fields Jev was unsure of, on what is left of
    the request's budget (capped, leaving the optional passes time to start).
    Out of time or failed, Jev's none stands."""
    timeout = budget.left(SECOND_OPINION_MAX_S, reserve=MIN_CALL_S)
    if not fields or timeout is None:
        return {}
    try:
        return _with_llm(fields, criteria, session, "autofill-map-second", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model second opinion failed; Jev's none stands")
        return {}


def _agrees_no_fact(second: tuple[str, float] | None, *, history: bool) -> bool:
    """A second opinion keeps a field a guess candidate only by not naming
    anything else: a fact (at any probability), a protected, EEO or free-text
    kind keep it the user's. Silence says nothing."""
    return second is None or second[0] == NO_SLOT or (history and second[0] == HISTORY_UNANSWERED)


def _has_history(facts: dict[str, Fact]) -> bool:
    return any((m := _ENTRY.fullmatch(slot)) and m[1] in _HISTORY_KINDS for slot in facts)


def map_fields(fields: list[MapField], facts: dict[str, Fact], session: Session, *,
               eeo_consented: bool, low_stakes: bool) -> dict[str, Mapped]:
    budget = Budget()
    criteria = _criteria(facts)
    picked, second = None, {}
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            picked = _with_jev(fields, criteria, session)
        except llm.LLMProviderError:
            logger.warning("jev map failed; the fast model maps this batch")
    if picked is None:
        picked = _with_llm(fields, criteria, session)
    else:
        second = _second_opinion([f for f in fields if _unsure(f, picked.get(f.fid), facts)],
                                 criteria, session, budget)
    out = {f.fid: _route(f, picked.get(f.fid), facts, eeo_consented=eeo_consented) for f in fields}
    # Only a fact or an EEO block is the second opinion's to decide: a field
    # Jev said no fact answers never becomes a model-drafted free-text answer.
    by_fid = {f.fid: f for f in fields}
    decided = {fid: routed for fid, answer in second.items()
               if (routed := _route(by_fid[fid], answer, facts, eeo_consented=eeo_consented)).route
               in ("slot", "blocked")}
    if decided:
        logger.info("map: the fast model decided %d of %d fields Jev was unsure of", len(decided), len(second))
    out |= decided

    def leftovers(*, history: bool) -> list[MapField]:
        return [f for f in fields if out[f.fid].route == "none" and f.shape not in _WRITTEN_SHAPES
                and not _foreign(f) and _said_no_fact(picked.get(f.fid), history=history)
                and _agrees_no_fact(second.get(f.fid), history=history)]

    # Out of time (`budget.left()`), a pass asks nothing: the open questions stay the user's.
    if low_stakes:
        for fid in _low_stakes(leftovers(history=False), facts, session, budget):
            out[fid] = Mapped(route="low_stakes")
    if _has_history(facts):
        for fid in _answerable(leftovers(history=True), session, budget):
            out[fid] = Mapped(route="reasoned")
    return out
