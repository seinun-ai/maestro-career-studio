import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from openai import OpenAI

from app.config import settings
from app.services import tracing
from app.services.llm_providers.errors import (  # noqa: F401 — re-exported; callers use llm.*
    _KEY_REFUSED,
    _TIMED_OUT,
    NO_ANTHROPIC_KEY_MESSAGE,
    NO_GEMINI_KEY_MESSAGE,
    NO_KEY_MESSAGE,
    LLMProviderError,
    _gemini_reason,
    _no_answer,
    _openai_reason,
    _status_reason,
)

logger = logging.getLogger(__name__)


ResponseFormat = Literal["json", "text"]


def _openai_provider() -> str:
    """Who the OpenAI SDK is talking to, as the refused-key sentence names it."""
    return "Your AI server" if get_base_url() else "OpenAI"


# Langfuse usage_details shape: {"input": prompt tokens, "output": completion
# tokens}. None when the provider response has no usable counts (e.g. mocks).
Usage = dict[str, int] | None

_client: OpenAI | None = None
_client_key: tuple[str | None, str | None] | None = None
# OpenRouter clients keyed by (provider, key). Separate from `_client` so an
# OpenRouter call cannot repoint the JSON-services client.
_chat_clients: dict[tuple[str, str], OpenAI] = {}


def get_openai_key() -> str | None:
    from app.services import model_settings
    return model_settings.get_openai_api_key() or settings.openai_api_key or None


def get_base_url() -> str | None:
    """Custom OpenAI-compatible endpoint, or None for api.openai.com."""
    from app.services import model_settings
    return model_settings.get_base_url() or settings.openai_base_url or None


def get_gemini_key() -> str | None:
    from app.services import model_settings
    return model_settings.get_gemini_api_key() or settings.gemini_api_key or None


def get_anthropic_key() -> str | None:
    from app.services import model_settings
    return model_settings.get_api_key("anthropic") or settings.anthropic_api_key or None


def get_openrouter_key() -> str | None:
    from app.services import model_settings
    return model_settings.get_api_key("openrouter") or settings.openrouter_api_key or None


def any_model_key_configured() -> bool:
    """Some provider can be called: any of the four keys, or a custom server (which needs none,
    see `_get_client`). The ONE definition for setup status, KB seeding and the startup log."""
    return bool(get_base_url() or get_openai_key() or get_gemini_key()
                or get_anthropic_key() or get_openrouter_key())


ANTHROPIC_BASE_URL = "https://api.anthropic.com"  # explicit: never ANTHROPIC_BASE_URL from a shell

_anthropic_clients: dict[str, Any] = {}


def _get_anthropic_client():
    """Built with an explicit key AND base URL. A zero-argument client would pick up a user's
    ANTHROPIC_AUTH_TOKEN, `ant auth` profile or ANTHROPIC_BASE_URL from their shell (native
    installs inherit it) and bill or route somewhere the user never chose."""
    import anthropic  # lazy: keeps the SDK out of app startup

    key = get_anthropic_key()
    if not key:
        raise LLMProviderError(NO_ANTHROPIC_KEY_MESSAGE)
    client = _anthropic_clients.get(key)
    if client is None:
        client = anthropic.Anthropic(api_key=key, base_url=ANTHROPIC_BASE_URL)
        _anthropic_clients.clear()
        _anthropic_clients[key] = client
    return client


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"  # code-owned; the key goes nowhere else
# Forced on every OpenRouter request; not a setting (design §2, PRIVACY.md).
OPENROUTER_PRIVACY = {"provider": {"data_collection": "deny", "zdr": True}}
NO_OPENROUTER_KEY_MESSAGE = "No OpenRouter API key is set. Add one in Settings › AI & models."


def _get_openrouter_client() -> OpenAI:
    """No attribution headers (HTTP-Referer, X-Title): the request names nobody."""
    key = get_openrouter_key()
    if not key:
        raise LLMProviderError(NO_OPENROUTER_KEY_MESSAGE)
    cached = _chat_clients.get(("openrouter", key))
    if cached is None:
        cached = OpenAI(api_key=key, base_url=OPENROUTER_BASE_URL)
        _chat_clients[("openrouter", key)] = cached
    return cached


def _get_client() -> OpenAI:
    global _client, _client_key
    current_key = get_openai_key()
    base_url = get_base_url()
    cache_key = (current_key, base_url)
    if _client is None or _client_key != cache_key:
        # No key AND no custom endpoint means we are about to call
        # api.openai.com unauthenticated, which returns an opaque 401 telling a
        # first-run user nothing. Name both places a key can go instead. A custom
        # endpoint is exempt: local servers ignore the key entirely.
        if not current_key and not base_url:
            # The other place a key can go is for whoever runs the server,
            # so it goes to the log and the docs, not the sentence a user reads.
            logger.warning("no model key: add one in the web app, or set "
                           "OPENAI_API_KEY in .env and restart the backend")
            raise LLMProviderError(NO_KEY_MESSAGE)
        # Local servers (Ollama, LM Studio, vLLM) ignore the key entirely, but
        # the SDK refuses to construct without a non-empty string.
        _client = OpenAI(api_key=current_key or "local", base_url=base_url)
        _client_key = cache_key
    return _client


def _usage_details(input_tokens: Any, output_tokens: Any) -> Usage:
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return {"input": input_tokens, "output": output_tokens}
    return None


def _json_mode_supported() -> bool:
    """Whether to send `response_format={"type":"json_object"}`.

    OpenAI supports it; arbitrary OpenAI-compatible servers may reject the
    unknown field outright (a hard 400 rather than a degraded answer), so a
    custom endpoint opts out by default and leans on the prompt, the
    `_extract_json_object` salvage, and the existing retry loop instead.
    Override with the `llm.json_mode` setting once a probe proves the endpoint
    accepts it.
    """
    from app.services import model_settings

    mode = model_settings.get_json_mode()
    if mode in {"on", "off"}:
        return mode == "on"
    return get_base_url() is None


def _extract_json_object(text: str) -> str:
    """Salvage a JSON object from a chatty answer.

    Local models routinely wrap JSON in ``` fences or a sentence of preamble
    even when told not to. A clean object passes through untouched, so this
    costs hosted models nothing.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        without_open = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = without_open.rsplit("```", 1)[0].strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def _call_model(
    prompt: str,
    model: str,
    response_format: ResponseFormat,
    images: list[bytes] | None = None,
    timeout: float | None = None,
    schema: dict[str, Any] | None = None,
) -> tuple[str, Usage]:
    """`timeout`: seconds for this one request, with no SDK retries behind it
    (a caller on a budget, such as the fill's optional passes); None keeps the
    client's own timeout and retries. `schema`: a JSON Schema for the reply, sent only to Claude."""
    from app.services.llm_providers import registry
    from app.services.llm_providers.types import ImagePart, Message, TextPart
    from app.services.llm_providers.types import Request as ProviderRequest

    ref = registry.resolve(model)
    parts = [TextPart(prompt), *(ImagePart(img) for img in images or [])]
    # A JSON Schema goes only to the provider that enforces one (anthropic.py: a dict `output` becomes
    # output_config.format json_schema). The OpenAI-compatible adapter sends response_format json_object only
    # for the literal "json" (openai_compat.build_generate_kwargs, when _json_mode_supported allows: a hosted
    # key, or llm.json_mode "on"), and Gemini's _generation_config likewise reads only "json"; a dict would
    # fall through to plain text. So every other provider gets "json", and the caller validates either way.
    output = schema if schema is not None and ref.provider == "anthropic" else response_format
    response = registry.get(ref.provider).generate(ProviderRequest(
        model=ref, messages=[Message("user", parts)], output=output, timeout=timeout,
    ))
    return response.text, response.usage.as_langfuse() if response.usage else None


def _log_call(prompt: str, model: str, response_text: str, attempt: int) -> None:
    """Record that a call happened. Record WHAT WAS SAID only if asked to.

    This used to write the full prompt and response every time, and because it
    sits outside the `tracing.generation` block it ran whether or not Langfuse
    was configured. The result was a second permanent copy of every resume, job
    description, work-authorization answer and generated screening answer, with
    no rotation, no retention, no owner-only permissions and no way to purge it
    (SEC-08, 2026-08-19 audit).

    The default now keeps what debugging actually needs — which model, which
    attempt, how big, and a hash that proves two calls sent the same prompt
    without keeping either. `settings.llm_log_content` opts back into content,
    announced at startup.

    Files are created 0600 in both modes: even metadata says which models you
    call and how often, and this is a machine with other accounts on it.

    NOT here, on purpose: rotation, retention limits, and a purge control.
    Those are P2. Flipping the default and closing the file mode are what make
    the shipped default honest, and they are small enough to land before the
    open-source publish.
    """
    log_dir = Path(settings.logs_dir) / "llm_calls"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = log_dir / f"{timestamp}_{uuid4().hex}.json"

    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model,
        "attempt": attempt,
        "prompt_chars": len(prompt),
        "response_chars": len(response_text),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "response_sha256": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
    }
    if settings.llm_log_content:
        payload["prompt"] = prompt
        payload["response"] = response_text

    # Open with the mode set rather than chmod-ing after: a write-then-chmod
    # leaves the content world-readable for the window in between.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def call_openai(
    *,
    prompt: str,
    model: str,
    response_format: ResponseFormat = "json",
    max_retries: int = 2,
    trace_name: str = "llm-call",
    images: list[bytes] | None = None,
    timeout: float | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any] | str:
    """`timeout`: per request, no SDK retries (see `_call_model`); pair it with
    `max_retries=0` to bound the whole call. `schema`: a JSON Schema the reply must follow, enforced by Claude
    only (every other provider gets plain JSON mode); the caller validates the reply either way."""
    if response_format not in {"json", "text"}:
        raise ValueError("response_format must be 'json' or 'text'")
    if schema is not None and response_format != "json":
        raise ValueError("schema needs response_format 'json'")

    last_error: JSONDecodeError | None = None
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        with tracing.generation(
            trace_name,
            model=model,
            prompt=prompt,
            metadata={
                "attempt": attempt,
                "response_format": response_format,
                "image_count": len(images) if images else 0,
            },
        ) as record:
            response_text, usage = _call_model(prompt, model, response_format, images, timeout, schema)
            record(response_text, usage)
        _log_call(prompt, model, response_text, attempt)

        if response_format == "text":
            return response_text

        try:
            parsed = json.loads(_extract_json_object(response_text))
        except JSONDecodeError as exc:
            last_error = exc
            continue

        if not isinstance(parsed, dict):
            raise ValueError("Expected OpenAI JSON response to be an object")
        return parsed

    if last_error is not None:
        raise ValueError("OpenAI response was not valid JSON after retries") from last_error
    raise RuntimeError("OpenAI call failed without a captured response")
