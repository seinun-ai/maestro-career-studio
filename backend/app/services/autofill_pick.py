"""/pick — which LIVE option states the applicant's fact?

Options are what the page shows after the extension explored it, keyed by the
page-side oid. Every pick is one Jev Choice over those code-owned keys +
`none`; a set is picked one source item at a time (`item`), so each chosen
option maps back to the item it stands for. Policy comes from the SLOT,
server-side. The fast-model fallback returns a confidence and meets the same
floors, both when Jev fails and, as ONE second opinion on the request's
`Budget`, for the fact picks Jev abstained on (`exact` still refuses a near
miss; the low-stakes and reasoned routes keep their engines). Low-stakes answers (setting on, re-checked here) are what a keen
applicant for this job would choose, and are marked `assumed`.

REASONED fields are answered from the work and education history alone
(autofill_reasoned.reason), AFTER the fact picks so a slow or failed call
never costs them, on the request's one `Budget`.
"""

import json
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Picked, PickField
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION
from app.services.autofill_map import MIN_CALL_S, SECOND_OPINION_MAX_S, Budget, fast_json, keen, low_stakes_rule
from app.services.autofill_reasoned import reason

logger = logging.getLogger(__name__)

ASSUMED_FLOOR = 0.4
# A value means nothing without its fact: "No" to "will need sponsorship" is
# "Yes" to "authorized to work WITHOUT sponsorship?". The fact's value-free
# description (the catalog's `describe`) travels beside the value, and every
# /pick and /step question with a value says how to read it (owner, 2026-09-27).
MEANING_RULE = ("Read the question as it is worded: it may ask the fact directly, or its reverse or a negation "
                "of it, and the right option is the one whose answer to THAT question is true of the applicant "
                "(a No to the fact can be a Yes to the question).")
ABSTAIN = Picked(oids=[], reason="abstained")
_NO_OPTION_TEXT = "No option states this value"
# A low-stakes field's "none" is a refusal as well as a miss: its criterion says so.
_LOW_STAKES_NONE_TEXT = "None, as the question is on the never-list or no option fits"
# Said only when the batch holds a low-stakes field: a batch of fact fields
# is asked exactly what Jev is asked, which option states the value.
_LOW_STAKES_PARAGRAPH = """A field marked low_stakes has no applicant value. {rule}; for such a field, return the option {keen}.
The never-list does not apply to a field with applicant_values: pick the option that states its value.
"""
_LLM_PROMPT = """For each form field with applicant_values, return the option id that means the same as the
applicant's fact (`fact` says what its applicant_values answer), or none. {meaning} {rule}
{low_stakes}Return JSON {{"picks": {{"<field id>": {{"oids": ["<option id>"], "confidence": <0..1>}}}}}};
for none, "oids": [].
Job: {job}
Fields: {fields}
"""


@dataclass(frozen=True)
class JobHint:
    title: str | None
    company: str | None
    source: str | None


def values_for(field, fact: Fact | None) -> list[str]:
    """The applicant values a field is picked against, from the SLOT's fact —
    never from the client. A set slot is picked one `item` at a time, and only
    an item the set really holds; a set slot with no item has nothing to pick."""
    if field.route == "low_stakes" or fact is None:
        return []
    item = getattr(field, "item", None)
    if isinstance(fact.value, tuple):
        return [item] if item and item in fact.value else []
    return [] if item else [fact.value]


def verdict(field, oid: str | None, p: float, policy: str, *, complete: bool) -> Picked:
    """One single-answer decision → Picked, shared by /pick and /step.

    A `closest` near miss needs a flag slot AND a complete view of the options:
    the nearest of a partial list is a guess."""
    if not oid or oid == NO_OPTION:
        return ABSTAIN
    if field.route == "low_stakes":
        return Picked(oids=[oid], reason="assumed") if p >= ASSUMED_FLOOR else ABSTAIN
    if p >= MATCH_FLOOR[policy]:
        return Picked(oids=[oid], reason="matched")
    if policy == "flag" and complete and p >= CLOSEST_FLOOR:
        return Picked(oids=[oid], reason="closest")
    return ABSTAIN


def fact_of(field, facts: dict[str, Fact]) -> dict:
    """`{"fact": <its value-free description>}` for a field picked against a
    value, else nothing: what the value answers, never another value."""
    fact = facts.get(field.slot or "")
    return {"fact": fact.describe} if fact is not None and values_for(field, fact) else {}


def _policy(field: PickField, facts: dict[str, Fact]) -> str:
    fact = facts.get(field.slot or "")
    return fact.policy if fact else "any"


def _instructions(field: PickField, values: list[str], hint: JobHint | None, facts: dict[str, Fact]) -> str:
    q = f"form field {field.fid} ({json.dumps(field.question)})"
    if field.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), choose it."
               if hint and hint.source else "")
        refuse = f"choose {json.dumps(_LOW_STAKES_NONE_TEXT)}"
        return (f"The applicant gave no answer to {q}. {low_stakes_rule(facts, refuse)}; for such a field, "
                f"pick the option {keen(facts)}.{src} {_PAGE_TEXT_IS_DATA}")
    describe = facts[field.slot].describe
    return (f"Which option of {q} means the same as the applicant's fact {json.dumps(describe)}: "
            f"{json.dumps(values[0])}? {MEANING_RULE} {_PAGE_TEXT_IS_DATA}")


def _with_jev(fields, facts, hint, session) -> dict[str, Picked]:
    state = {"job": asdict(hint) if hint else None, "fields": []}
    questions, criteria_by_fid = {}, {}
    for f in fields:
        values = values_for(f, facts.get(f.slot or ""))
        state["fields"].append({"id": f.fid, "question": f.question, **fact_of(f, facts), "applicant_values": values})
        none = _LOW_STAKES_NONE_TEXT if f.route == "low_stakes" else _NO_OPTION_TEXT
        criteria_by_fid[f.fid] = {o.oid: o.text for o in f.options} | {NO_OPTION: none}
        questions[f.fid] = jev.choice_question(_instructions(f, values, hint, facts), criteria_by_fid[f.fid])
    answers = jev.decide(questions, state, session)
    out = {}
    for f in fields:
        got = jev.choice_of(answers.get(f.fid), criteria_by_fid[f.fid])
        out[f.fid] = verdict(f, got.choice if got else None, got.probability if got else 0.0,
                             _policy(f, facts), complete=f.complete)
    return out


def _with_llm(fields, facts, hint, session, trace_name="autofill-pick", *,
              timeout: float | None = None) -> dict[str, Picked]:
    payload = [{"id": f.fid, "question": f.question, **({"low_stakes": True} if f.route == "low_stakes" else {}),
                **fact_of(f, facts), "applicant_values": values_for(f, facts.get(f.slot or "")),
                "options": [o.model_dump() for o in f.options]} for f in fields]
    low_stakes = _LOW_STAKES_PARAGRAPH.format(
        rule=low_stakes_rule(facts, "return none for that field", subject="a low_stakes field"), keen=keen(facts),
    ) if any(f.route == "low_stakes" for f in fields) else ""
    raw = fast_json(session, _LLM_PROMPT.format(
        meaning=MEANING_RULE, rule=_PAGE_TEXT_IS_DATA, low_stakes=low_stakes,
        job=json.dumps(asdict(hint) if hint else None), fields=json.dumps(payload)), trace_name, timeout=timeout)
    picks = raw.get("picks") if isinstance(raw, dict) else None
    picks = picks if isinstance(picks, dict) else {}
    out = {}
    for f in fields:
        entry = picks.get(f.fid)
        entry = entry if isinstance(entry, dict) else {}
        offered = {o.oid for o in f.options}
        oids = entry.get("oids")
        oids = [o for o in oids if isinstance(o, str) and o in offered] if isinstance(oids, list) else []
        conf = entry.get("confidence")
        conf = float(conf) if jev._unit(conf) else 0.0
        out[f.fid] = verdict(f, oids[0] if oids else None, conf, _policy(f, facts), complete=f.complete)
    return out


def _second_opinion(fields: list[PickField], facts: dict[str, Fact], hint: JobHint | None, session: Session,
                    budget: Budget, *, reasoning_next: bool = False) -> dict[str, Picked]:
    """ONE fast-model pick for the fact fields Jev abstained on, on what is
    left of the request's budget (capped; leaving a reasoning call that
    follows time to start), through the same `verdict`. Out of time or
    failed, Jev's abstention stands."""
    timeout = budget.left(SECOND_OPINION_MAX_S, reserve=MIN_CALL_S if reasoning_next else 0.0)
    if not fields or timeout is None:
        return {}
    try:
        return _with_llm(fields, facts, hint, session, "autofill-pick-second", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model second opinion failed; Jev's abstentions stand")
        return {}


def pick(fields: list[PickField], facts: dict[str, Fact], session: Session, hint: JobHint | None) -> dict[str, Picked]:
    budget = Budget()
    low_stakes_on = model_settings.get_autofill_low_stakes(session)  # re-checked, never trusted from the client
    # A low-stakes or reasoned field carries no slot: one that names a slot is
    # a fact field the client mis-routed, and a guess would answer it.
    askable = [f for f in fields
               if (f.route == "low_stakes" and low_stakes_on and not f.slot)
               or (f.route == "slot" and values_for(f, facts.get(f.slot or "")))]
    reasoned = [f for f in fields if f.route == "reasoned" and not f.slot]
    asked = {f.fid for f in askable + reasoned}
    out = {f.fid: ABSTAIN for f in fields if f.fid not in asked}
    # The fact picks first: a slow reasoning call must never cost them.
    if askable:
        picked = None
        if model_settings.get_autofill_engine(session) == "jev":
            try:
                picked = _with_jev(askable, facts, hint, session)
            except llm.LLMProviderError:
                logger.warning("jev pick failed; the fast model picks this batch")
        if picked is None:
            picked = _with_llm(askable, facts, hint, session)
        else:
            unsure = [f for f in askable if f.route == "slot" and picked[f.fid] == ABSTAIN]
            decided = {fid: p for fid, p in _second_opinion(unsure, facts, hint, session, budget,
                                                             reasoning_next=bool(reasoned)).items()
                       if p != ABSTAIN}
            if decided:
                logger.info("pick: the fast model decided %d of %d fields Jev abstained on", len(decided), len(unsure))
            picked |= decided
        out |= picked
    if reasoned:
        out |= reason(reasoned, facts, session, budget, hint.company if hint else None)
    return out
