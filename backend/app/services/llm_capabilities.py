"""Decide what a configured model can actually do, once, at configure time.

Maestro CS does not need one capability from a model; it needs three, and
different surfaces need different ones:

    text   plain completion        cover letters, screening answers
    json   a JSON object back      JD extraction, KB ingest, tailoring, health,
                                   the base-from-KB planner (14 services)
    tools  tool calls + streaming  the chat agent, and nothing else

Hosted OpenAI models clear all three. A 3B model served by Ollama often clears
`text` and `json` and fails `tools` outright. Discovering that halfway through a
tailoring run is the bad outcome, so we probe when the model is SAVED and let
each surface ask whether its own requirement is met.

This is not a new idea in this codebase — `set_models` already refuses a Gemini
chat model because that path cannot stream a tools loop. The probe generalizes
that from a hardcoded provider rule to a measured property of the served model,
which is the only thing that works once the endpoint is arbitrary.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import Setting
from app.services import llm

CAPABILITIES = ("text", "json", "tools")

# Which capability each surface needs, for the error message when it is absent.
SURFACE_REQUIREMENTS = {
    "chat": "tools",
    "tailoring": "json",
    "extraction": "json",
    "cover_letter": "text",
}

_PROBE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "report_ok",
            "description": "Report that the check succeeded.",
            "parameters": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
        },
    }
]


@dataclass
class CapabilityReport:
    model: str
    base_url: str | None = None
    text: bool = False
    json: bool = False
    tools: bool = False
    # capability -> the provider error, so the UI can explain a failure rather
    # than only marking it red.
    errors: dict[str, str] = field(default_factory=dict)
    checked_at: str = ""

    def supports(self, capability: str) -> bool:
        return bool(getattr(self, capability, False))


def _key(model: str) -> str:
    return f"llm.capabilities.{model}"


def _probe_text(model: str) -> None:
    result = llm.call_openai(
        prompt="Reply with the single word: ok",
        model=model,
        response_format="text",
        max_retries=0,
        trace_name="capability-probe-text",
    )
    if not str(result).strip():
        raise RuntimeError("model returned empty text")


def _probe_json(model: str) -> None:
    result = llm.call_openai(
        prompt='Reply with only this JSON object and nothing else: {"ok": true}',
        model=model,
        response_format="json",
        max_retries=1,
        trace_name="capability-probe-json",
    )
    if not isinstance(result, dict):
        raise RuntimeError("model did not return a JSON object")


def _probe_tools(model: str) -> None:
    """Tool calling AND streaming — the chat agent needs both together."""
    # Same client the chat agent uses (it imports `_get_client` too) so the
    # probe exercises the exact transport the capability is needed on.
    stream = llm._get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Call report_ok with ok=true."}],
        tools=_PROBE_TOOL,
        stream=True,
    )
    saw_tool_call = False
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if delta is not None and getattr(delta, "tool_calls", None):
            saw_tool_call = True
            break
    if not saw_tool_call:
        raise RuntimeError("model streamed no tool call")


_PROBES = {"text": _probe_text, "json": _probe_json, "tools": _probe_tools}


def probe(model: str) -> CapabilityReport:
    """Run all three probes. Never raises — a dead endpoint is a report of Nos."""
    report = CapabilityReport(
        model=model,
        base_url=llm.get_base_url(),
        checked_at=datetime.now(UTC).isoformat(),
    )
    for capability, run in _PROBES.items():
        try:
            run(model)
            setattr(report, capability, True)
        except Exception as exc:  # noqa: BLE001 — every failure is a "No", not a crash
            report.errors[capability] = str(exc)[:500]
    return report


def save(session: Session, report: CapabilityReport) -> CapabilityReport:
    payload = json.dumps(asdict(report))
    existing = session.scalar(select(Setting).where(Setting.key == _key(report.model)))
    if existing is None:
        session.add(Setting(key=_key(report.model), value=payload))
    else:
        existing.value = payload
    session.commit()
    return report


def load(session: Session, model: str) -> CapabilityReport | None:
    row = session.scalar(select(Setting).where(Setting.key == _key(model)))
    if row is None or not row.value:
        return None
    try:
        data = json.loads(row.value)
    except json.JSONDecodeError:
        return None
    known = {k: v for k, v in data.items() if k in CapabilityReport.__dataclass_fields__}
    return CapabilityReport(**known)


def probe_and_save(session: Session, model: str) -> CapabilityReport:
    return save(session, probe(model))


class CapabilityMissing(RuntimeError):
    """A surface needs something the configured model was measured not to do."""


def require(session: Session, model: str, capability: str) -> None:
    """Raise a message that names the capability, not a bare "request failed".

    An UNPROBED model is allowed through: never block work because we have not
    measured yet. The probe exists to warn early, not to gate on its own absence.
    """
    report = load(session, model)
    if report is None or report.supports(capability):
        return
    reason = report.errors.get(capability, "the capability probe found it unsupported")
    raise CapabilityMissing(
        f"{model!r} does not support {capability}: {reason}. "
        f"Choose a {capability}-capable model in Settings — the fast, smart and "
        f"chat models are configured separately, so a local model can keep doing "
        f"the rest."
    )
