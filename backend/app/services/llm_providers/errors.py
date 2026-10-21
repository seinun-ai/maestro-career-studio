"""The LLM error vocabulary: one exception type and the user sentences for provider failures.

Imported by `app.services.llm` (which re-exports every name here), so this module must never
import `app.services.llm`. The logger keeps the old name so log assertions keep matching.
"""

import logging

import openai

logger = logging.getLogger("app.services.llm")


class LLMProviderError(RuntimeError):
    """The upstream model provider failed us — outage, quota, auth, missing key.

    Subclasses RuntimeError so the routers that already map RuntimeError → 502
    by hand (career_kb) keep their behavior, while `app.main` can map THIS type
    globally without also swallowing the render/compile RuntimeErrors raised by
    pdf_render and typst_compiler, which are not gateway failures.

    `str()` is a sentence for the user (the 502 detail, the Assistant's error
    event); `provider_detail` keeps what the provider actually said, for the
    log and for `llm_capabilities`' reachability check, which reads it.
    """

    def __init__(self, message: str, provider_detail: str | None = None) -> None:
        super().__init__(message)
        self.provider_detail = provider_detail or message


NO_KEY_MESSAGE = (
    "No API key is set. Add one in Settings › Basics. To use a model on your computer "
    "instead, add its address in Settings › Advanced › Custom AI server."
)
NO_GEMINI_KEY_MESSAGE = "No Gemini API key is set. Add one in Settings › Basics."
NO_ANTHROPIC_KEY_MESSAGE = "No Claude API key is set. Add one in Settings › Basics."


_KEY_REFUSED = "your key was refused"
# One wording for a request that ran out of time, whichever provider it was.
_TIMED_OUT = "it timed out"


def _no_answer(reason: str, provider_detail: str, provider: str = "OpenAI") -> LLMProviderError:
    """The one sentence for a provider that failed a request. A refused key is not
    worth retrying, so its sentence names who refused it and the fix, nothing else."""
    logger.warning("model provider failed: %s", provider_detail)
    if reason == _KEY_REFUSED:
        return LLMProviderError(
            f"{provider} refused your API key. Check it in Settings › Basics.",
            provider_detail=provider_detail,
        )
    return LLMProviderError(
        f"The AI model didn't answer ({reason}). Try again, or check your key in "
        "Settings › Basics.",
        provider_detail=provider_detail,
    )


def _gemini_reason(status: int, body: str) -> str:
    """Gemini refuses a bad key with a 400 whose body says API_KEY_INVALID."""
    if "API_KEY_INVALID" in body:
        return _KEY_REFUSED
    return _status_reason(status)


# A provider's error code or HTTP status in words, for the sentence a user
# reads. The raw code stays in `provider_detail` (the log and the capability
# probe read it); a code in the sentence ("insufficient_quota") is developer text
# and the web app hides the whole message for it (`isPlainSentence`).
_CODE_WORDS = {
    "invalid_api_key": _KEY_REFUSED,
    "insufficient_quota": "your account is out of credit",
    "model_not_found": "that model wasn't found",
    "rate_limit_exceeded": "too many requests",
}
_STATUS_WORDS = {
    401: _KEY_REFUSED,
    404: "that model wasn't found",
    429: "too many requests",
    529: "the provider is overloaded",
}


def _status_reason(status: int, code: object = None) -> str:
    """The code's words, else the status's, else "error {status}"."""
    if isinstance(code, str) and code in _CODE_WORDS:
        return _CODE_WORDS[code]
    return _STATUS_WORDS.get(status, f"error {status}")


def _openai_reason(exc: Exception) -> str:
    """A few words for what went wrong, never the provider's body or code."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return _status_reason(status, getattr(exc, "code", None))
    if isinstance(exc, openai.APITimeoutError):
        return _TIMED_OUT
    if isinstance(exc, openai.APIConnectionError):
        return "no connection"
    return "unknown error"
