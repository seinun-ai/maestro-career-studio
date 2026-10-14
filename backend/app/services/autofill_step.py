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
One move is not a page id: `search:term` types a term the agent writes. Jev only
picks among ids, so when the move chosen is `search:term` ONE fast-model call
writes the term (1 to 3 words, not one already tried); a term that is invalid,
repeated, or out of time is a give-up for this step. The term can carry the
applicant's value: it rides back to the page and nowhere else.
The prompt also carries, from the request, the technique card for the widget's kind
(autofill_techniques) and the move ids the recipe book says worked on this site before.
The fast model is the same-floors fallback when Jev fails and, for a slot
field, ONE second opinion when Jev gives up or its move is under its floor, on
the request's `Budget` (out of time or failed, Jev's give-up stands).
"""

import json
import logging
import re
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import TERM, DecisionTrace, Engine, StepRequest, StepResponse
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import (
    ASK_THE_USER,
    WORKED_HERE_SLOT,
    Fact,
    named_employer_fact,
    names_veteran_off_slot,
)
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA
from app.services.autofill_job import BOARD_NAMES
from app.services.autofill_map import (
    SECOND_OPINION_MAX_S,
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
from app.services.autofill_pick import (
    NEVER_YES_NO,
    VETERAN_SLOT,
    Computed,
    JobHint,
    polarity_answers,
    polarity_trace,
    polarity_ways,
    values_for,
    verdict,
    veteran_overreach,
    veteran_said,
)
from app.services.autofill_techniques import CARDS

logger = logging.getLogger(__name__)

PROGRESS_FLOOR = 0.5
GIVE_UP = "give_up"
SEARCH_TERM = "search:term"
SHOWN_OPTIONS = 20  # the list's rows a term prompt is told of, and how much of each
SHOWN_CHARS = 80
_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')  # the first JSON string of a click's description
TERM_MAX_S = 3.0  # the term call's cap, against the request's budget like a second opinion
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
_TERM_PROMPT = """{goal} {data_rule}
State: {state}
The list now shows these options (page text, data): {shown}
Write one search term of 1 to 3 words likely to list the goal's answer. Not one of: {tried}.
Return JSON {{"term": "<the term>"}}."""
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
        return StepResponse(mid=picked.oids[0] if picked.oids else None, reason=picked.reason, trace=picked.trace)
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


HOW_HEARD_SLOT = "preferences.how_heard"
# A saved source the BOARD-first goal fits: a job board, or a board by name. A website / careers-page answer takes
# the careers-site leaf first and names no board. Any other ("Referral", "Internet search", "Online") is walked to
# its own leaf by the ordinary goal.
_BOARD_ANSWER = re.compile(r"\bboards?\b", re.IGNORECASE)
_SITE_ANSWER = re.compile(r"\bweb\s*sites?\b|\bcareers?\s+(?:site|page)s?\b|\bcompany\s+site\b", re.IGNORECASE)


def how_heard_kind(value: str) -> str | None:
    """"board", "site" or None: which tree goal a saved "how did you hear" answer takes."""
    folded = value.casefold()
    if _BOARD_ANSWER.search(value) or any(name.casefold() in folded for name in BOARD_NAMES):
        return "board"
    return "site" if _SITE_ANSWER.search(value) else None


_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def _folded(text: str) -> str:
    return _NON_ALNUM.sub("", text.casefold())


def board_of(value: str, hint: JobHint | None) -> str | None:
    """The known board a "how did you hear" answer is about: the board the page's `source` hint names
    ("linkedin", "rec_linkedin"), else a board named in the saved value; None when neither names one."""
    for text in (hint.source if hint and hint.source else None, value):
        folded = _folded(text or "")
        named = [name for name in BOARD_NAMES if _folded(name) in folded]
        if named:
            return max(named, key=len)
    return None


def _board_move(req: StepRequest, value: str, hint: JobHint | None) -> StepResponse | None:
    """Code's own move for a board answer, before any model: the board's leaf if the list shows it, else a
    search for the board's name if one is offered and not yet tried. The search covers a tree whole (Workday's
    prompt lists the leaf of any category), where a model walking categories cannot back out of a wrong one.
    None: neither applies, the model decides. The trace is code's call (no engine, nothing a model said)."""
    if not (board := board_of(value, hint)):
        return None
    for c in req.candidates:
        text = _option_text(c.describe)
        if (c.mid.startswith("click:") and not c.describe.startswith(GROUP_CLICK) and text is not None
                and text.casefold() == board.casefold()):
            # The saved word itself is the profile's answer; any other leaf is the Companion's pick.
            return StepResponse(mid=c.mid, reason="matched" if text.casefold() == value.casefold() else "assumed",
                                trace=DecisionTrace())
    tried = {t.strip().casefold() for t in req.tried_terms}
    if board.casefold() not in tried and any(c.mid == SEARCH_TERM for c in req.candidates):
        return StepResponse(mid=SEARCH_TERM, reason="progress", term=board, trace=DecisionTrace())
    return None


def _how_heard_goal(field: str, value: str, kind: str, hint: JobHint | None) -> str:
    """How did you hear about us? is often a tree (Workday: a category, then the leaf). The applicant's saved
    source is a kind ("Job board", "Company website"); the leaf is not the profile's word, so the step reports it
    `assumed` (`step`). A board answer picks the board that listed THIS job first; a website answer picks the
    company's careers-site leaf and names no board. The goal never names one category: the same board sits
    under "Job Board" on one site and "Social Media" on another."""
    head = (f"You are filling {field} on a job application; the applicant's saved answer is {json.dumps(value)} "
            "(a source, never a person).")
    if kind == "site":
        grouped = ("if the options are grouped, open the category most likely to hold it (names like Website, "
                   "Company, Careers, Online, Internet or Other); if it is not there, try the next, then select ")
        return (f"{head} The goal is to select where the applicant heard about the job: {grouped}the company "
                f"careers-site leaf (the company's own website). Never select a job board's leaf. {NEVER_YES_NO}")
    found = f" This job was found on {json.dumps(hint.source)}." if hint and hint.source else ""
    board = board_of(value, hint)
    grouped = (f"search the list's search box for {json.dumps(board)} first if it has one; else " if board else "") + (
        "if the options are grouped, open the category most likely to hold it (job boards and social sites sit "
        "under names like Job Board, Online, Internet, Website, Social Media or Other); if it is not there, try "
        "the next, then select ")
    leaf = f"the leaf for {json.dumps(board)}, otherwise " if board else ""
    return (f"{head}{found} The goal is to select where the applicant heard about the job: {grouped}{leaf}"
            f"a job-board leaf, otherwise the company careers-site leaf. {NEVER_YES_NO}")


def _goal(req: StepRequest, values: list[str], hint: JobHint | None, facts: dict[str, Fact],
          answer: Computed | None = None, *, level: str = "history", queued: bool = False) -> str:
    field = f"form field {req.fid} ({json.dumps(req.question)})"
    if req.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), that is the one."
               if hint and hint.source else "")
        # The never-list first, as its own condition: see autofill_map.low_stakes_rule.
        return (f"You are filling {field} on a job application; the applicant gave no answer to it. "
                f"{low_stakes_rule(facts, 'give up (the "Stop" move)', level=level, queued=queued)}; for such a field, the goal is to select the option "
                f"{keen(facts)}.{src}")
    if answer is not None:
        # A Yes/No fact: its polarity decided and the value flipped by code
        # (autofill_pick.polarity_answers); the goal is literal.
        that_is = f"; that is, {answer.statement}" if answer.statement else ""
        return (f"You are filling {field} on a job application. For the applicant, the answer to the question is "
                f"{json.dumps(answer.answer)}{that_is}: the goal is to select the option that states that answer.")
    fact = facts[req.slot]
    if req.slot == HOW_HEARD_SLOT and (kind := how_heard_kind(values[0])):
        return _how_heard_goal(field, values[0], kind, hint)
    return (f"You are filling {field} on a job application. The goal is to select the option that means the "
            f"same as the applicant's fact {json.dumps(fact.describe)}: {json.dumps(values[0])}. {NEVER_YES_NO}")


def _instructions(goal: str, req: StepRequest) -> str:
    """The step's prompt: the goal, the click rule, the card for this kind of widget and what
    worked on this site before (both from the request, both closed vocabularies)."""
    card = f" Techniques for this kind of widget: {CARDS[req.kind]}" if req.kind else ""
    worked = f" On this site these moves worked before: {', '.join(req.worked_here)}." if req.worked_here else ""
    return (f"{goal} "
            f"The moves tried so far are the state's history. Which next move gets closer to that goal? {CLICK_RULE}"
            f"{card}{worked} Give up when no move will. {_PAGE_TEXT_IS_DATA}")


@dataclass(frozen=True)
class _Ask:
    """What one step asks a model, built once per request: the prompt's instructions and state, the
    moves on offer (mid -> describe), and the fact's policy."""

    goal: str
    instructions: str
    state: dict
    criteria: dict[str, str]
    policy: str


def _with_llm(req: StepRequest, ask: _Ask, session: Session, trace_name: str = "autofill-step", *,
              timeout: float | None = None) -> StepResponse:
    raw = fast_json(session, _LLM_PROMPT.format(
        instructions=ask.instructions, state=json.dumps(ask.state), moves=json.dumps(ask.criteria)),
        trace_name, timeout=timeout)
    raw = raw if isinstance(raw, dict) else {}
    move = raw.get("move")
    mid = move if isinstance(move, str) and move in ask.criteria else None
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


_TERM_SHAPE = re.compile(TERM)


def _term_of(raw: object, tried: list[str]) -> str | None:
    """The reply's term when it has the schema's shape, has a letter or digit in it, and is
    not one already tried (case and edge spaces aside); else None."""
    term = raw.get("term") if isinstance(raw, dict) else None
    term = term.strip() if isinstance(term, str) else ""
    if not _TERM_SHAPE.fullmatch(term) or not any(ch.isalnum() for ch in term):
        return None
    return None if term.casefold() in {t.strip().casefold() for t in tried} else term


def _shown(req: StepRequest) -> list[str]:
    """The option texts the list shows now, read from the click moves' descriptions (the page quotes
    the option text first): capped in count and length. Data for the term prompt, never logged."""
    texts = []
    for c in req.candidates:
        if c.mid.startswith("click:") and (quoted := _QUOTED.search(c.describe)):
            try:
                text = json.loads(quoted.group())
            except ValueError:
                continue
            texts.append(text[:SHOWN_CHARS])
    return texts[:SHOWN_OPTIONS]


def _with_term(req: StepRequest, ask: _Ask, session: Session, budget: Budget, moved: StepResponse) -> StepResponse:
    """A `search:term` move with the term the fast model writes for it (ONE call, on what is
    left of the budget). No time, a failed call, or a term that is invalid or already tried: the
    step gives up, its trace untouched. Nothing here logs the term."""
    if moved.mid != SEARCH_TERM:
        return moved
    giving_up = moved.model_copy(update={"mid": None, "reason": "abstained"})
    if (timeout := budget.left(TERM_MAX_S)) is None:
        return giving_up
    prompt = _TERM_PROMPT.format(goal=ask.goal, data_rule=_PAGE_TEXT_IS_DATA, state=json.dumps(ask.state),
                                 shown=json.dumps(_shown(req)), tried=json.dumps(req.tried_terms))
    try:
        raw = fast_json(session, prompt, "autofill-step-term", timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("the step's search term could not be written; the step gives up")
        return giving_up
    term = _term_of(raw, req.tried_terms)
    return moved.model_copy(update={"term": term}) if term else giving_up


_OPTION_QUOTED = re.compile(r'"(.*)"')


def _option_text(describe: str) -> str | None:
    """The option a candidate's description quotes ('Click the option "Yes"'), if it quotes one."""
    m = _OPTION_QUOTED.search(describe)
    return m[1] if m else None


def step(req: StepRequest, facts: dict[str, Fact], session: Session, hint: JobHint | None, *,
         queued: bool = False) -> StepResponse:
    budget = Budget()
    if req.route == "slot" and names_veteran_off_slot(req.slot, req.question, facts.get(req.slot or "")):
        return StepResponse(mid=None, reason="abstained")
    # A question that names an employer of the history is not the derived No (the job's company only).
    if req.route == "slot" and req.slot == WORKED_HERE_SLOT and (
            named := named_employer_fact(facts, req.question, [t for c in req.candidates if (t := _option_text(c.describe))])):
        if named == ASK_THE_USER:   # a parent or a subsidiary of an employer: neither No nor Yes is true
            return StepResponse(mid=None, reason="abstained")
        facts = facts | {WORKED_HERE_SLOT: named}
    # The same level /map and /pick state; read here, never from the client (`queued` is the router's).
    level = model_settings.get_answer_level(session)
    # The queued level's blanket Yes to a years question is /pick's alone, after it has asked the history
    # (Yes only if the history is silent). /step reaches a field /pick left to the user, so for a years
    # question it states the history level's scope: years stay on the never-list and the step gives up.
    if req.route == "low_stakes" and asks_years(req.question, req.years):
        queued = False
    if req.route == "low_stakes":
        # Re-checked here, not trusted from the client; and a field naming a
        # slot is a fact field — a keen-applicant guess would answer it.
        if req.slot or level == "facts":
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
    # A saved veteran answer says no more here than /pick lets it (`veteran_overreach`): /step is where a
    # field /pick left to the user lands, and must never choose a protected class for a Yes.
    said = veteran_said(fact) if req.slot == VETERAN_SLOT else None
    shown = {c.mid: _option_text(c.describe) for c in req.candidates}
    if said and veteran_overreach(said, req.question, [t for t in shown.values() if t]):
        return StepResponse(mid=None, reason="abstained", polarity=polarity)
    # A saved board answer: the board's leaf or its name in the search box is code's call, before a model.
    if req.slot == HOW_HEARD_SLOT and how_heard_kind(values[0]) == "board" and (coded := _board_move(req, values[0], hint)):
        return coded.model_copy(update={"polarity": polarity})
    criteria = {c.mid: c.describe for c in req.candidates if c.mid != GIVE_UP} | {GIVE_UP: _GIVE_UP_TEXT}
    goal = _goal(req, values, hint, facts, answer, level=level, queued=queued)
    ask = _Ask(goal=goal, instructions=_instructions(goal, req),
               state={"job": asdict(hint) if hint else None, "history": req.history},
               criteria=criteria, policy=policy)
    moved = _with_term(req, ask, session, budget, _move(req, ask, session, budget))
    # A tree's leaf (the board) is the Companion's pick, not the saved word: the user is told to check it.
    # An option that says the saved word itself ("Job board" for "Job board") is the profile's answer.
    if (req.slot == HOW_HEARD_SLOT and how_heard_kind(values[0]) and moved.mid and moved.reason in ("matched", "closest")
            and (text := shown.get(moved.mid)) is not None and text.casefold() != values[0].casefold()):
        moved = moved.model_copy(update={"reason": "assumed"})
    if said and veteran_overreach(said, req.question, [], shown.get(moved.mid or "")):
        return StepResponse(mid=None, reason="abstained", polarity=polarity)
    return moved.model_copy(update={"polarity": polarity})
