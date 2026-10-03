"""/step — the next move for a field the generic path could not finish.

Jev picks ONE candidate move id (the page's code generated them from the live
widget) or `give_up`. Clicking an option is a semantic answer and must clear
the slot's match floor through the same `verdict` /pick uses (a flag slot may
take a `closest` click only on a complete view). A move that is not an answer —
open, search, scroll, or a click the page described as opening a group
("Open the group …") — only needs PROGRESS_FLOOR and answers `progress`; the
loop sends that click `as: "progress"`. A plain click is an answer or nothing:
an unmarked category (Workday's "Job Board" on the way to "LinkedIn") is an
answer click the page reports as progressed when its children appear. The
fact comes from the SLOT, server-side; the request carries none. Low-stakes
(setting re-checked here, never trusted from the client) is only for a field
with no slot, and states the never-list; its answer click is `assumed` at
ASSUMED_FLOOR (0.4) and its other moves need PROGRESS_FLOOR like any field's.
The fast model is the same-floors fallback when Jev fails and, for a slot
field, ONE second opinion when Jev gives up or its move is under its floor, on
the request's `Budget` (out of time or failed, Jev's give-up stands).
"""

import json
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import DecisionTrace, Engine, StepRequest, StepResponse
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA
from app.services.autofill_map import (
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
from app.services.autofill_pick import (
    NEVER_YES_NO,
    Computed,
    JobHint,
    polarity_answers,
    polarity_trace,
    polarity_ways,
    values_for,
    verdict,
)

logger = logging.getLogger(__name__)

PROGRESS_FLOOR = 0.5
GIVE_UP = "give_up"
# The page's description of a click that opens a group of options (fill-core
# stepState). Page text only ever follows it, JSON-quoted.
GROUP_CLICK = "Open the group "
CLICK_RULE = ("Click an option if it is the goal's answer to the question as worded, or if it looks like a "
              "category whose sub-options will contain that answer; open a group only if its sub-options will "
              "contain it. Never click an option that neither is that answer nor leads to it.")
_GIVE_UP_TEXT = "Stop: no move will select the goal's answer to the question"
# For a return that carries no trace (a request no model was asked about). An abstain that has
# a trace is a fresh StepResponse, so it never equals this one: ask `abstained`, never compare with it.
ABSTAIN = StepResponse(mid=None, reason="abstained")
_LLM_PROMPT = """{instructions}
State: {state}
Moves (id: what it does): {moves}
Return JSON {{"move": "<move id>", "confidence": <0..1>}}."""


def _is_answer(req: StepRequest, mid: str) -> bool:
    """A click selects an answer — unless the page described it as opening a group."""
    describe = next(c.describe for c in req.candidates if c.mid == mid)
    return mid.startswith("click:") and not describe.startswith(GROUP_CLICK)


def abstained(r: StepResponse) -> bool:
    """No move was chosen. Tested by content: `==` compares the trace too, so a
    response carrying one never equals ABSTAIN."""
    return r.mid is None


def _decide(req: StepRequest, mid: str | None, p: float | None, policy: str, *,
            engine: Engine) -> StepResponse:
    """The move as a StepResponse, with how it was decided. `p` None: the model's
    confidence was unreadable (or Jev gave no readable answer); it routes as 0.0 and is
    never traced as a 0.0 it did not say."""
    mid = None if mid == GIVE_UP else mid
    if mid and _is_answer(req, mid):
        picked = verdict(req, mid, p, policy, engine=engine)
        return StepResponse(mid=picked.oids[0] if picked.oids else None, reason=picked.reason,
                            trace=picked.trace)
    return _progress(mid, p, engine)


def _progress(mid: str | None, p: float | None, engine: Engine) -> StepResponse:
    """A move that is not an answer click, or none: a give-up or no move. A progress move needs
    PROGRESS_FLOOR. A give-up (or no move) has no floor of its own; it carries the same one, so
    every non-answer step trace reads against one bar. `chose_none`: the top choice was give_up
    or no move (None when neither a move nor a confidence was readable)."""
    trace = DecisionTrace(engine=engine, p=p, floor=PROGRESS_FLOOR,
                          chose_none=None if not mid and p is None else not mid)
    if mid and (p or 0.0) >= PROGRESS_FLOOR:
        return StepResponse(mid=mid, reason="progress", trace=trace)
    return StepResponse(mid=None, reason="abstained", trace=trace)


def _instructions(req: StepRequest, values: list[str], hint: JobHint | None, facts: dict[str, Fact],
                  answer: Computed | None = None) -> str:
    field = f"form field {req.fid} ({json.dumps(req.question)})"
    if req.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), that is the one."
               if hint and hint.source else "")
        # The never-list first, as its own condition: see autofill_map.low_stakes_rule.
        goal = (f"You are filling {field} on a job application; the applicant gave no answer to it. "
                f"{low_stakes_rule(facts, 'give up (the "Stop" move)')}; for such a field, the goal is to select the option "
                f"{keen(facts)}.{src}")
    elif answer is not None:
        # A Yes/No fact: its polarity decided and the value flipped by code
        # (autofill_pick.polarity_answers); the goal is literal.
        that_is = f"; that is, {answer.statement}" if answer.statement else ""
        goal = (f"You are filling {field} on a job application. For the applicant, the answer to the question is "
                f"{json.dumps(answer.answer)}{that_is}: the goal is to select the option that states that answer.")
    else:
        fact = facts[req.slot]
        goal = (f"You are filling {field} on a job application. The goal is to select the option that means the "
                f"same as the applicant's fact {json.dumps(fact.describe)}: {json.dumps(values[0])}. {NEVER_YES_NO}")
    return (f"{goal} "
            f"The moves tried so far are the state's history. Which next move gets closer to that goal? {CLICK_RULE} "
            f"Give up when no move will. {_PAGE_TEXT_IS_DATA}")


@dataclass(frozen=True)
class _Ask:
    """What one step asks a model, built once per request: the prompt's instructions and state, the
    moves on offer (mid -> describe), and the fact's policy."""

    instructions: str
    state: dict
    criteria: dict[str, str]
    policy: str


def _with_llm(req: StepRequest, ask: _Ask, session: Session, trace_name: str = "autofill-step", *,
              timeout: float | None = None) -> StepResponse:
    criteria = ask.criteria
    raw = fast_json(session, _LLM_PROMPT.format(
        instructions=ask.instructions, state=json.dumps(ask.state), moves=json.dumps(criteria)),
        trace_name, timeout=timeout)
    raw = raw if isinstance(raw, dict) else {}
    move = raw.get("move")
    mid = move if isinstance(move, str) and move in criteria else None
    conf = raw.get("confidence")
    # A move that was not offered is unknown, not a give-up: no p, so `chose_none` stays None.
    p = float(conf) if jev._unit(conf) and not (move and mid is None) else None
    return _decide(req, mid, p, ask.policy, engine="fast")


def _second_opinion(req: StepRequest, ask: _Ask, session: Session, budget: Budget) -> StepResponse | None:
    """ONE fast-model move for a slot field Jev gave up on, on what is left of
    the request's budget, capped (a give-up step costs at most Jev's 2 s plus
    this against the field's clock), at the same floors. None: it never ran
    (out of time, or it failed), and Jev's give-up stands."""
    if (timeout := budget.left(SECOND_OPINION_MAX_S)) is None:
        return None
    try:
        second = _with_llm(req, ask, session, "autofill-step-second", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model second opinion failed; Jev's give-up stands")
        return None
    if not abstained(second):
        logger.info("step: the fast model decided a move Jev gave up on")
    return second


def _with_second_opinion(jev_says: StepResponse, top: Top | None, second: StepResponse | None) -> StepResponse:
    """The second opinion's move, traced against Jev's top choice `top`, if it decided; else
    Jev's abstain, marked asked if the second opinion ran. `second` None: it never ran."""
    if second is None:
        return jev_says
    if abstained(second):
        return jev_says.model_copy(update={"trace": second_asked(jev_says.trace)})
    return second.model_copy(update={"trace": second_decided(second.trace, top, second.mid)})


def _move(req: StepRequest, ask: _Ask, session: Session, budget: Budget) -> StepResponse:
    """The next move, by the engine the setting names."""
    # The fast step (its engine, or Jev's failure fallback) is one request of
    # what is left of the budget, no retries.
    if model_settings.get_autofill_engine(session) != "jev":
        return main_call(budget, lambda timeout: _with_llm(req, ask, session, timeout=timeout), "fast step")
    try:
        answer = jev.decide({req.fid: jev.choice_question(ask.instructions, ask.criteria)}, ask.state, session)
    except llm.LLMProviderError:
        logger.warning("jev step failed; the fast model decides this move")
        return main_call(budget, lambda timeout: _with_llm(req, ask, session, timeout=timeout), "fast step")
    got = jev.choice_of(answer.get(req.fid), ask.criteria)
    decided = _decide(req, got.choice if got else None, got.probability if got else None, ask.policy, engine="jev")
    # A low-stakes step keeps its engine.
    if not abstained(decided) or req.route != "slot":
        return decided
    second = _second_opinion(req, ask, session, budget)
    return _with_second_opinion(decided, (got.choice, got.probability) if got else None, second)


def step(req: StepRequest, facts: dict[str, Fact], session: Session, hint: JobHint | None) -> StepResponse:
    budget = Budget()
    if req.route == "low_stakes":
        # Re-checked here, not trusted from the client; and a field naming a
        # slot is a fact field — a keen-applicant guess would answer it.
        if req.slot or not model_settings.get_autofill_low_stakes(session):
            return ABSTAIN
        fact = None
    else:
        fact = facts.get(req.slot or "")
    values = values_for(req, fact)
    if req.route == "slot" and not values:
        return ABSTAIN
    policy = fact.policy if fact else "any"
    # A Yes/No fact: this request decides its question's polarity itself; unsure, the step gives up.
    answer = polarity = None
    if req.route == "slot" and fact.yes_no:
        ways = polarity_ways([req], facts, session, budget)
        polarity = polarity_trace(ways[req.fid])
        answer = polarity_answers([req], facts, ways).get(req.fid)
        if answer is None:
            return StepResponse(mid=None, reason="abstained", polarity=polarity)
    criteria = {c.mid: c.describe for c in req.candidates if c.mid != GIVE_UP} | {GIVE_UP: _GIVE_UP_TEXT}
    ask = _Ask(_instructions(req, values, hint, facts, answer),
               {"job": asdict(hint) if hint else None, "history": req.history}, criteria, policy)
    moved = _move(req, ask, session, budget)
    return moved.model_copy(update={"polarity": polarity})
