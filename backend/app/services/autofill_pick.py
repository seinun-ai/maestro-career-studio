"""/pick — which LIVE option answers a field: the one stating a Yes/No fact's
computed answer (autofill_polarity), or the one meaning the same as any other fact?

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
import re
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import DecisionTrace, Engine, Picked, PickField, PolarityTrace, Reason
from app.services import autofill_polarity, jev, llm, model_settings
from app.services.autofill_catalog import Fact, yes_no_word
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION
from app.services.autofill_map import (
    MIN_CALL_S,
    SECOND_OPINION_MAX_S,
    Budget,
    Top,
    fast_json,
    keen,
    low_stakes_rule,
    main_call,
    second_asked,
    second_decided,
)
from app.services.autofill_reasoned import reason

logger = logging.getLogger(__name__)

ASSUMED_FLOOR = 0.4
# A Yes/No fact (`Fact.yes_no`) is not picked by its value: "No" to "will need
# sponsorship" is "Yes" to "authorized to work WITHOUT sponsorship?". Its
# question's polarity is decided first (autofill_polarity), code flips the value,
# and the pick is LITERAL: which option states that answer (owner, 2026-09-27).
# Any other fact travels with its value-free description, and is never turned
# into a Yes or a No: "Do you require sponsorship?" mapped to an "F-1 OPT"
# status must stay none, never become a confident No.
NEVER_YES_NO = ("A status, list or name value is never turned into a Yes or No: only an option naming that same "
                "status, item or name answers it, else none.")
# For a return that carries no trace (a field no pick was asked for). An abstain that has
# a trace is a fresh Picked, so it never equals this one: ask `abstained`, never compare with it.
ABSTAIN = Picked(oids=[], reason="abstained")
_NO_OPTION_TEXT = "No option means the same as the fact"
_NO_ANSWER_TEXT = "No option states this answer"
# A low-stakes field's "none" is a refusal as well as a miss: its criterion says so.
_LOW_STAKES_NONE_TEXT = "None, as the question is on the never-list or no option fits"
# Said only when the batch holds a low-stakes field: a batch without one (a
# second opinion always) is asked exactly what Jev is asked of each field.
_LOW_STAKES_PARAGRAPH = """A field marked low_stakes has no applicant value. {rule}; for such a field, return the option {keen}.
The never-list does not apply to a field with applicant_values or an answer: pick as that field says.
"""
_ANSWER_LINE = ("A field with `answer` holds the applicant's answer to its question as it is worded (`that_is`, "
                "when given, says what that answer means): return the option that states that answer.\n")
_FACT_LINE = ("A field with `fact` and applicant_values: return the option that means the same as the applicant's "
              "fact (`fact` says what its applicant_values answer). {never}\n")
_LLM_PROMPT = """For each form field return the option id that answers it, or none. {rule}
{answer}{fact}{low_stakes}Return JSON {{"picks": {{"<field id>": {{"oids": ["<option id>"], "confidence": <0..1>}}}}}};
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


def abstained(picked: Picked) -> bool:
    """Nothing was chosen. Tested by content: `==` compares the trace too, so a
    Picked carrying one never equals ABSTAIN."""
    return not picked.oids


def _bar(field, chance: float, policy: str, *, closest_ok: bool) -> tuple[float, Reason]:
    """The floor an answer is judged against and the reason it carries if it clears it. A
    `closest` near miss is a flag slot's, within [CLOSEST_FLOOR, MATCH_FLOOR) only."""
    if field.route == "low_stakes":
        return ASSUMED_FLOOR, "assumed"
    if closest_ok and policy == "flag" and CLOSEST_FLOOR <= chance < MATCH_FLOOR[policy]:
        return CLOSEST_FLOOR, "closest"
    return MATCH_FLOOR[policy], "matched"


def verdict(field, oid: str | None, p: float | None, policy: str, *, engine: Engine | None) -> Picked:
    """One single-answer decision → Picked, shared by /pick and /step, with the
    trace of how it was decided (`engine`, `p` and the floor it was judged against).

    A `closest` near miss needs a flag slot AND a complete view of the options
    (`field.complete`): the nearest of a partial list is a guess. `p` None is a
    confidence the model gave unreadably: routed as 0.0, but never traced as a 0.0
    it did not say. `chose_none`: the model's top choice was no option (None when it gave
    neither an option nor a readable confidence)."""
    chance = p or 0.0
    named = bool(oid) and oid != NO_OPTION
    chose_none = None if oid is None and p is None else not named
    floor, reason = _bar(field, chance, policy, closest_ok=named and field.complete)
    stands = named and chance >= floor
    return Picked(oids=[oid] if stands else [], reason=reason if stands else "abstained",
                  trace=DecisionTrace(engine=engine, p=p, floor=floor, chose_none=chose_none))


@dataclass(frozen=True)
class Computed:
    """A Yes/No fact's answer to its question as worded. `statement`: for a
    SAME question only (nothing was flipped), what the answer says, in the
    fact's value-free words — an undirected label over statement options
    ("Visa sponsorship": "I will not require sponsorship") needs to know what
    "No" is about; a worded answer, which fact it answers. Never for an
    OPPOSITE one: a description beside a flipped answer could flip it back."""

    answer: str
    statement: str | None = None


def statement_of(fact: Fact, answer: str) -> str:
    """The whole trailing "(yes/no…)" goes ("(yes/no; derived from …)" too): what
    is true or not true is the proposition, not its provenance."""
    about = re.sub(r"\s*\(yes/no[^)]*\)\s*$", "", fact.describe)
    return f"for the applicant, {json.dumps(about)} is {'true' if answer == 'Yes' else 'not true'}"


def asked_against(field, facts: dict[str, Fact], answers: dict[str, Computed]) -> dict:
    """What a field is picked against, as the models see it: a Yes/No fact's
    computed `answer` (and, for a SAME one, `that_is`: its statement); any
    other fact's value-free description and its values; nothing for a
    low-stakes one."""
    if field.fid in answers:
        got = answers[field.fid]
        return {"answer": got.answer, **({"that_is": got.statement} if got.statement else {})}
    fact = facts.get(field.slot or "")
    values = values_for(field, fact)
    return {"fact": fact.describe, "applicant_values": values} if fact is not None and values else {
        "applicant_values": values}


def polarity_question(field) -> str:
    """The question polarity is asked about. Options that STATE an answer go
    with it: an undirected question ("Please check one of the boxes below:",
    iCIMS CC-305, live 2026-10-02) names no direction and was judged unsure,
    while "No, I do not have a disability…" says what is asked. Only options
    that are SENTENCES (two or more of four words or more): plain Yes / No say
    nothing, so a reversed knockout question is judged as worded, and short
    labels ("Current Associate", "Not Applicable") made a label judged same
    read as unsure."""
    texts = [o.text.strip() for o in getattr(field, "options", None) or [] if o.text.strip()]
    stated = [t for t in texts if yes_no_word(t) not in ("Yes", "No") and len(t.split()) >= 4]
    if len(stated) < 2:   # also a /step, which has no options
        return field.question
    return f"{field.question} (options: {'; '.join(texts)})"


def _yes_no(fields, facts: dict[str, Fact]) -> dict[str, Fact]:
    """The slot fields holding a Yes/No fact, with that fact."""
    return {f.fid: facts[f.slot] for f in fields if f.route == "slot" and f.slot in facts and facts[f.slot].yes_no}


def polarity_ways(fields, facts: dict[str, Fact], session: Session,
                  budget: Budget) -> dict[str, autofill_polarity.Polarity]:
    """Per slot field holding a Yes/No fact, which way its question reads against the
    fact (autofill_polarity: same, opposite, neither or unsure) and how that was decided.
    The model calls; `polarity_answers` turns the ways into answers."""
    yes_no = _yes_no(fields, facts)
    return autofill_polarity.decide([autofill_polarity.Ask(f.fid, polarity_question(f), facts[f.slot].describe,
                                                           facts[f.slot].policy)
                                     for f in fields if f.fid in yes_no], session, budget)


def polarity_trace(w: autofill_polarity.Polarity) -> PolarityTrace:
    """How polarity went, value-free; UNSURE reads as 'unsure'."""
    return PolarityTrace(way=w.way or "unsure", engine=w.engine, p=w.p)


def polarity_answers(fields, facts: dict[str, Fact],
                     ways: dict[str, autofill_polarity.Polarity]) -> dict[str, Computed | None]:
    """Per slot field holding a Yes/No fact, the applicant's answer to its
    question as worded: its polarity (`polarity_ways`), then the value flipped
    by code. None: unsure, neither, or a wordy value asked the other way."""
    out: dict[str, Computed | None] = {}
    for fid, fact in _yes_no(fields, facts).items():
        way = ways[fid].way
        answer = autofill_polarity.answer_for(str(fact.value), way)
        # A saved answer is described by its own question ("saved answer to:
        # …"): a statement would read as that answer being false. Literal only.
        same = way == autofill_polarity.SAME and not fact.slot.startswith("custom.")
        # A worded answer ("No, I do not have a disability") says which fact
        # it answers: beside an undirected question ("Please check one of the
        # boxes below:", iCIMS CC-305) Jev picked the right box under the floor.
        statement = (statement_of(fact, answer) if answer in ("Yes", "No")
                     else f"it answers {json.dumps(fact.describe)}") if same else None
        out[fid] = Computed(answer, statement) if answer is not None else None
    return out


def _policy(field: PickField, facts: dict[str, Fact]) -> str:
    fact = facts.get(field.slot or "")
    return fact.policy if fact else "any"


def _instructions(field: PickField, values: list[str], hint: JobHint | None, facts: dict[str, Fact],
                  answer: Computed | None = None) -> str:
    q = f"form field {field.fid} ({json.dumps(field.question)})"
    if field.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), choose it."
               if hint and hint.source else "")
        refuse = f"choose {json.dumps(_LOW_STAKES_NONE_TEXT)}"
        return (f"The applicant gave no answer to {q}. {low_stakes_rule(facts, refuse)}; for such a field, "
                f"pick the option {keen(facts)}.{src} {_PAGE_TEXT_IS_DATA}")
    if answer is not None:
        that_is = f"; that is, {answer.statement}" if answer.statement else ""
        return (f"The applicant's answer to {q} is {json.dumps(answer.answer)}{that_is}. "
                f"Which option states that answer? {_PAGE_TEXT_IS_DATA}")
    fact = facts[field.slot]
    return (f"Which option of {q} means the same as the applicant's fact {json.dumps(fact.describe)}: "
            f"{json.dumps(values[0])}? {NEVER_YES_NO} {_PAGE_TEXT_IS_DATA}")


def _with_jev(fields, facts, hint, session,
              answers: dict[str, Computed]) -> tuple[dict[str, Picked], dict[str, Top]]:
    """Each field's Picked, and Jev's top choice with its probability for every
    field it answered readably, even an abstained one: a second opinion that
    decides is traced against it (`autofill_map.second_decided`)."""
    state = {"job": asdict(hint) if hint else None, "fields": []}
    questions, criteria_by_fid = {}, {}
    for f in fields:
        values = values_for(f, facts.get(f.slot or ""))
        state["fields"].append({"id": f.fid, "question": f.question, **asked_against(f, facts, answers)})
        none = (_LOW_STAKES_NONE_TEXT if f.route == "low_stakes"
                else _NO_ANSWER_TEXT if f.fid in answers else _NO_OPTION_TEXT)
        criteria_by_fid[f.fid] = {o.oid: o.text for o in f.options} | {NO_OPTION: none}
        questions[f.fid] = jev.choice_question(_instructions(f, values, hint, facts, answers.get(f.fid)),
                                               criteria_by_fid[f.fid])
    replies = jev.decide(questions, state, session)
    out: dict[str, Picked] = {}
    tops: dict[str, Top] = {}
    for f in fields:
        got = jev.choice_of(replies.get(f.fid), criteria_by_fid[f.fid])
        if got:
            tops[f.fid] = (got.choice, got.probability)
        out[f.fid] = verdict(f, got.choice if got else None, got.probability if got else None,
                             _policy(f, facts), engine="jev")
    return out, tops


def _with_llm(fields, facts, hint, session, answers: dict[str, Computed], trace_name="autofill-pick", *,
              timeout: float | None = None) -> dict[str, Picked]:
    payload = [{"id": f.fid, "question": f.question, **({"low_stakes": True} if f.route == "low_stakes" else {}),
                **asked_against(f, facts, answers), "options": [o.model_dump() for o in f.options]} for f in fields]
    low_stakes = _LOW_STAKES_PARAGRAPH.format(
        rule=low_stakes_rule(facts, "return none for that field", subject="a low_stakes field"), keen=keen(facts),
    ) if any(f.route == "low_stakes" for f in fields) else ""
    raw = fast_json(session, _LLM_PROMPT.format(
        rule=_PAGE_TEXT_IS_DATA, low_stakes=low_stakes,
        answer=_ANSWER_LINE if any("answer" in p for p in payload) else "",
        fact=_FACT_LINE.format(never=NEVER_YES_NO) if any("fact" in p for p in payload) else "",
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
        conf = float(conf) if jev._unit(conf) else None   # unreadable: routed as 0.0, traced as None
        out[f.fid] = verdict(f, oids[0] if oids else None, conf, _policy(f, facts), engine="fast")
    return out


def _second_opinion(fields: list[PickField], facts: dict[str, Fact], hint: JobHint | None, session: Session,
                    budget: Budget, answers: dict[str, Computed], *,
                    reasoning_next: bool = False) -> dict[str, Picked] | None:
    """ONE fast-model pick for the fact fields Jev abstained on, on what is
    left of the request's budget (capped; leaving a reasoning call that
    follows time to start), through the same `verdict`. Out of time or
    failed, Jev's abstention stands. None: it did not run (the trace's
    `second` stays None for those fields)."""
    timeout = budget.left(SECOND_OPINION_MAX_S, reserve=MIN_CALL_S if reasoning_next else 0.0)
    if not fields or timeout is None:
        return None
    try:
        return _with_llm(fields, facts, hint, session, answers, "autofill-pick-second", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model second opinion failed; Jev's abstentions stand")
        return None


def _with_second_opinion(picked: dict[str, Picked], tops: dict[str, Top], unsure: list[PickField],
                         second: dict[str, Picked] | None) -> int:
    """Fold the second opinion into Jev's `picked`: a field it decided takes its answer,
    traced against Jev's top choice; one it was asked about and did not decide keeps
    Jev's trace, marked asked. `second` None: it did not run, and every field keeps
    Jev's trace as it was. How many it decided."""
    if second is None:
        return 0
    n_decided = 0
    for f in unsure:
        got = second[f.fid]
        if abstained(got):
            picked[f.fid] = picked[f.fid].model_copy(update={"trace": second_asked(picked[f.fid].trace)})
        else:
            trace = second_decided(got.trace, tops.get(f.fid), got.oids[0])
            picked[f.fid] = got.model_copy(update={"trace": trace})
            n_decided += 1
    return n_decided


def _with_polarity(out: dict[str, Picked], ways: dict[str, autofill_polarity.Polarity]) -> None:
    """How polarity went, on every field it judged, also the ones it left to the user: they
    carry no trace (no pick was asked), and this is what explains them (iCIMS CC-305,
    live 2026-10-02)."""
    for fid, w in ways.items():
        out[fid] = out[fid].model_copy(update={"polarity": polarity_trace(w)})


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
    # A Yes/No fact's answer to the question as worded: polarity first, code
    # flips; unsure, it is left to the user and never picked.
    ways = polarity_ways(askable, facts, session, budget)
    computed = polarity_answers(askable, facts, ways)
    answers = {fid: a for fid, a in computed.items() if a is not None}
    out |= {fid: ABSTAIN for fid in computed if fid not in answers}
    askable = [f for f in askable if f.fid not in computed or f.fid in answers]
    # The fact picks first: a slow reasoning call must never cost them.
    if askable:
        picked, tops = None, {}
        if model_settings.get_autofill_engine(session) == "jev":
            try:
                picked, tops = _with_jev(askable, facts, hint, session, answers)
            except llm.LLMProviderError:
                logger.warning("jev pick failed; the fast model picks this batch")
        if picked is None:
            # One request of what is left of the budget, no retries: a slow
            # batch never outlives the Companion's wait.
            picked = main_call(budget, lambda timeout: _with_llm(askable, facts, hint, session, answers,
                                                                 timeout=timeout), "fast pick")
        else:
            unsure = [f for f in askable if f.route == "slot" and abstained(picked[f.fid])]
            second = _second_opinion(unsure, facts, hint, session, budget, answers,
                                     reasoning_next=bool(reasoned))
            if n_decided := _with_second_opinion(picked, tops, unsure, second):
                logger.info("pick: the fast model decided %d of %d fields Jev abstained on", n_decided, len(unsure))
        out |= picked
    if reasoned:
        out |= reason(reasoned, facts, session, budget, hint.company if hint else None)
    _with_polarity(out, ways)
    return out
