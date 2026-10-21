"""OpenAI chat.completions wire format: OpenAI, custom servers (Ollama, LM Studio, vLLM) and
OpenRouter. Every quirk of that wire format, model-id rules included, lives in this file."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Callable, Iterable, Iterator

import httpx
import openai
from urllib.error import HTTPError, URLError
from urllib.request import Request as HttpRequest
from urllib.request import urlopen

from app.services.llm_providers.errors import (
    _TIMED_OUT,
    LLMProviderError,
    _no_answer,
    _openai_reason,
    _status_reason,
    logger,
)
from app.services.llm_providers.types import (
    Finish,
    ImagePart,
    Message,
    ModelRef,
    ProviderMeta,
    ReasoningPart,
    Request,
    Response,
    StreamEvent,
    TextDelta,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
)


NO_ZDR_MESSAGE = "OpenRouter has no zero-retention provider for this model. Pick another model."
# OpenRouter's 404 text when the forced zdr/data_collection preferences leave no endpoint.
# Wording unconfirmed live (Task 14). NOT "no endpoints": OpenRouter's capability 404
# ("No endpoints found that support tool use") must keep the model/capability wording.
_NO_ZDR_RE = re.compile(r"data policy|zero data retention", re.IGNORECASE)

# OpenAI: "Starting with GPT-5.4, Chat Completions does not support tool calling with
# `reasoning_effort` values other than `none`" (migration guide, checked 2026-10-10). GPT-6 too:
# the live check (2026-10-11) got a 400 from gpt-6-luna without it and a pass with it.
_TOOLS_NEED_NO_REASONING = re.compile(r"^gpt-(5\.[4-9]|6([.-]|$))")


def completion_extras(model: str) -> dict[str, Any]:
    """Per-model kwargs for chat.completions.create, for every caller of it.

    GPT-5.4 and later, GPT-6 included, reject function tools on /v1/chat/completions unless
    reasoning_effort is "none" (400 otherwise); older models like gpt-4o reject the parameter
    entirely, so it stays conditional. The id is tested after any vendor prefix, so OpenRouter's
    `openai/gpt-5.x-...` matches.
    The capability probe passes tools too and must send the same kwargs as chat, or it measures
    a call the app never makes and reports a working chat model as tool-incapable.
    """
    if _TOOLS_NEED_NO_REASONING.match(model.rsplit("/", 1)[-1]):
        return {"reasoning_effort": "none"}
    return {}


_OPENROUTER_MAX_PAGES = 20

# Non-chat model id fragments: keep discovery focused on generation.
_OPENAI_SKIP_FRAGMENTS = (
    "embedding", "whisper", "tts", "dall-e", "davinci", "babbage", "moderation",
    "transcribe", "realtime", "audio", "image", "search",
)


def _openai_model_is_chatlike(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(fragment in lowered for fragment in _OPENAI_SKIP_FRAGMENTS)


def _user_content(msg: Message) -> Any:
    images = [p for p in msg.parts if isinstance(p, ImagePart)]
    text = "".join(p.text for p in msg.parts if isinstance(p, TextPart))
    if not images:
        return text
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in images:
        b64 = base64.b64encode(img.data).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{img.media_type};base64,{b64}"}})
    return content


def build_generate_kwargs(req: Request, *, json_mode: bool) -> dict[str, Any]:
    """One-shot call: today's exact request (a single user message, no system)."""
    kwargs: dict[str, Any] = {
        "model": req.model.model,
        "messages": [{"role": "user", "content": _user_content(req.messages[-1])}],
    }
    if req.output == "json" and json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _reasoning_details(msg: Message, provider: str) -> list[Any]:
    if provider != "openrouter":
        return []
    out: list[Any] = []
    for p in msg.parts:
        if (isinstance(p, ReasoningPart) and p.meta is not None and p.meta.provider == "openrouter"):
            out.extend(p.meta.data.get("reasoning_details") or [])
    return out


def build_chat_kwargs(req: Request) -> dict[str, Any]:
    """Streaming chat call: the whole transcript, tools, and the per-model extras."""
    messages: list[dict[str, Any]] = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    for msg in req.messages:
        if msg.role == "user":
            messages.append({"role": "user", "content": _user_content(msg)})
        elif msg.role == "assistant":
            calls = msg.tool_calls
            out: dict[str, Any] = {"role": "assistant", "content": msg.text or None}
            if not calls:
                out["content"] = msg.text
            else:
                out["tool_calls"] = [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": json.dumps(c.arguments or {})}}
                    for c in calls
                ]
            details = _reasoning_details(msg, req.model.provider)
            if details:
                out["reasoning_details"] = details
            messages.append(out)
        else:
            for p in msg.parts:
                if isinstance(p, ToolResultPart):
                    messages.append({"role": "tool", "tool_call_id": p.tool_call_id, "content": p.content})
    kwargs: dict[str, Any] = {"model": req.model.model, "messages": messages, "stream": True}
    if req.tools:
        kwargs["tools"] = [
            {"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in req.tools
        ]
    kwargs.update(completion_extras(req.model.model))
    return kwargs


def _delta_reasoning_details(delta: Any) -> list[Any]:
    raw = getattr(delta, "reasoning_details", None) or (getattr(delta, "model_extra", None) or {}).get(
        "reasoning_details")
    if not isinstance(raw, list):
        return []
    return [d.model_dump() if hasattr(d, "model_dump") else d for d in raw]


def accumulate(chunks: Iterable[Any], ref: ModelRef) -> Iterator[StreamEvent]:
    """Chunks -> TextDeltas, then one Finish. Tool-call deltas join by index; arguments that are
    not a JSON object become None. OpenRouter `reasoning_details` ride in one leading ReasoningPart."""
    text: list[str] = []
    calls: dict[int, dict[str, Any]] = {}
    details: list[Any] = []
    stop_reason, usage, answered_by = "stop", None, ref.model
    for chunk in chunks:
        usage = _usage(chunk) or usage
        if isinstance(getattr(chunk, "model", None), str):
            answered_by = chunk.model
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if isinstance(getattr(choice, "finish_reason", None), str):
            stop_reason = choice.finish_reason
        delta = choice.delta
        if delta is None:
            continue
        if ref.provider == "openrouter":
            details.extend(_delta_reasoning_details(delta))
        if delta.content:
            text.append(delta.content)
            yield TextDelta(delta.content)
        for tc in delta.tool_calls or []:
            key = tc.index
            if not isinstance(key, int):
                # Some servers omit `index`: an id we have seen is that slot, a new
                # id opens the next one, an id-less fragment continues the last.
                key = next((k for k, v in calls.items() if tc.id and v["id"] == tc.id), None)
                if key is None:
                    key = len(calls) if tc.id or not calls else max(calls)
            slot = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
    parts: list[Any] = []
    if details:
        parts.append(ReasoningPart("", ProviderMeta("openrouter", ref.model, {"reasoning_details": details})))
    if text:
        parts.append(TextPart("".join(text)))
    for index in sorted(calls):
        slot = calls[index]
        try:
            args = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            args = None
        parts.append(ToolCallPart(slot["id"] or f"call_{index}", slot["name"],
                                  args if isinstance(args, dict) else None))
    yield Finish(Message("assistant", parts), usage, stop_reason, answered_by)


def _usage(response: Any) -> Usage | None:
    usage = getattr(response, "usage", None)
    i, o = getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
    return Usage(i, o) if isinstance(i, int) and isinstance(o, int) else None


class OpenAICompatProvider:
    def __init__(self, name: str, client: Callable[[], Any], json_mode: Callable[[], bool],
                 label: Callable[[], str], extra_body: dict[str, Any] | None = None):
        self.name = name
        self._client = client
        self._json_mode = json_mode
        self._label = label
        self._extra_body = extra_body

    def ready(self) -> None:
        self._client()  # raises LLMProviderError with the right sentence

    def _map_error(self, exc: openai.OpenAIError) -> LLMProviderError:
        """The ONE place an SDK error becomes a user sentence (generate, stream, list_models).
        Normalizes to LLMProviderError so provider outages mean ONE exception type for every
        caller (app.main maps it to 502); SDK errors must not escape as 500s."""
        if (self.name == "openrouter" and getattr(exc, "status_code", None) == 404
                and _NO_ZDR_RE.search(str(exc))):
            # Every OpenRouter request forces zero retention, so a model with no such
            # provider answers 404 "No endpoints found matching your data policy".
            logger.warning("model provider failed: %s", exc)
            return LLMProviderError(NO_ZDR_MESSAGE, provider_detail=f"OpenRouter request failed: {exc}")
        return _no_answer(_openai_reason(exc), f"OpenAI API request failed: {exc}",
                          provider=self._label())

    def generate(self, req: Request) -> Response:
        kwargs = build_generate_kwargs(req, json_mode=self._json_mode())
        if self._extra_body:
            kwargs["extra_body"] = self._extra_body
        client = self._client()
        if req.timeout is not None:
            client = client.with_options(timeout=req.timeout, max_retries=0)
        try:
            response = client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            raise self._map_error(exc) from exc
        text = response.choices[0].message.content or ""
        answered_by = getattr(response, "model", None)  # a MagicMock under patched-client tests
        return Response(Message("assistant", [TextPart(text)]), _usage(response), "stop",
                        answered_by if isinstance(answered_by, str) else req.model.model)

    def stream(self, req: Request) -> Iterator[StreamEvent]:
        """Streaming chat. No `stream_options`: custom servers reject it, so usage is usually None.
        Errors, at the call and mid-stream, map through the same `_map_error` as `generate`."""
        kwargs = build_chat_kwargs(req)
        if self._extra_body:
            kwargs["extra_body"] = self._extra_body
        client = self._client()
        if req.timeout is not None:
            client = client.with_options(timeout=req.timeout, max_retries=0)
        sdk_stream = None
        try:
            sdk_stream = client.chat.completions.create(**kwargs)
            yield from accumulate(sdk_stream, req.model)
        except openai.OpenAIError as exc:
            raise self._map_error(exc) from exc
        except httpx.HTTPError as exc:
            # Older SDK lines let raw transport errors escape mid-iteration.
            reason = _TIMED_OUT if isinstance(exc, httpx.TimeoutException) else "no connection"
            raise _no_answer(reason, f"OpenAI API request failed: {exc}", provider=self._label()) from exc
        finally:
            close = getattr(sdk_stream, "close", None)
            if callable(close):
                close()

    def list_models(self) -> list[dict[str, str]]:
        """Chat-like models for Settings › Advanced › Available models. OpenRouter lists only zero-retention
        models (`zdr=true`), the ones that can run under the forced privacy preferences."""
        if self.name == "openrouter":
            return self._list_openrouter()
        try:
            page = self._client().models.list()
        except openai.OpenAIError as exc:
            raise self._map_error(exc) from exc
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for item in page.data:
            model_id = getattr(item, "id", None)
            if not isinstance(model_id, str) or not model_id or model_id in seen:
                continue
            if not _openai_model_is_chatlike(model_id):
                continue
            seen.add(model_id)
            out.append({"id": model_id, "label": model_id, "provider": self.name})
        out.sort(key=lambda row: row["id"])
        return out

    def _list_openrouter(self) -> list[dict[str, str]]:
        """Plain GET, not `models.list()`: the response pages via `links.next`, which the SDK
        does not follow. The key only ever goes to OPENROUTER_BASE_URL."""
        from app.services import llm

        key = llm.get_openrouter_key()
        if not key:
            raise LLMProviderError(llm.NO_OPENROUTER_KEY_MESSAGE)
        base = llm.OPENROUTER_BASE_URL
        url: str | None = f"{base}/models?zdr=true"
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for _ in range(_OPENROUTER_MAX_PAGES):
            request = HttpRequest(url, headers={"Authorization": f"Bearer {key}"}, method="GET")
            try:
                with urlopen(request, timeout=60) as response:
                    doc = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise _no_answer(_status_reason(exc.code), f"OpenRouter models.list failed: {exc.code} {body}",
                                 provider="OpenRouter") from exc
            except (URLError, TimeoutError, ValueError) as exc:
                raise _no_answer("no connection", f"OpenRouter models.list failed: {exc}",
                                 provider="OpenRouter") from exc
            for item in doc.get("data") or []:
                model_id = item.get("id") if isinstance(item, dict) else None
                if not isinstance(model_id, str) or not model_id or model_id in seen:
                    continue
                seen.add(model_id)
                out.append({"id": model_id, "label": item.get("name") or model_id,
                            "provider": self.name})
            nxt = (doc.get("links") or {}).get("next")
            if not isinstance(nxt, str) or not nxt.startswith(base + "/"):
                break  # no more pages, or a link off OpenRouter: never send the key there
            url = nxt
        out.sort(key=lambda row: row["id"])
        return out
