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
from dataclasses import asdict, dataclass, replace

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import DecisionTrace, Engine, Picked, PickField, PolarityTrace, Reason
from app.services import autofill_education, autofill_place, autofill_polarity, autofill_sponsorship, jev, llm, model_settings
from app.services.autofill_catalog import (
    ASK_THE_USER,
    NAMES_PROTECTED_CLASS,
    WORKED_HERE_SLOT,
    Fact,
    asks_worked_here_of_other,
    named_employer_fact,
    names_veteran_off_slot,
    yes_no_word,
)
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION
from app.services.autofill_map import (
    MIN_CALL_S,
    SECOND_OPINION_MAX_S,
    second_opinion_floor,
    Budget,
    Top,
    asks_years,
    fast_json,
    keen,
    low_stakes_rule,
    main_call,
    second_asked,
    second_decided,
)
from app.services.autofill_reasoned import reason, reason_years

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


# Slots whose answer is the Companion's assumption, not the profile's word: judged at the assumed floor
# and reported `assumed`, so the user is told to check it (the profile never says what kind of phone it is).
ASSUMED_SLOTS = frozenset({"derived.phone_type"})
# The derived worked-here No read for ANOTHER company than the job's (`asks_worked_here_of_other`): the history
# says no employer of it is named, but the page's word for the company is a guess at the job record's, so the
# answer is reported assumed and listed for the user to check. A slot of its own, like the named-employer ones.
WORKED_ELSEWHERE_SLOT = f"{WORKED_HERE_SLOT}#other"
ASSUMED_SLOTS = ASSUMED_SLOTS | {WORKED_ELSEWHERE_SLOT}


def worked_elsewhere(facts: dict[str, Fact], slot: str | None, question: str, options: list[str]) -> Fact | None:
    """The derived No as a fact of its own slot, when a worked-here field's question names one other
    company (`asks_worked_here_of_other`); else None."""
    if slot == WORKED_HERE_SLOT and asks_worked_here_of_other(facts, question, options):
        return replace(facts[WORKED_HERE_SLOT], slot=WORKED_ELSEWHERE_SLOT)
    return None


def _bar(field, chance: float, policy: str, *, closest_ok: bool) -> tuple[float, Reason]:
    """The floor an answer is judged against and the reason it carries if it clears it. A
    `closest` near miss is a flag slot's, within [CLOSEST_FLOOR, MATCH_FLOOR) only."""
    if field.route == "low_stakes" or getattr(field, "slot", None) in ASSUMED_SLOTS:
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


# "Are you located in X and/or willing to relocate?" over a saved Yes to relocating: the second half is the applicant's
# own answer, so the question reads the same as the fact, with no model. ONE question: both halves in one sentence (a
# statement elsewhere in the text, "candidates who are not local or willing to relocate will not be considered", is not
# what is asked), no negation before the relocate verb, and not a work-authorization or sponsorship question (those
# never ride on this slot). "Located" alone or "relocate" alone is the model's.
_SENTENCE_END = re.compile(r"(?<=[?!])\s+|\n+|(?<=[a-z]{2}\.)\s+(?=[A-Z])")
_LOCATED_OR_RELOCATE = re.compile(
    r"\b(?:located|live|living|reside|residing|based)\b[^?!\n]*?\b(?:and/or|or)\b[^?!\n]*?"
    r"\b(?:willing|open|able|prepared)\s+to\s+(?:re-?locat|move)", re.IGNORECASE)
_NEGATION = re.compile(r"\bnot\b|n['\u2019]t\b|\bnever\b", re.IGNORECASE)
_AUTHORIZATION = re.compile(r"authori[sz]|sponsor|visa|eligible to work|legally|citizen|work permit", re.IGNORECASE)
# A condition on the relocating ("on your own", "without relocation assistance"): the saved Yes is the applicant's word
# for relocating, not for relocating on these terms, so the answer is reported assumed.
_QUALIFIER = re.compile(
    r"\bon\s+your\s+own\b|\bat\s+your\s+own\b|\bown\s+(?:expense|cost|dime)\b|\bself[- ]fund\w*|"
    r"\bwithout\b[^?!\n]*\b(?:assistance|support|package|reimburse\w*|stipend|help)\b|"
    r"\b(?:no|not)\b[^?!\n]*\brelocation\s+(?:assistance|support|package|help|reimburse\w*|stipend)\b", re.IGNORECASE)


def _relocate_sentence(question: str) -> str | None:
    """The sentence of `question` that asks "located … and/or willing to relocate" (a question, or an unpunctuated last
    line addressed to "you"), else None."""
    parts = [p.strip() for p in _SENTENCE_END.split(question) if p.strip()]
    for i, part in enumerate(parts):
        found = _LOCATED_OR_RELOCATE.search(part)
        asked = part.endswith("?") or (i == len(parts) - 1 and re.search(r"\byou(?:r)?\b", part, re.IGNORECASE))
        if found and asked and not _NEGATION.search(part[:found.end()]):
            return part
    return None


def _located_or_relocate(field, fact: Fact) -> bool:
    return (field.slot == "preferences.willing_to_relocate" and str(fact.value) == "Yes"
            and _relocate_sentence(field.question) is not None and not _AUTHORIZATION.search(field.question))


def relocate_qualified(field, fact: Fact | None) -> bool:
    """A coded relocate Yes whose question puts a condition on relocating: reported assumed."""
    return fact is not None and _located_or_relocate(field, fact) and bool(_QUALIFIER.search(field.question))


def polarity_ways(fields, facts: dict[str, Fact], session: Session,
                  budget: Budget) -> dict[str, autofill_polarity.Polarity]:
    """Per slot field holding a Yes/No fact, which way its question reads against the
    fact (autofill_polarity: same, opposite, neither or unsure) and how that was decided.
    The model calls; `polarity_answers` turns the ways into answers. "Located in … and/or
    willing to relocate" over a saved Yes is decided here, by code (same, no engine)."""
    yes_no = _yes_no(fields, facts)
    coded = {f.fid: autofill_polarity.Polarity(autofill_polarity.SAME, None, 1.0)
             for f in fields if f.fid in yes_no and _located_or_relocate(f, yes_no[f.fid])}
    asked = autofill_polarity.decide([autofill_polarity.Ask(f.fid, polarity_question(f), facts[f.slot].describe,
                                                            facts[f.slot].policy)
                                      for f in fields if f.fid in yes_no and f.fid not in coded], session, budget)
    return coded | asked


def polarity_trace(w: autofill_polarity.Polarity) -> PolarityTrace:
    """How polarity went, value-free; UNSURE reads as 'unsure'."""
    return PolarityTrace(way=w.way or "unsure", engine=w.engine, p=w.p, remembered=True if w.remembered else None)


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
                  answer: Computed | None = None, *, level: str = "history", queued: bool = False) -> str:
    q = f"form field {field.fid} ({json.dumps(field.question)})"
    if field.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), choose it."
               if hint and hint.source else "")
        refuse = f"choose {json.dumps(_LOW_STAKES_NONE_TEXT)}"
        return (f"The applicant gave no answer to {q}. {low_stakes_rule(facts, refuse, level=level, queued=queued)}; for such a field, "
                f"pick the option {keen(facts)}.{src} {_PAGE_TEXT_IS_DATA}")
    if answer is not None:
        that_is = f"; that is, {answer.statement}" if answer.statement else ""
        return (f"The applicant's answer to {q} is {json.dumps(answer.answer)}{that_is}. "
                f"Which option states that answer? {_PAGE_TEXT_IS_DATA}")
    fact = facts[field.slot]
    return (f"Which option of {q} means the same as the applicant's fact {json.dumps(fact.describe)}: "
            f"{json.dumps(values[0])}? {NEVER_YES_NO} {_PAGE_TEXT_IS_DATA}")


def _with_jev(fields, facts, hint, session, answers: dict[str, Computed], *, level: str = "history",
              queued: bool = False) -> tuple[dict[str, Picked], dict[str, Top]]:
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
        questions[f.fid] = jev.choice_question(
            _instructions(f, values, hint, facts, answers.get(f.fid), level=level, queued=queued),
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
              timeout: float | None = None, level: str = "history", queued: bool = False) -> dict[str, Picked]:
    payload = [{"id": f.fid, "question": f.question, **({"low_stakes": True} if f.route == "low_stakes" else {}),
                **asked_against(f, facts, answers), "options": [o.model_dump() for o in f.options]} for f in fields]
    low_stakes = _LOW_STAKES_PARAGRAPH.format(
        rule=low_stakes_rule(facts, "return none for that field", subject="a low_stakes field",
                             level=level, queued=queued), keen=keen(facts),
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
        if oids == [] and entry.get("oids"):   # it named only options that were not offered: unknown, not none
            conf = None
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
    timeout = budget.left(SECOND_OPINION_MAX_S, reserve=MIN_CALL_S if reasoning_next else 0.0,
                          floor=second_opinion_floor(session), keep=MIN_CALL_S if reasoning_next else 0.0,
                          late_ok=reasoning_next)
    if not fields or timeout is None:
        return None
    try:
        return _with_llm(fields, facts, hint, session, answers, "autofill-pick-second", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model second opinion failed (timeout given %.1f s); Jev's abstentions stand", timeout)
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


# A final abstain, not a miss: the loop must not hand the field to /step (it would be a years question
# answered Yes by the page's own wording rather than the history).
_ASKED = Picked(oids=[], reason="asked")


def _years_first(fields: list[PickField], facts: dict[str, Fact], hint: JobHint | None, session: Session,
                 budget: Budget) -> dict[str, Picked]:
    """The queued level's years questions: the history FIRST (autofill_reasoned.reason_years). Enough
    years shown is its Yes; fewer, or anything it could not read, is left to the user; and only a
    history SILENT about the skill gets the keen Yes, asked as any low_stakes field is (never-list
    stated). An optional pass: a failure leaves its fields to the user."""
    picks, silent = reason_years(fields, facts, session, budget, hint.company if hint else None)
    # Everything the history did not answer Yes and was not silent about is the user's, and final.
    out = {fid: p if p.oids else _ASKED for fid, p in picks.items()}
    rest = [f for f in fields if f.fid in silent]
    if not rest:
        return out
    try:
        picked = None
        if model_settings.get_autofill_engine(session) == "jev":
            try:
                picked, _ = _with_jev(rest, facts, hint, session, {}, level="queued", queued=True)
            except llm.LLMProviderError:
                logger.warning("jev pick failed; the fast model picks this batch")
        if picked is None:
            picked = main_call(budget, lambda timeout: _with_llm(rest, facts, hint, session, {}, timeout=timeout,
                                                                 level="queued", queued=True), "fast pick")
    except llm.LLMProviderError:
        logger.warning("the keen answer to a years question failed; its fields are left to the user")
        return out | {f.fid: _ASKED for f in rest}
    # A years question the keen pick could not answer is final too: /step could only click a blanket Yes.
    return out | {fid: p if p.oids else p.model_copy(update={"reason": "asked"}) for fid, p in picked.items()}


# The veteran answer is a Yes/No ("Are you a veteran?", owner 2026-10-14). A No settles an option that
# DENIES being a veteran, never one that claims it: any chosen option that mentions "veteran" is a claim
# unless it OPENS with a negation (an option "I am a veteran, but not a protected veteran" contains the
# words "not a protected veteran", and "Non-protected veteran" is a veteran too). A Yes claims nothing
# about a protected class. So after a Yes, a QUESTION that names a class, or a list that offers one
# anywhere, is the user's whatever option was chosen: the classes are VEVRAA's (disabled, recently
# separated, active duty wartime or campaign badge, Armed Forces service medal), and a form may name them
# with or without the word "protected". One pattern reads the question, the options and the chosen option.
VETERAN_SLOT = "eeo.veteran_status"
_MENTIONS_VETERAN = re.compile(r"veteran", re.IGNORECASE)
_OPENS_BY_IDENTIFYING = re.compile(r"^\W*i\s+(?:identify\s+as|belong\s+to)\b", re.IGNORECASE)
_OPENS_WITH_NEGATION = re.compile(
    r"^\W*(?:no\b|not\b|non-?veterans?\b|i\s+am\s+not\b|i['\u2019]m\s+not\b|i\s+do\s+not\b|i\s+don['\u2019]?t\b"
    r"|never\s+served\b|i\s+(?:have\s+)?never\b)", re.IGNORECASE)
_NAMES_PROTECTED_CLASS = NAMES_PROTECTED_CLASS
# A bare class as an option after a No: "Disabled", "Recently separated", "Campaign", "Wartime".
_BARE_CLASS = re.compile(r"\b(?:disabled|recently\s+separated|campaign|wartime)\b", re.IGNORECASE)


# A saved Yes says the applicant served at some time, never that they serve now. So a question about
# CURRENT service alone ("Are you currently serving?", "presently a member of the Reserves?") is the user's
# after a Yes. A question that also asks about the past ("currently or have you ever served", "ever")
# is a Yes for a veteran, and so is "active duty" in a question about history: there only an OPTION that
# claims current service ("Yes, I am currently serving") is taken back. A No answers all of them, a person
# who is no veteran serves nowhere, but "not a veteran" is not "never served" for someone in the Guard
# or Reserves, so such a No is the Companion's inference (`veteran_inferred`).
_ASKS_ONLY_CURRENT = re.compile(
    r"\b(?:currently|presently)\b[^?.]{0,40}?\b(?:serv(?:e|es|ed|ing)|active[-\s]duty|member\s+of\s+the\s+(?:military|armed|reserves?|national\s+guard))\b",
    re.IGNORECASE)
_ASKS_THE_PAST = re.compile(r"\b(?:ever|previously|formerly|past)\b|\bhave\s+you\b", re.IGNORECASE)
_CLAIMS_CURRENT_SERVICE = re.compile(
    r"\b(?:currently|presently)\s+(?:serv(?:e|es|ing)|on\s+active|in\s+the|a\s+member)\b"
    r"|\b(?:am|is)\s+(?:now\s+)?serving\b|\bon\s+active[-\s]duty\b", re.IGNORECASE)
_ASKS_SERVICE = re.compile(r"\bserv(?:e|es|ed|ing)\b", re.IGNORECASE)
_SAYS_NEVER_SERVED = re.compile(r"\bnever\s+served\b|\bnot\s+(?:now\s+|currently\s+)?served\b", re.IGNORECASE)


def veteran_inferred(said: str, question: str, chosen: list[str]) -> bool:
    """Whether a saved No answering this question is the Companion's inference: a question about SERVING
    (not about being a veteran), or a chosen option that says "never served"."""
    return said == "No" and (bool(_ASKS_SERVICE.search(question)) or any(_SAYS_NEVER_SERVED.search(t) for t in chosen))


# "No, I am a veteran but not a protected veteran" opens with a negation and still claims to be a veteran.
_NEGATION_THEN_BUT = re.compile(r"\b(?:but|however|except|although|though)\b", re.IGNORECASE)


def _claims_veteran(text: str) -> bool:
    """An option that does not open with a negation and that mentions a veteran, names a protected class, or
    opens "I identify as" / "I belong to"; or one that opens with a negation and then takes it back ("No, I am a
    veteran but not a protected veteran"). A bare "Yes" claims nothing."""
    if _OPENS_WITH_NEGATION.search(text):
        return bool(_NEGATION_THEN_BUT.search(text) and _MENTIONS_VETERAN.search(text))
    return bool(
        _MENTIONS_VETERAN.search(text) or _NAMES_PROTECTED_CLASS.search(text) or _BARE_CLASS.search(text)
        or _OPENS_BY_IDENTIFYING.search(text))


def veteran_said(fact: Fact | None) -> str | None:
    """"Yes" or "No" when the saved veteran answer is one (a decline is neither), else None."""
    if fact is None or not isinstance(fact.value, str):
        return None
    said = yes_no_word(fact.value).split(",", 1)[0]
    return said if said in ("No", "Yes") else None


# "I do not wish to disclose my veteran status" opens with a negation and mentions a veteran, and denies nothing.
_DECLINES = re.compile(r"\b(?:wish|want|prefer|choose|disclose|answer|share|self-?identify|say)\b", re.IGNORECASE)


def veteran_option(fact: Fact | None, question: str, options: list[tuple[str, str]]) -> tuple[str, Reason] | None:
    """A saved No answers a veteran list in code when EXACTLY ONE option opens with a negation and names a
    veteran ("I am not a protected veteran", "No, I am not a veteran"): (its id, the reason), never a model's
    choice (live check 9: polarity timed out twice and the clear option was left). `assumed` when it is the
    Companion's inference (`veteran_inferred`). Never an option that claims to be a veteran, a saved Yes, or
    a list with two such options (the ordinary path decides those)."""
    if veteran_said(fact) != "No":
        return None
    denying = [(oid, text) for oid, text in options
               if _OPENS_WITH_NEGATION.search(text) and _MENTIONS_VETERAN.search(text)
               and not _DECLINES.search(text) and not _claims_veteran(text)]
    if len(denying) != 1:
        return None
    oid, text = denying[0]
    if veteran_overreach("No", question, [t for _, t in options], text):
        return None
    return oid, "assumed" if veteran_inferred("No", question, [text]) else "matched"


def veteran_overreach(said: str, question: str, options: list[str], chosen: str | list[str] | None = None) -> bool:
    """Whether choosing `chosen` (every option, or with None answering at all) would say more than a saved
    `said` does. After a No: a chosen option that claims veteran status. After a Yes: a question or any
    option, offered or chosen, that names a protected class, a question about current service alone, or a
    chosen option that claims current service."""
    picks = [chosen] if isinstance(chosen, str) else list(chosen or [])
    if said == "No":
        return any(_claims_veteran(text) for text in picks)
    asks_only_current = bool(_ASKS_ONLY_CURRENT.search(question)) and not _ASKS_THE_PAST.search(question)
    return asks_only_current or any(_CLAIMS_CURRENT_SERVICE.search(text) for text in picks) or any(
        _NAMES_PROTECTED_CLASS.search(text) for text in (question, *options, *picks))


def _veteran_claims(fields: list[PickField], facts: dict[str, Fact], out: dict[str, Picked]) -> None:
    """Take back a veteran pick that says more than the saved answer does (`veteran_overreach`). The
    abstain is FINAL ("asked"): /step must not take the field over, and it enforces the same rule
    itself. Left to the user."""
    said = veteran_said(facts.get(VETERAN_SLOT))
    if said is None:
        return
    for f in fields:
        picked = out.get(f.fid)
        if f.slot != VETERAN_SLOT or picked is None or picked.reason == "asked":
            continue
        texts = [o.text for o in f.options if o.oid in picked.oids]
        if veteran_overreach(said, f.question, [o.text for o in f.options], texts):
            out[f.fid] = picked.model_copy(update={"oids": [], "reason": "asked"})
        elif picked.reason == "matched" and veteran_inferred(said, f.question, texts):
            out[f.fid] = picked.model_copy(update={"reason": "assumed"})


def named_employers(fields: list[PickField], facts: dict[str, Fact]
                    ) -> tuple[list[PickField], dict[str, Fact], set[str]]:
    """A worked-here field whose question lists a company that is an employer of the history (or whose option
    is one) is picked against Yes, not the derived No (which is about the job's company only): such a field
    is pointed at a slot of its own, holding that fact, so the rest of the batch keeps the fact it had. One
    that lists a parent or a subsidiary of an employer, with no exact match, is neither (`ASK_THE_USER`):
    it leaves the batch and is the user's, for good. The fields to pick, the facts, the dropped fids."""
    moved: dict[str, Fact] = {}
    dropped: set[str] = set()
    out = []
    for f in fields:
        named = (named_employer_fact(facts, f.question, [o.text for o in f.options])
                 if f.slot == WORKED_HERE_SLOT and f.route == "slot" else None)
        if named is None and f.route == "slot" and (other := worked_elsewhere(
                facts, f.slot, f.question, [o.text for o in f.options])):
            moved[WORKED_ELSEWHERE_SLOT] = other
            out.append(f.model_copy(update={"slot": WORKED_ELSEWHERE_SLOT}))
        elif named is None:
            out.append(f)
        elif named == ASK_THE_USER:
            dropped.add(f.fid)
        else:
            slot = f"{WORKED_HERE_SLOT}#{len(moved)}"
            moved[slot] = replace(named, slot=slot)
            out.append(f.model_copy(update={"slot": slot}))
    return (out, facts | moved, dropped) if (moved or dropped) else (fields, facts, dropped)


CITY_SLOT = "personal.city"
DEGREE_SLOT = re.compile(r"education\.\d+\.degree")


def city_picks(fields: list[PickField], facts: dict[str, Fact]) -> tuple[list[PickField], dict[str, Picked]]:
    """A city field whose options are Places-style ("Springfield, IL, USA"): the one that is the saved city in the saved
    state is code's pick (autofill_place); any other list goes the ordinary way. Returns the other fields, and the decided."""
    state = facts.get("personal.state")
    if state is None or not isinstance(state.value, str):
        return fields, {}
    decided = {}
    for f in fields:
        fact = facts.get(f.slot or "")
        if f.route == "slot" and f.slot == CITY_SLOT and isinstance(getattr(fact, "value", None), str) and (
                oid := autofill_place.city_option(fact.value, state.value, [(o.oid, o.text) for o in f.options])):
            decided[f.fid] = Picked(oids=[oid], reason="matched", trace=DecisionTrace())
    return [f for f in fields if f.fid not in decided], decided


def education_picks(fields: list[PickField], facts: dict[str, Fact]) -> tuple[list[PickField], dict[str, Picked]]:
    """The fields asking for the education level (`derived.education_level`) are decided in code, never by a
    model: the highest threshold the applicant's completed level meets, else nobody (autofill_education). So are the
    degree-TYPE lists ("Degree": Master's Degree, M.B.A., …) over a saved degree (`autofill_education.degree_type`). Returns the other fields, and the decided ones' answers."""
    level = facts.get(autofill_education.SLOT)
    decided = {}
    for f in fields:
        if f.route == "slot" and f.slot == autofill_education.SLOT:
            if level is not None and isinstance(level.value, str):
                got = autofill_education.decide(level.value, [(o.oid, o.text) for o in f.options], complete=f.complete)
                decided[f.fid] = Picked(oids=[got.oid] if got.oid else [], reason=got.reason, trace=DecisionTrace())
        elif (f.route == "slot" and DEGREE_SLOT.fullmatch(f.slot or "") and isinstance(getattr(facts.get(f.slot), "value", None), str)
              and (typed := autofill_education.degree_type(facts[f.slot].value, [(o.oid, o.text) for o in f.options],
                                                           complete=f.complete)) is not None):
            decided[f.fid] = Picked(oids=[typed.oid] if typed.oid else [], reason=typed.reason, trace=DecisionTrace())
    return [f for f in fields if f.fid not in decided], decided


def sponsorship_type_picks(fields: list[PickField], facts: dict[str, Fact]) -> tuple[list[PickField], dict[str, Picked]]:
    """A "what type of sponsorship" question under a saved No (autofill_sponsorship): the option that means none /
    not applicable, else nobody. A saved Yes (or no fact) leaves the field to the ordinary path."""
    decided = {}
    for f in fields:
        options = [(o.oid, o.text) for o in f.options]
        fact = facts.get(f.slot or "")
        if (f.route == "slot" and fact is not None and fact.value == "No"
                and autofill_sponsorship.is_type_question(f.slot, f.question, options, facts)):
            oid = autofill_sponsorship.none_option(options)
            decided[f.fid] = Picked(oids=[oid] if oid else [], reason="matched" if oid else "abstained",
                                    trace=DecisionTrace())
    return [f for f in fields if f.fid not in decided], decided


def veteran_picks(fields: list[PickField], facts: dict[str, Fact]) -> tuple[list[PickField], dict[str, Picked]]:
    """The veteran list a saved No settles in code (`veteran_option`), before polarity and any model.
    Returns the other fields, and the decided ones' answers."""
    decided = {}
    for f in fields:
        if f.route == "slot" and f.slot == VETERAN_SLOT and (got := veteran_option(
                facts.get(VETERAN_SLOT), f.question, [(o.oid, o.text) for o in f.options])):
            decided[f.fid] = Picked(oids=[got[0]], reason=got[1], trace=DecisionTrace())
    return [f for f in fields if f.fid not in decided], decided


def pick(fields: list[PickField], facts: dict[str, Fact], session: Session, hint: JobHint | None, *,
         queued: bool = False) -> dict[str, Picked]:
    fields, facts, dropped = named_employers(fields, facts)
    fields, by_code = education_picks(fields, facts)
    fields, cities = city_picks(fields, facts)
    by_code |= cities
    fields, sponsored = sponsorship_type_picks(fields, facts)
    by_code |= sponsored
    fields, veterans = veteran_picks(fields, facts)
    by_code |= veterans
    # Another voluntary-disclosure answer never answers a question that names a veteran: final, the user's.
    cross = {f.fid for f in fields if names_veteran_off_slot(f.slot, f.question, facts.get(f.slot or ""))}
    dropped |= cross
    fields = [f for f in fields if f.fid not in cross]
    budget = Budget()
    # Re-checked, never trusted from the client; `queued` is the server's too (the router reads the job's proposal).
    level = model_settings.get_answer_level(session)
    low_stakes_on = level != "facts"
    # A low-stakes or reasoned field carries no slot: one that names a slot is
    # a fact field the client mis-routed, and a guess would answer it.
    askable = [f for f in fields
               if (f.route == "low_stakes" and low_stakes_on and not f.slot)
               or (f.route == "slot" and values_for(f, facts.get(f.slot or "")))]
    reasoned = [f for f in fields if f.route == "reasoned" and not f.slot]
    asked = {f.fid for f in askable + reasoned}
    # Level "queued" on a queued job: a years-with-a-skill question asks the history before it may be a keen Yes.
    years = [f for f in askable if f.route == "low_stakes" and level == "queued" and queued
             and asks_years(f.question, f.years)]
    askable = [f for f in askable if f not in years]
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
                picked, tops = _with_jev(askable, facts, hint, session, answers, level=level, queued=queued)
            except llm.LLMProviderError:
                logger.warning("jev pick failed; the fast model picks this batch")
        if picked is None:
            # One request of what is left of the budget, no retries: a slow
            # batch never outlives the Companion's wait.
            picked = main_call(budget, lambda timeout: _with_llm(askable, facts, hint, session, answers,
                                                                 timeout=timeout, level=level, queued=queued),
                               "fast pick")
        else:
            unsure = [f for f in askable if f.route == "slot" and abstained(picked[f.fid])]
            second = _second_opinion(unsure, facts, hint, session, budget, answers,
                                     reasoning_next=bool(reasoned))
            if n_decided := _with_second_opinion(picked, tops, unsure, second):
                logger.info("pick: the fast model decided %d of %d fields Jev abstained on", n_decided, len(unsure))
        out |= picked
    if years:
        out |= _years_first(years, facts, hint, session, budget)
    if reasoned:
        out |= reason(reasoned, facts, session, budget, hint.company if hint else None, level)
    _veteran_claims(fields, facts, out)
    for f in fields:
        if f.fid in out and out[f.fid].reason == "matched" and relocate_qualified(f, facts.get(f.slot or "")):
            out[f.fid] = out[f.fid].model_copy(update={"reason": "assumed"})
    _with_polarity(out, ways)
    return out | by_code | {fid: _ASKED for fid in dropped}
