"""The only shapes code above the adapters sees. Provider wire formats never leak past here.

Rules (SYSTEM.md inv-provider-tagged-meta): opaque provider data rides in `ProviderMeta` and is
replayed only to the provider that produced it (`replay.py`). Persisted form is `dump_parts`
JSON, versioned; bump TRANSCRIPT_VERSION and add a loader branch, never edit v1 in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Protocol, Union

TRANSCRIPT_VERSION = 1

Role = Literal["user", "assistant", "tool"]


@dataclass(frozen=True)
class ModelRef:
    provider: str  # "openai" | "anthropic" | "gemini" | "openrouter"
    model: str


@dataclass(frozen=True)
class ProviderMeta:
    provider: str
    model: str
    data: dict[str, Any]


@dataclass
class TextPart:
    text: str


@dataclass
class ImagePart:
    """In-memory only (one-shot OCR calls); never persisted (planning decision 4)."""

    data: bytes
    media_type: str = "image/png"


@dataclass
class ToolCallPart:
    id: str
    name: str
    arguments: dict[str, Any] | None  # None = the model sent arguments that were not JSON
    meta: ProviderMeta | None = None


@dataclass
class ToolResultPart:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ReasoningPart:
    text: str
    meta: ProviderMeta | None = None


ANTHROPIC_THINKING_TYPES = frozenset({"thinking", "redacted_thinking"})


def is_anthropic_thinking_part(part: object) -> bool:
    """True for a Claude thinking / redacted_thinking block. The ONE predicate for "reasoning a retry
    may drop": the `fallback` block is also an opaque anthropic ReasoningPart but must be KEPT (the API
    uses its position to validate the surrounding thinking). Shared with the persisted drop_reasoning."""
    meta = getattr(part, "meta", None)
    return (isinstance(part, ReasoningPart) and meta is not None and meta.provider == "anthropic"
            and meta.data.get("type") in ANTHROPIC_THINKING_TYPES)


Part = Union[TextPart, ImagePart, ToolCallPart, ToolResultPart, ReasoningPart]


@dataclass
class Message:
    role: Role
    parts: list[Part]

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, TextPart))

    @property
    def tool_calls(self) -> list[ToolCallPart]:
        return [p for p in self.parts if isinstance(p, ToolCallPart)]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


@dataclass
class Request:
    model: ModelRef
    messages: list[Message]
    system: str | None = None
    tools: list[ToolSpec] = field(default_factory=list)
    output: Literal["text", "json"] | dict[str, Any] = "text"  # dict = JSON Schema
    max_tokens: int | None = None
    timeout: float | None = None  # per request, no SDK retries (llm._call_model contract)
    effort: str | None = None  # Claude output_config.effort; ignored elsewhere
    cache: bool = False  # ask the adapter to cache the stable prefix (system + tools)


@dataclass
class Usage:
    input: int
    output: int
    cache_read: int = 0
    cache_write: int = 0

    def as_langfuse(self) -> dict[str, int]:
        out = {"input": self.input, "output": self.output}
        if self.cache_read:
            out["cache_read"] = self.cache_read
        if self.cache_write:
            out["cache_write"] = self.cache_write
        return out


@dataclass
class Response:
    message: Message
    usage: Usage | None
    stop_reason: str
    model: str  # the model that actually answered (a Claude fallback can differ)
    reasoning_dropped: bool = False  # planning decision 5

    @property
    def text(self) -> str:
        return self.message.text


@dataclass
class TextDelta:
    text: str


@dataclass
class Finish:
    message: Message
    usage: Usage | None
    stop_reason: str
    model: str
    reasoning_dropped: bool = False  # planning decision 5


StreamEvent = Union[TextDelta, Finish]


class Provider(Protocol):
    name: str

    def ready(self) -> None:
        """Raise LLMProviderError (a user sentence) when this provider cannot be called."""

    def generate(self, req: Request) -> Response: ...

    def stream(self, req: Request) -> Iterator[StreamEvent]: ...

    def list_models(self) -> list[dict[str, str]]:
        """Rows {"id", "label", "provider"} for Settings › Advanced › Available models."""


# --- persisted form -------------------------------------------------------------------------

def _meta_json(meta: ProviderMeta | None) -> dict[str, Any] | None:
    if meta is None:
        return None
    return {"provider": meta.provider, "model": meta.model, "data": meta.data}


def _meta_load(raw: dict[str, Any] | None) -> ProviderMeta | None:
    if not raw:
        return None
    return ProviderMeta(raw["provider"], raw["model"], dict(raw.get("data") or {}))


def dump_parts(parts: list[Part]) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for p in parts:
        if isinstance(p, TextPart):
            out.append({"type": "text", "text": p.text})
        elif isinstance(p, ToolCallPart):
            out.append({"type": "tool_call", "id": p.id, "name": p.name,
                        "arguments": p.arguments, "meta": _meta_json(p.meta)})
        elif isinstance(p, ToolResultPart):
            out.append({"type": "tool_result", "tool_call_id": p.tool_call_id,
                        "content": p.content, "is_error": p.is_error})
        elif isinstance(p, ReasoningPart):
            out.append({"type": "reasoning", "text": p.text, "meta": _meta_json(p.meta)})
        else:
            raise ValueError(f"{type(p).__name__} is not persisted")
    return {"v": TRANSCRIPT_VERSION, "parts": out}


def load_parts(doc: dict[str, Any]) -> list[Part]:
    if doc.get("v") != TRANSCRIPT_VERSION:
        raise ValueError(f"unknown transcript version {doc.get('v')!r}")
    out: list[Part] = []
    for raw in doc.get("parts") or []:
        kind = raw.get("type")
        if kind == "text":
            out.append(TextPart(raw["text"]))
        elif kind == "tool_call":
            out.append(ToolCallPart(raw["id"], raw["name"], raw.get("arguments"),
                                    _meta_load(raw.get("meta"))))
        elif kind == "tool_result":
            out.append(ToolResultPart(raw["tool_call_id"], raw["content"],
                                      bool(raw.get("is_error"))))
        elif kind == "reasoning":
            out.append(ReasoningPart(raw.get("text", ""), _meta_load(raw.get("meta"))))
        # unknown part types from a newer build are skipped, not fatal
    return out
