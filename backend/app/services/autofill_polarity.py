"""Polarity — does a question ask the SAME thing as a Yes/No fact, or the OPPOSITE?

Owner decision (2026-09-27), after the final evaluation: asked in one shot to
judge a reversed question, flip the answer and pick an option, both engines
answered knockout questions backwards ("authorized to work WITHOUT
sponsorship?" with "will need sponsorship: No" → "No"). So the work is split:

1. the AI judges ONLY whether the question asks the same thing as the fact's
   value-free description, its opposite (a reverse or a negation), or neither
   — the value is not sent;
2. code flips a plain "Yes" / "No" for an opposite question (`answer_for`); a
   wordy value ("No, I do not have a disability", "Yes, previously") is never
   rewritten, so an opposite question about one is left to the user;
3. /pick and /step then ask a LITERAL question: which option states that answer.

Only for a Yes/No fact (`Fact.yes_no`). Jev first over code-owned keys, at
max(the slot's floor, POLARITY_FLOOR). A confident Jev `neither` abstains; where
Jev is unsure (under the floor, or no readable answer) ONE fast second opinion
at the same floor, on the request's `Budget`; still unsure, the field abstains.
On the `fast` engine, or when the Jev call fails, the fast model decides.

A confident answer (same, opposite, or Jev's neither) is REMEMBERED in this
process for MEMORY_TTL_S by (question, fact description, policy) — page text
and a value-free description, never a value — so a /step after a /pick, or the
next run on the same form, does not ask again. An unsure one never is.
"""

import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Engine
from app.services import jev, llm, model_settings
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, MATCH_FLOOR
from app.services.autofill_map import MIN_CALL_S, Budget, fast_json

logger = logging.getLogger(__name__)

Way = Literal["same", "opposite", "neither"]
SAME, OPPOSITE, NEITHER = "same", "opposite", "neither"
# A flip is a knockout answer's direction: never taken on a slot's lower match
# floor alone (an `any` slot matches at 0.5).
POLARITY_FLOOR = 0.8
# The fast polarity call's cap, and how long before OPTIONAL_PASS_BUDGET_S it
# must end. What may follow it in the request, worst case: Jev's pick or step
# (jev.TIMEOUT_S = 2 s), then that pick's or step's fast second opinion (it
# needs MIN_CALL_S = 1 s, and must START before the 6 s mark), then /pick's
# reasoning call (1 s more, and it too must start before 6 s). So polarity ends
# by 6 - (2 + 1 + 1) = 2 s into the request: asked at 0.5 s it gets 1.5 s; the
# pick runs to 4 s, its second opinion to 5 s, and the reasoning call starts at
# 5 s with what is left of REQUEST_BUDGET_S. (Budget.left never gives under
# MIN_CALL_S, so a polarity asked later than 1 s still takes 1 s.)
POLARITY_MAX_S = 2.0
POLARITY_RESERVE_S = jev.TIMEOUT_S + 2 * MIN_CALL_S
# The memory: this long, this many entries (the least recently kept goes first).
MEMORY_TTL_S = 600.0
MEMORY_MAX = 500
_clock = time.monotonic
# SAME is wide on purpose: most forms ask a knockout or EEO question with an
# undirected label ("Protected veteran status", "Age requirement",
# "Employment with this company" over Current / Former / Not Applicable), and
# reading those as neither would leave the most common fields unfilled.
# OPPOSITE and NEITHER stay tight.
CRITERIA = {
    SAME: "Same: the question asks what the fact says, or asks about it without a direction of its own (a label "
          "whose words do not negate or reverse the fact, such as a status label whose options state it; if its "
          "words do negate or reverse it, it is Opposite), so the fact's answer is the question's answer",
    OPPOSITE: "Opposite: the question asks the reverse or a negation of the fact, so a Yes to the fact is a No "
              "to the question",
    NEITHER: "Neither: the question asks about something else",
}
_LLM_PROMPT = """For each form field, does its question ask the same thing as the applicant fact named beside it,
or its opposite (the reverse or a negation of it), or neither? {rule}
Keys: {keys}
Return JSON {{"polarity": {{"<field id>": {{"key": "<key>", "confidence": <0..1>}}}}}}.
Fields: {fields}
"""


@dataclass(frozen=True)
class Ask:
    """One field's polarity question: its wording and its fact's value-free
    description. `policy`: the fact's, whose match floor a decision must clear."""

    fid: str
    question: str
    describe: str
    policy: str


@dataclass(frozen=True)
class Polarity:
    way: Way | None   # None: unsure; neither: decided, but no answer — both leave the field to the user
    engine: Engine | None   # which engine decided
    # The deciding answer's probability (value-free: the fill trace reads it). A
    # remembered polarity keeps it. None: nothing decided.
    p: float | None = None


UNSURE = Polarity(None, None)
_memory: "OrderedDict[tuple[str, str, str], tuple[float, Polarity]]" = OrderedDict()
_memory_lock = threading.Lock()


def _key(a: Ask) -> tuple[str, str, str]:
    return (a.question, a.describe, a.policy)


def _remember(key: tuple[str, str, str], polarity: Polarity) -> None:
    with _memory_lock:
        _memory[key] = (_clock(), polarity)
        _memory.move_to_end(key)
        while len(_memory) > MEMORY_MAX:
            _memory.popitem(last=False)


def _recall(key: tuple[str, str, str]) -> Polarity | None:
    with _memory_lock:
        held = _memory.get(key)
        if held is None:
            return None
        if _clock() - held[0] > MEMORY_TTL_S:
            del _memory[key]
            return None
        return held[1]


def forget() -> None:
    """Drop everything remembered (tests; the evaluation between engines)."""
    with _memory_lock:
        _memory.clear()


def answer_for(value: str, way: str | None) -> str | None:
    """The applicant's answer to the question as worded: the value for a same
    question; for an opposite one, a plain Yes or No flipped — a wordy value is
    never rewritten (None: abstain)."""
    if way == SAME:
        return value
    if way == OPPOSITE and value in ("Yes", "No"):
        return "No" if value == "Yes" else "Yes"
    return None


def _payload(asks: list[Ask]) -> list[dict]:
    return [{"id": a.fid, "question": a.question, "fact": a.describe} for a in asks]


def _with_jev(asks: list[Ask], session: Session) -> dict[str, tuple[str, float]]:
    questions = {
        a.fid: jev.choice_question(
            f"Does form field {a.fid} ({json.dumps(a.question)}) ask the same thing as the applicant fact "
            f"{json.dumps(a.describe)}, or its opposite (the reverse or a negation of it)? " + _PAGE_TEXT_IS_DATA,
            CRITERIA)
        for a in asks
    }
    answers = jev.decide(questions, {"fields": _payload(asks)}, session)
    out = {}
    for a in asks:
        if picked := jev.choice_of(answers.get(a.fid), CRITERIA):
            out[a.fid] = (picked.choice, picked.probability)
    return out


def _with_llm(asks: list[Ask], session: Session, trace_name: str, *, timeout: float) -> dict[str, tuple[str, float]]:
    raw = fast_json(session, _LLM_PROMPT.format(
        rule=_PAGE_TEXT_IS_DATA, keys=json.dumps(CRITERIA), fields=json.dumps(_payload(asks))),
        trace_name, timeout=timeout)
    got = raw.get("polarity") if isinstance(raw, dict) else None
    asked = {a.fid for a in asks}
    out = {}
    for fid, entry in (got.items() if isinstance(got, dict) else ()):
        if fid not in asked or not isinstance(entry, dict):
            continue
        key, conf = entry.get("key"), entry.get("confidence")
        if key in CRITERIA and jev._unit(conf):
            out[fid] = (key, float(conf))
    return out


def _fast(asks: list[Ask], session: Session, budget: Budget, trace_name: str) -> dict[str, tuple[str, float]]:
    """One fast-model call, capped (POLARITY_MAX_S) and ending in time for what
    follows it (POLARITY_RESERVE_S). Out of time or failed: nothing."""
    timeout = budget.left(POLARITY_MAX_S, reserve=POLARITY_RESERVE_S)
    if not asks or timeout is None:
        return {}
    try:
        return _with_llm(asks, session, trace_name, timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model polarity (%s) failed; its fields are left to the user", trace_name)
        return {}


def _second_opinion(asks: list[Ask], session: Session, budget: Budget) -> dict[str, tuple[str, float]]:
    return _fast(asks, session, budget, "autofill-polarity-second")


def floor_of(policy: str) -> float:
    return max(MATCH_FLOOR.get(policy, MATCH_FLOOR["exact"]), POLARITY_FLOOR)


def _accepted(answer: tuple[str, float] | None, policy: str) -> str | None:
    """A confident answer's way (same, opposite or neither), else None."""
    if answer is None:
        return None
    key, p = answer
    return key if key in CRITERIA and p >= floor_of(policy) else None


def decide(asks: list[Ask], session: Session, budget: Budget) -> dict[str, Polarity]:
    """Per field: same, opposite, neither (decided, no answer), or UNSURE —
    and which engine decided. A confident Jev neither gets no second opinion;
    only an under-floor or unreadable answer does."""
    if not asks:
        return {}
    out: dict[str, Polarity] = {}
    for a in asks:
        if (held := _recall(_key(a))) is not None:
            out[a.fid] = held
            logger.info("polarity: field %s %s (remembered, by %s)", a.fid, held.way, held.engine)
    todo = [a for a in asks if a.fid not in out]
    if not todo:
        return out
    decided: dict[str, Polarity] = {}
    fast_asks = todo
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            got = _with_jev(todo, session)
        except llm.LLMProviderError:
            logger.warning("jev polarity failed; the fast model decides these fields")
            fast = _fast(todo, session, budget, "autofill-polarity")
        else:
            for a in todo:
                if way := _accepted(got.get(a.fid), a.policy):
                    decided[a.fid] = Polarity(way, "jev", got[a.fid][1])
            fast_asks = [a for a in todo if a.fid not in decided]
            fast = _second_opinion(fast_asks, session, budget)
    else:
        fast = _fast(todo, session, budget, "autofill-polarity")
    for a in fast_asks:
        if way := _accepted(fast.get(a.fid), a.policy):
            decided[a.fid] = Polarity(way, "fast", fast[a.fid][1])
    for a in todo:
        polarity = decided.get(a.fid, UNSURE)
        if polarity.way is not None:
            _remember(_key(a), polarity)
        out[a.fid] = polarity
        logger.info("polarity: field %s %s (by %s)", a.fid, polarity.way or "unsure", polarity.engine or "none")
    return out
