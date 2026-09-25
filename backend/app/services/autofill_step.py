"""/step — the next move for a field the generic path could not finish.

Jev picks ONE candidate move id (the page's code generated them from the live
widget) or `give_up`. Clicking an option is a semantic answer and must clear
the slot's match floor through the same `verdict` /pick uses (a flag slot may
take a `closest` click only on a complete view). A move that is not an answer —
open, search, scroll, or a click the page described as opening a group
("Open the group …") — only needs PROGRESS_FLOOR and answers `progress`. A plain
click below its answer floor is TENTATIVE progress at PROGRESS_FLOOR (an
unmarked category, Workday's "Job Board" on the way to "LinkedIn"), except on an
exact slot, where a plain click is an answer or nothing; the loop sends it
`as: "progress"`, so the page never verifies it as the answer. The
fact comes from the SLOT, server-side; the request carries none. Low-stakes
(setting re-checked here, never trusted from the client) is only for a field
with no slot, and states the never-list; its answer click is `assumed` at
ASSUMED_FLOOR (0.4) and its other moves need PROGRESS_FLOOR like any field's.
The fast model is the same-floors fallback.
"""

import json
import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import StepRequest, StepResponse
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA
from app.services.autofill_map import _NEVER_LOW_STAKES, fast_json
from app.services.autofill_pick import JobHint, values_for, verdict

logger = logging.getLogger(__name__)

PROGRESS_FLOOR = 0.5
GIVE_UP = "give_up"
# The page's description of a click that opens a group of options (fill-core
# stepState). Page text only ever follows it, JSON-quoted.
GROUP_CLICK = "Open the group "
CLICK_RULE = ("Click an option if it states the applicant value, or if it looks like a category whose "
              "sub-options will contain it; open a group only if its sub-options will contain it. Never click "
              "an option that neither states the value nor leads to it.")
_GIVE_UP_TEXT = "Stop: no move will select an option that states the value"
ABSTAIN = StepResponse(mid=None, reason="abstained")
_LLM_PROMPT = """{instructions}
State: {state}
Moves (id: what it does): {moves}
Return JSON {{"move": "<move id>", "confidence": <0..1>}}."""


def _is_answer(req: StepRequest, mid: str) -> bool:
    """A click selects an answer — unless the page described it as opening a group."""
    describe = next(c.describe for c in req.candidates if c.mid == mid)
    return mid.startswith("click:") and not describe.startswith(GROUP_CLICK)


def _decide(req: StepRequest, mid: str | None, p: float, policy: str) -> StepResponse:
    if not mid or mid == GIVE_UP:
        return ABSTAIN
    if _is_answer(req, mid):
        picked = verdict(req, mid, p, policy, complete=req.complete)
        if picked.oids:
            return StepResponse(mid=mid, reason=picked.reason)
        # Not sure it is the answer: it may still open the category that holds it.
        if policy != "exact" and p >= PROGRESS_FLOOR:
            return StepResponse(mid=mid, reason="progress")
        return ABSTAIN
    return StepResponse(mid=mid, reason="progress") if p >= PROGRESS_FLOOR else ABSTAIN


def _instructions(req: StepRequest, values: list[str], hint: JobHint | None) -> str:
    field = f"form field {req.fid} ({json.dumps(req.question)})"
    if req.route == "low_stakes":
        src = (f" If an option names where this job was found ({json.dumps(hint.source)}), that is the one."
               if hint and hint.source else "")
        goal = (f"the option an applicant keen on this job would choose.{src} If the field asks about "
                f"{_NEVER_LOW_STAKES}, give up")
    else:
        goal = f"the option that states the applicant value {json.dumps(values[0])}"
    return (f"You are filling {field} on a job application. The goal is to select {goal}. "
            f"The moves tried so far are the state's history. Which next move gets closer to that goal? {CLICK_RULE} "
            f"Give up when no move will. {_PAGE_TEXT_IS_DATA}")


def step(req: StepRequest, facts: dict[str, Fact], session: Session, hint: JobHint | None) -> StepResponse:
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
    criteria = {c.mid: c.describe for c in req.candidates if c.mid != GIVE_UP} | {GIVE_UP: _GIVE_UP_TEXT}
    instructions = _instructions(req, values, hint)
    state = {"job": asdict(hint) if hint else None, "history": req.history}
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            answer = jev.decide({req.fid: jev.choice_question(instructions, criteria)}, state, session)
            got = jev.choice_of(answer.get(req.fid), criteria)
            return _decide(req, got.choice if got else None, got.probability if got else 0.0, policy)
        except llm.LLMProviderError:
            logger.warning("jev step failed; the fast model decides this move")
    raw = fast_json(session, _LLM_PROMPT.format(
        instructions=instructions, state=json.dumps(state), moves=json.dumps(criteria)), "autofill-step")
    raw = raw if isinstance(raw, dict) else {}
    mid = raw.get("move") if isinstance(raw.get("move"), str) and raw.get("move") in criteria else None
    conf = raw.get("confidence")
    return _decide(req, mid, float(conf) if jev._unit(conf) else 0.0, policy)
