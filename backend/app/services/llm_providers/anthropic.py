"""Claude through the official `anthropic` SDK (1.x). Every Claude-specific rule lives here.

- Never send temperature/top_p/top_k or a forced tool_choice: current Claude models 400 on them.
- Thinking is adaptive (the default on Claude 5 models); no `thinking` param, effort only when a
  caller asks.
- Thinking blocks are replayed unchanged (meta.data is the raw block); removing them can 400.
- Refusals: server-side `fallbacks: "default"` on models that accept it; a final refusal is a
  plain sentence. After a mid-output fallback (Anthropic's echo rule, refusals-and-fallback
  docs, checked 2026-10-10): the `fallback` block is KEPT exactly where it appeared (the API
  uses its position to validate the thinking around it; omitting or moving it is rejected);
  thinking, redacted_thinking and client tool_use blocks before the last `fallback` block are
  dropped; text is kept. The fallback block rides as an opaque `anthropic` ReasoningPart.
- SDK blocks are dumped `by_alias=True`: the fallback block's `from_` field is `from` on the wire.

`anthropic` and `app.services.llm` are imported only inside functions (startup cost; the registry
imports this module and `llm` imports the registry).
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Iterator

from app.services.llm_providers.errors import (
    _TIMED_OUT,
    LLMProviderError,
    _no_answer,
    _status_reason,
)
from app.services.llm_providers.types import (
    Finish,
    ImagePart,
    Message,
    ProviderMeta,
    ReasoningPart,
    Request,
    Response,
    TextDelta,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
    is_anthropic_thinking_part,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models documented to take `fallbacks: "default"` on the Claude API (claude-api skill, 2026-10).
# Haiku 5.5 has no server-side fallback. Unknown ids get none rather than a 400.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5", "claude-fable-5-1"})
GENERATE_MAX_TOKENS = 32_000
STREAM_MAX_TOKENS = 64_000
REFUSED = ("Claude declined to answer this request. Try rephrasing it, or pick another model "
           "in Settings › Advanced › Model per job.")


def _user_blocks(msg: Message) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for p in msg.parts:
        if isinstance(p, TextPart) and p.text:
            blocks.append({"type": "text", "text": p.text})
        elif isinstance(p, ImagePart):
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": p.media_type,
                "data": base64.b64encode(p.data).decode("ascii")}})
    return blocks


def _assistant_blocks(msg: Message) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for p in msg.parts:
        if isinstance(p, ReasoningPart) and p.meta and p.meta.provider == "anthropic":
            blocks.append(p.meta.data)
        elif isinstance(p, TextPart) and p.text:
            blocks.append({"type": "text", "text": p.text})
        elif isinstance(p, ToolCallPart):
            blocks.append({"type": "tool_use", "id": p.id, "name": p.name,
                           "input": p.arguments or {}})
    return blocks


def build_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            results = []
            for p in msg.parts:
                if isinstance(p, ToolResultPart):
                    block = {"type": "tool_result", "tool_use_id": p.tool_call_id, "content": p.content}
                    if p.is_error:
                        block["is_error"] = True
                    results.append(block)
            prev = out[-1] if out else None
            if prev and prev["role"] == "user" and prev.get("_tool_results"):
                prev["content"].extend(results)
            else:
                out.append({"role": "user", "content": results, "_tool_results": True})
            continue
        blocks = _user_blocks(msg) if msg.role == "user" else _assistant_blocks(msg)
        if blocks:
            out.append({"role": msg.role, "content": blocks})
    for entry in out:
        entry.pop("_tool_results", None)
    return out


def build_kwargs(req: Request, *, stream: bool) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "model": req.model.model,
        "max_tokens": req.max_tokens or (STREAM_MAX_TOKENS if stream else GENERATE_MAX_TOKENS),
        "messages": build_messages(req.messages),
    }
    if req.system:
        kw["system"] = [{"type": "text", "text": req.system}]
    if req.tools:
        kw["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                       for t in req.tools]
    if req.cache:
        kw["cache_control"] = {"type": "ephemeral"}
    output_config: dict[str, Any] = {}
    if isinstance(req.output, dict):
        output_config["format"] = {"type": "json_schema", "schema": req.output}
    if req.effort:
        output_config["effort"] = req.effort
    if output_config:
        kw["output_config"] = output_config
    if req.model.model in FALLBACK_MODELS:
        kw["fallbacks"] = "default"
        kw["betas"] = [FALLBACK_BETA]
    return kw


def parts_from_message(msg: Any) -> list[Any]:
    # by_alias: the fallback block's `from_` attribute is `from` on the wire (and when replayed).
    blocks = [b.model_dump(mode="json", exclude_none=True, by_alias=True) for b in msg.content]
    last_fallback = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    parts: list[Any] = []
    for i, b in enumerate(blocks):
        kind = b.get("type")
        if i < last_fallback and kind != "text":
            continue
        if kind == "text":
            parts.append(TextPart(b.get("text", "")))
        elif kind in ("thinking", "redacted_thinking", "fallback"):
            # Opaque to us, replayed verbatim and in place by _assistant_blocks.
            parts.append(ReasoningPart(b.get("thinking", ""), ProviderMeta("anthropic", msg.model, b)))
        elif kind == "tool_use":
            parts.append(ToolCallPart(b["id"], b["name"], b.get("input") or {}))
    return parts


def raise_for_refusal(msg: Any) -> None:
    if getattr(msg, "stop_reason", None) == "refusal":
        details = getattr(msg, "stop_details", None)
        raise LLMProviderError(REFUSED, provider_detail=f"Claude refusal: {details!r}")


def _usage(msg: Any) -> Usage | None:
    u = getattr(msg, "usage", None)
    if u is None or not isinstance(getattr(u, "input_tokens", None), int):
        return None
    return Usage(u.input_tokens, u.output_tokens,
                 getattr(u, "cache_read_input_tokens", 0) or 0,
                 getattr(u, "cache_creation_input_tokens", 0) or 0)


def _strip_reasoning(req: Request) -> Request:
    """Drop thinking/redacted_thinking only; the `fallback` block stays (see module docstring)."""
    return replace(req, messages=[
        Message(m.role, [p for p in m.parts if not is_anthropic_thinking_part(p)]) for m in req.messages
    ])


def _signature_retry(exc: Exception, req: Request) -> Request | None:
    """The request to re-send after a 400 about a stale thinking signature, else None.

    Planning decision 5: the checked prefix changed (system prompt or tools). Only worth a retry
    when `_strip_reasoning` actually removes a part: otherwise the re-send is identical and
    `reasoning_dropped` would be a lie (a later task rewrites persisted history on it)."""
    text = str(exc).lower()
    if "signature" not in text and "thinking" not in text:
        return None
    if not any(is_anthropic_thinking_part(p) for m in req.messages for p in m.parts):
        return None
    return _strip_reasoning(req)


_ERROR_TYPE_STATUS = {"overloaded_error": 529, "rate_limit_error": 429}


def _anthropic_reason(exc: Any) -> str:
    """A few words for an SDK status error. A mid-stream `event: error` is raised with the
    stream response's status (200), so below 400 the reason comes from the body's error type."""
    status = exc.status_code
    # Anthropic answers an empty prepaid balance with a 400 invalid_request_error, not a 429.
    if "credit balance is too low" in str(exc).lower():
        return _status_reason(status, "insufficient_quota")
    if status >= 400:
        return _status_reason(status)
    body = getattr(exc, "body", None)
    err = body.get("error") if isinstance(body, dict) else None
    kind = err.get("type") if isinstance(err, dict) else (body.get("type") if isinstance(body, dict) else None)
    mapped = _ERROR_TYPE_STATUS.get(kind) if isinstance(kind, str) else None
    return _status_reason(mapped) if mapped else "the provider had an error"


@contextmanager
def _sdk_errors() -> Iterator[None]:
    """The ONE place an anthropic SDK error becomes a user sentence (calls, streams, model listing).
    The httpx branch is a guard for older SDKs; httpx2 (what 1.13 uses) is the transport that can leak."""
    import anthropic
    import httpx

    transport: tuple[type[Exception], ...] = (httpx.HTTPError,)
    timeouts: tuple[type[Exception], ...] = (httpx.TimeoutException,)
    try:  # anthropic 1.x runs on httpx2
        import httpx2
        transport += (httpx2.HTTPError,)
        timeouts += (httpx2.TimeoutException,)
    except ImportError:
        pass

    try:
        yield
    except anthropic.APIStatusError as exc:
        raise _no_answer(_anthropic_reason(exc), f"Anthropic API request failed: {exc}",
                         provider="Claude") from exc
    except anthropic.APITimeoutError as exc:
        raise _no_answer(_TIMED_OUT, f"Anthropic API request timed out: {exc}", provider="Claude") from exc
    except anthropic.APIConnectionError as exc:
        raise _no_answer("no connection", f"Anthropic API connection failed: {exc}", provider="Claude") from exc
    except transport as exc:
        reason = _TIMED_OUT if isinstance(exc, timeouts) else "no connection"
        raise _no_answer(reason, f"Anthropic API connection failed: {exc}", provider="Claude") from exc


class AnthropicProvider:
    name = "anthropic"

    def ready(self) -> None:
        from app.services import llm
        llm._get_anthropic_client()

    def _client(self, req: Request):
        from app.services import llm
        client = llm._get_anthropic_client()
        if req.timeout is not None:
            client = client.with_options(timeout=req.timeout, max_retries=0)
        return client

    def _call(self, req: Request) -> tuple[Any, bool]:
        """(final message, reasoning_dropped)."""
        import anthropic

        def once(r: Request) -> Any:
            with self._client(r).beta.messages.stream(**build_kwargs(r, stream=False)) as s:
                return s.get_final_message()

        with _sdk_errors():
            try:
                return once(req), False
            except anthropic.BadRequestError as exc:
                retry = _signature_retry(exc, req)
                if retry is None:
                    raise
                return once(retry), True

    def generate(self, req: Request) -> Response:
        msg, dropped = self._call(req)
        raise_for_refusal(msg)
        return Response(Message("assistant", parts_from_message(msg)), _usage(msg),
                        msg.stop_reason or "end_turn", msg.model, reasoning_dropped=dropped)

    def stream(self, req: Request) -> Iterator[Any]:
        """TextDeltas, then one Finish carrying the whole Message (planning decision 1).
        A signature 400 arrives when the stream opens, before any delta, so the retry cannot
        duplicate text; once a delta has gone out a 400 is surfaced, never retried."""
        import anthropic

        with _sdk_errors():
            attempt, dropped = req, False
            while True:
                sent = False
                try:
                    # The with-block closes the SDK stream on error and on early generator close.
                    with self._client(attempt).beta.messages.stream(
                            **build_kwargs(attempt, stream=True)) as s:
                        for event in s:
                            if event.type == "text":
                                sent = True
                                yield TextDelta(event.text)
                        msg = s.get_final_message()
                    break
                except anthropic.BadRequestError as exc:
                    retry = None if (sent or dropped) else _signature_retry(exc, attempt)
                    if retry is None:
                        raise
                    attempt, dropped = retry, True
            raise_for_refusal(msg)
            yield Finish(Message("assistant", parts_from_message(msg)), _usage(msg),
                         msg.stop_reason or "end_turn", msg.model, reasoning_dropped=dropped)

    def list_models(self) -> list[dict[str, str]]:
        from app.services import llm
        rows = []
        with _sdk_errors():
            for m in llm._get_anthropic_client().models.list():
                rows.append({"id": m.id, "label": getattr(m, "display_name", None) or m.id,
                             "provider": "anthropic"})
        return sorted(rows, key=lambda r: r["id"])
