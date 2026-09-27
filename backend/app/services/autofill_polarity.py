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

Only for a Yes/No fact (`Fact.yes_no`). Jev first over code-owned keys; where
it is unsure (under the slot's floor, or `neither`) ONE fast second opinion at
the same floor, on the request's `Budget`; still unsure, the field abstains.
On the `fast` engine, or when the Jev call fails, the fast model decides.
"""

import json
import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.services import jev, llm, model_settings
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, MATCH_FLOOR
from app.services.autofill_map import MIN_CALL_S, SECOND_OPINION_MAX_S, Budget, fast_json

logger = logging.getLogger(__name__)

Way = Literal["same", "opposite"]
SAME, OPPOSITE, NEITHER = "same", "opposite", "neither"
CRITERIA = {
    SAME: "Same: the question asks what the fact says, so a Yes to the fact is a Yes to the question",
    OPPOSITE: "Opposite: the question asks the reverse or a negation of the fact, so a Yes to the fact is a No "
              "to the question",
    NEITHER: "Neither: the question asks something else, or which one it asks cannot be told",
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
    way: Way | None   # None: unsure, or neither — the field is left to the user
    engine: str | None   # "jev" | "fast": which engine decided


UNSURE = Polarity(None, None)


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
    """One fast-model call, capped and on what is left of the budget (leaving
    the pick that follows time to start). Out of time or failed: nothing."""
    timeout = budget.left(SECOND_OPINION_MAX_S, reserve=MIN_CALL_S)
    if not asks or timeout is None:
        return {}
    try:
        return _with_llm(asks, session, trace_name, timeout=timeout)
    except llm.LLMProviderError:
        logger.warning("fast model polarity (%s) failed; its fields are left to the user", trace_name)
        return {}


def _second_opinion(asks: list[Ask], session: Session, budget: Budget) -> dict[str, tuple[str, float]]:
    return _fast(asks, session, budget, "autofill-polarity-second")


def _accepted(answer: tuple[str, float] | None, policy: str) -> str | None:
    if answer is None:
        return None
    key, p = answer
    return key if key in (SAME, OPPOSITE) and p >= MATCH_FLOOR.get(policy, MATCH_FLOOR["exact"]) else None


def decide(asks: list[Ask], session: Session, budget: Budget) -> dict[str, Polarity]:
    """Per field: same, opposite, or UNSURE (under the floor, `neither`, no
    answer, out of time) — and which engine decided."""
    if not asks:
        return {}
    out: dict[str, Polarity] = {}
    fast_asks = asks
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            got = _with_jev(asks, session)
        except llm.LLMProviderError:
            logger.warning("jev polarity failed; the fast model decides these fields")
            fast = _fast(asks, session, budget, "autofill-polarity")
        else:
            for a in asks:
                if way := _accepted(got.get(a.fid), a.policy):
                    out[a.fid] = Polarity(way, "jev")
            fast_asks = [a for a in asks if a.fid not in out]
            fast = _second_opinion(fast_asks, session, budget)
    else:
        fast = _fast(asks, session, budget, "autofill-polarity")
    for a in fast_asks:
        if way := _accepted(fast.get(a.fid), a.policy):
            out[a.fid] = Polarity(way, "fast")
    for a in asks:
        out.setdefault(a.fid, UNSURE)
        logger.info("polarity: field %s %s (by %s)", a.fid, out[a.fid].way or "unsure", out[a.fid].engine or "none")
    return out
