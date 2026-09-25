"""Jev (TypeSafe AI's System One model): typed decisions, never generated text.

A call sends a STATE and a map of typed questions and gets back, per question, a
chosen option with calibrated probabilities. It cannot write, extract or look
anything up — code gathers what a question needs into the state and acts on the
answer. Served by TypeSafe directly or by OpenRouter's passthrough; both speak
`POST {base}/v1/systemone`, so the base URL setting is the only difference.

Failures are `LLMProviderError`, the one provider-outage type (§12), so callers
fall back to the fast model exactly as they would on an OpenAI outage.
"""

import json
import logging
import math
import time
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services import model_settings
from app.services.llm import LLMProviderError, _log_call

logger = logging.getLogger(__name__)

# The fill pass's whole point is speed: a Jev call that takes longer than this
# is slower than the fast model it replaces, so give up and let it answer.
TIMEOUT_S = 2.0
_RETRY_STATUSES = frozenset({429, 503, 529})
_MAX_ATTEMPTS = 3
_BACKOFF_S = 0.3  # doubles per retry, and only while the budget still covers it
# A probability distribution sums to 1; allow for the provider's rounding.
_SUM_TOLERANCE = 0.02

# ONE pooled client for the process. A fresh connection per call pays a TLS
# handshake that costs about what Jev's whole answer does, and the fill pass
# makes two calls back to back. httpx.Client is safe to share across the
# threads FastAPI runs sync endpoints on.
_CLIENT = httpx.Client()

NO_JEV_KEY_MESSAGE = "No Jev API key is set. Add one in Settings › AI & models › Form filling."


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probability: float  # of the chosen option
    confidence: float


def choice_question(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def choice_of(answer: object, offered: Collection[str]) -> ChoiceAnswer | None:
    """One Choice answer checked against what was OFFERED, or None.

    Anything short of a well-formed distribution over exactly the offered keys
    is refused: a choice we never offered, missing or extra probability keys, a
    number outside [0, 1], probabilities that do not sum to 1, or a choice that
    is not the most probable. A refused answer places nothing — the caller
    abstains or falls back. (After browser-use/jev-ultrafast's validate_choice.)
    """
    try:
        choice = answer["choice"]
        probabilities = answer["probabilities"]
        confidence = answer["confidence"]
        valid = (
            isinstance(choice, str)
            and choice in offered
            and set(probabilities) == set(offered)
            and all(_unit(n) for n in [*probabilities.values(), confidence])
            and abs(sum(probabilities.values()) - 1) < _SUM_TOLERANCE
            and probabilities[choice] >= max(probabilities.values()) - 1e-6
        )
    except (KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        logger.warning("jev answer refused: not a distribution over the offered options")
        return None
    return ChoiceAnswer(choice, float(probabilities[choice]), float(confidence))


def noul_question(instructions: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": instructions}


def noul_of(answer: object) -> float | None:
    """P(yes) from a Noul answer ({"type": "noul", "noul": p}), or None.

    A missing `type` is tolerated; any other type, or p outside [0, 1] (or a
    bool), is refused and logged like `choice_of`'s refusals."""
    if not isinstance(answer, dict) or answer.get("type", "noul") != "noul":
        logger.warning("jev noul answer refused: not a noul answer")
        return None
    p = answer.get("noul")
    if not _unit(p):
        logger.warning("jev noul answer refused: not a probability")
        return None
    return float(p)


def _unit(n: object) -> bool:
    # `type(...) in`, not isinstance: a bool is an int and never a probability.
    return type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1


def decide(
    questions: dict[str, dict[str, Any]],
    state: Any,
    session: Session | None = None,
) -> dict[str, Any]:
    """POST one System One request; return its `answers` map."""
    key = model_settings.get_jev_api_key(session)
    if not key:
        raise LLMProviderError(NO_JEV_KEY_MESSAGE)
    body = {"model": model_settings.get_jev_model(session), "state": state, "questions": questions}
    url = f"{model_settings.get_jev_base_url(session).rstrip('/')}/v1/systemone"
    deadline = time.monotonic() + TIMEOUT_S

    attempt = 0
    while True:
        attempt += 1
        try:
            response = _CLIENT.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError("Jev could not be reached.", str(exc)) from exc
        backoff = _BACKOFF_S * 2 ** (attempt - 1)
        retry = (
            response.status_code in _RETRY_STATUSES
            and attempt < _MAX_ATTEMPTS
            and deadline - time.monotonic() > backoff
        )
        if not retry:
            break
        time.sleep(backoff)

    _log_call(json.dumps(body, sort_keys=True), body["model"], response.text, attempt)
    detail = response.text[:300]
    if response.status_code == 401:
        raise LLMProviderError(
            "Jev refused your API key. Check it in Settings › AI & models.", detail)
    if response.status_code >= 400:
        raise LLMProviderError(f"Jev couldn't answer (error {response.status_code}).", detail)
    try:
        answers = response.json()["answers"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMProviderError("Jev sent an answer we couldn't read.", detail) from exc
    if not isinstance(answers, dict):
        raise LLMProviderError("Jev sent an answer we couldn't read.", detail)
    return answers


def probe(session: Session | None = None) -> None:
    """One tiny Noul call; raises LLMProviderError when the key or endpoint is wrong."""
    decide({"ok": noul_question("Is the state the word yes?")}, "yes", session)
