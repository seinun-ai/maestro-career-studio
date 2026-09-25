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
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services import model_settings
from app.services.llm import LLMProviderError, _log_call

# The fill pass's whole point is speed: a Jev call that takes longer than this
# is slower than the fast model it replaces, so give up and let it answer.
TIMEOUT_S = 2.0
_RETRY_STATUSES = frozenset({429, 529})
_BACKOFF_S = 0.3

NO_JEV_KEY_MESSAGE = "No Jev API key is set. Add one in Settings › AI & models › Form filling."


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probability: float  # of the chosen option
    confidence: float


def choice_question(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def choice_of(answer: object) -> ChoiceAnswer | None:
    """One Choice answer, or None when the shape is not one."""
    if not isinstance(answer, dict) or not isinstance(answer.get("choice"), str):
        return None
    confidence = answer.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    probabilities = answer.get("probabilities")
    p = probabilities.get(answer["choice"]) if isinstance(probabilities, dict) else None
    probability = float(p) if isinstance(p, (int, float)) else confidence
    return ChoiceAnswer(answer["choice"], probability, confidence)


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
            response = httpx.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError("Jev could not be reached.", str(exc)) from exc
        retry = (
            response.status_code in _RETRY_STATUSES
            and attempt == 1
            and deadline - time.monotonic() > _BACKOFF_S
        )
        if not retry:
            break
        time.sleep(_BACKOFF_S)

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
    decide(
        {"ok": {"type": "noul", "instructions": "Is the state the word yes?"}},
        "yes",
        session,
    )
