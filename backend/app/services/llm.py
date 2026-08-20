import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import openai
from openai import OpenAI

from app.config import settings
from app.services import tracing


ResponseFormat = Literal["json", "text"]


class LLMProviderError(RuntimeError):
    """The upstream model provider failed us — outage, quota, auth, missing key.

    Subclasses RuntimeError so the routers that already map RuntimeError → 502
    by hand (career_kb) keep their behavior, while `app.main` can map THIS type
    globally without also swallowing the render/compile RuntimeErrors raised by
    pdf_render and typst_compiler, which are not gateway failures.
    """


# Langfuse usage_details shape: {"input": prompt tokens, "output": completion
# tokens}. None when the provider response has no usable counts (e.g. mocks).
Usage = dict[str, int] | None

# Google's OpenAI-compatible chat completions URL. Code-owned constant — never
# a user-set base_url (that value decides where the OpenAI key is sent).
GEMINI_OPENAI_COMPAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_client: OpenAI | None = None
_client_key: tuple[str | None, str | None] | None = None
# Chat-scoped clients keyed by (provider, key). Separate from `_client` so a
# Gemini chat turn cannot repoint the JSON-services client.
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


def completion_extras(model: str) -> dict[str, Any]:
    """Per-model kwargs for chat.completions.create, for every caller of it.

    The GPT-5.6 family rejects function tools on /v1/chat/completions unless
    reasoning_effort is "none" (400 otherwise); older models like gpt-4o reject
    the reasoning_effort parameter entirely, so it must stay conditional.

    This lives here, next to the client, because the chat agent is not the only
    caller that passes tools: the capability probe does too, and when it carried
    its own copy of the rule (it carried none) it measured a call the app never
    makes and reported a working chat model as tool-incapable.
    """
    if model.startswith("gpt-5.6"):
        return {"reasoning_effort": "none"}
    return {}


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
            raise LLMProviderError(
                "No OpenAI API key configured. Add one under Settings → Models "
                "in the web app, or set OPENAI_API_KEY in .env and restart the "
                "backend. To use a local model instead, set an OpenAI-compatible "
                "endpoint under Settings → Models."
            )
        # Local servers (Ollama, LM Studio, vLLM) ignore the key entirely, but
        # the SDK refuses to construct without a non-empty string.
        _client = OpenAI(api_key=current_key or "local", base_url=base_url)
        _client_key = cache_key
    return _client


def get_chat_client(model: str) -> OpenAI:
    """OpenAI-SDK client for the chat/tools surface.

    Custom endpoints win first so a locally served `gemini-*` id is not
    hijacked to Google. Hosted Gemini ids go to Google's OpenAI-compat URL
    with the Gemini key. Everything else shares `_get_client()`. Never
    mutates the global `_client` — that client is shared by every JSON service.
    """
    from app.services import model_settings

    if model_settings.using_custom_endpoint():
        return _get_client()
    if _is_gemini_model(model):
        gemini_key = get_gemini_key()
        if not gemini_key:
            raise LLMProviderError("GEMINI_API_KEY is required for Gemini models")
        cache_key = ("gemini", gemini_key)
        cached = _chat_clients.get(cache_key)
        if cached is None:
            cached = OpenAI(api_key=gemini_key, base_url=GEMINI_OPENAI_COMPAT_URL)
            _chat_clients[cache_key] = cached
        return cached
    return _get_client()


def _message_content(response: Any) -> str:
    return response.choices[0].message.content or ""


def _usage_details(input_tokens: Any, output_tokens: Any) -> Usage:
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return {"input": input_tokens, "output": output_tokens}
    return None


def _openai_usage(response: Any) -> Usage:
    usage = getattr(response, "usage", None)
    return _usage_details(
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


def _gemini_usage(response: dict[str, Any]) -> Usage:
    meta = response.get("usageMetadata") or {}
    return _usage_details(meta.get("promptTokenCount"), meta.get("candidatesTokenCount"))


def _gemini_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts)


def _gemini_model_name(model: str) -> str:
    return model.removeprefix("models/")


def _is_gemini_model(model: str) -> bool:
    return _gemini_model_name(model).startswith("gemini-")


def _gemini_thinking_level(model: str) -> str | None:
    normalized = _gemini_model_name(model)
    if not normalized.startswith("gemini-3"):
        return None
    if "pro" in normalized:
        return "high"
    return "low"


def _gemini_generation_config(model: str, response_format: ResponseFormat) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if response_format == "json":
        config["responseMimeType"] = "application/json"

    thinking_level = _gemini_thinking_level(model)
    if thinking_level:
        config["thinkingConfig"] = {"thinkingLevel": thinking_level}

    return config


def _call_gemini(
    prompt: str,
    model: str,
    response_format: ResponseFormat,
    images: list[bytes] | None = None,
) -> tuple[str, Usage]:
    gemini_key = get_gemini_key()
    if not gemini_key:
        raise LLMProviderError("GEMINI_API_KEY is required for Gemini models")

    parts: list[dict[str, Any]] = [{"text": prompt}]
    for image in images or []:
        parts.append(
            {
                "inlineData": {
                    "mimeType": "image/png",
                    "data": base64.b64encode(image).decode("ascii"),
                }
            }
        )
    payload: dict[str, Any] = {
        "contents": [{"parts": parts}],
    }
    generation_config = _gemini_generation_config(model, response_format)
    if generation_config:
        payload["generationConfig"] = generation_config

    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{_gemini_model_name(model)}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": gemini_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMProviderError(f"Gemini API request failed: {exc.code} {body}") from exc

    return _gemini_text(data), _gemini_usage(data)


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
) -> tuple[str, Usage]:
    if _is_gemini_model(model):
        return _call_gemini(prompt, model, response_format, images)

    content: Any = prompt
    if images:
        content = [{"type": "text", "text": prompt}]
        for image in images:
            b64 = base64.b64encode(image).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            )
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }
    if response_format == "json" and _json_mode_supported():
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = _get_client().chat.completions.create(**kwargs)
    except openai.OpenAIError as exc:
        # Normalize to LLMProviderError so provider outages mean ONE exception
        # type for every caller (app.main maps it to 502). The Gemini path raises
        # the same type; without this, OpenAI SDK errors escaped as unhandled
        # 500s — an exhausted credit balance reached the UI as the detail-free
        # "Request failed: 500", with the real 429 visible only in a traceback.
        raise LLMProviderError(f"OpenAI API request failed: {exc}") from exc
    return _message_content(response), _openai_usage(response)


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
) -> dict[str, Any] | str:
    if response_format not in {"json", "text"}:
        raise ValueError("response_format must be 'json' or 'text'")

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
            response_text, usage = _call_model(prompt, model, response_format, images)
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


# Non-chat OpenAI model id fragments — keep discovery focused on generation.
_OPENAI_SKIP_FRAGMENTS = (
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "davinci",
    "babbage",
    "moderation",
    "transcribe",
    "realtime",
    "audio",
    "image",
    "search",
)


def _openai_model_is_chatlike(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(fragment in lowered for fragment in _OPENAI_SKIP_FRAGMENTS)


def list_openai_models() -> list[dict[str, str]]:
    """Models visible to the configured OpenAI-compatible client.

    Uses the same key + base_url as inference. Filtered to chat-like ids; the
    UI still requires an explicit + before anything enters the usable catalog.
    """
    try:
        page = _get_client().models.list()
    except openai.OpenAIError as exc:
        raise LLMProviderError(f"OpenAI models.list failed: {exc}") from exc

    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in page.data:
        model_id = getattr(item, "id", None)
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            continue
        if not _openai_model_is_chatlike(model_id):
            continue
        seen.add(model_id)
        out.append({"id": model_id, "label": model_id, "provider": "openai"})
    out.sort(key=lambda row: row["id"])
    return out


def list_gemini_models() -> list[dict[str, str]]:
    """Gemini models that support generateContent for the configured Gemini key."""
    gemini_key = get_gemini_key()
    if not gemini_key:
        raise LLMProviderError(
            "No Gemini API key configured. Add one under Settings → Models."
        )

    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": gemini_key},
        method="GET",
    )
    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMProviderError(f"Gemini models.list failed: {exc.code} {body}") from exc

    out: list[dict[str, str]] = []
    for item in data.get("models") or []:
        name = item.get("name") or ""
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        model_id = _gemini_model_name(name)
        if not model_id.startswith("gemini-"):
            continue
        display = item.get("displayName") or model_id
        out.append({"id": model_id, "label": display, "provider": "gemini"})
    out.sort(key=lambda row: row["id"])
    return out
