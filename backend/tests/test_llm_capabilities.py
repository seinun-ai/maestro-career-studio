from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import llm_capabilities


def _tool_call_stream():
    """One chunk carrying a tool call, shaped like the OpenAI streaming delta."""
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(tool_calls=[MagicMock()]))]
    return [chunk]


def _no_tool_stream():
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(tool_calls=None))]
    return [chunk]


def test_probe_reports_all_three_when_model_is_capable(monkeypatch):
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(
        llm_capabilities.llm,
        "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True},
    )
    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.return_value = _tool_call_stream()
        report = llm_capabilities.probe("gpt-4o")

    assert (report.text, report.json, report.tools) == (True, True, True)
    assert report.errors == {}


def test_probe_records_the_reason_a_capability_failed(monkeypatch):
    """A small local model typically clears text+json and fails tools."""
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: "http://localhost:11434/v1")
    monkeypatch.setattr(
        llm_capabilities.llm,
        "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True},
    )
    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.return_value = _no_tool_stream()
        report = llm_capabilities.probe("llama3.2:3b")

    assert (report.text, report.json, report.tools) == (True, True, False)
    assert "tool call" in report.errors["tools"]
    assert report.base_url == "http://localhost:11434/v1"


def test_probe_never_raises_when_the_endpoint_is_dead(monkeypatch):
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: "http://nope:1/v1")

    def boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(llm_capabilities.llm, "call_openai", boom)
    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.side_effect = boom
        report = llm_capabilities.probe("whatever")

    assert (report.text, report.json, report.tools) == (False, False, False)
    assert set(report.errors) == {"text", "json", "tools"}


def test_save_and_load_round_trip(db_session):
    report = llm_capabilities.CapabilityReport(
        model="llama3.2:3b", text=True, json=True, tools=False, errors={"tools": "nope"}
    )
    llm_capabilities.save(db_session, report)

    loaded = llm_capabilities.load(db_session, "llama3.2:3b")
    assert loaded is not None
    assert loaded.supports("json") is True
    assert loaded.supports("tools") is False
    assert loaded.errors["tools"] == "nope"


def test_require_passes_for_unprobed_model(db_session):
    """Never block work because we have not measured yet."""
    llm_capabilities.require(db_session, "never-probed", "tools")


def test_require_names_the_missing_capability(db_session):
    llm_capabilities.save(
        db_session,
        llm_capabilities.CapabilityReport(
            model="llama3.2:3b", text=True, json=True, tools=False,
            errors={"tools": "model streamed no tool call"},
        ),
    )
    with pytest.raises(llm_capabilities.CapabilityMissing) as exc:
        llm_capabilities.require(db_session, "llama3.2:3b", "tools")

    message = str(exc.value)
    assert "tools" in message
    assert "streamed no tool call" in message
    # Points at the way out: the three models are configured separately.
    assert "configured separately" in message


class _RecordingClient:
    """Records the kwargs of each create() call.

    The MagicMock clients above accept any kwargs silently, so they cannot tell
    the probe's call apart from the chat agent's — which is exactly how the
    divergence these tests pin down went unnoticed.
    """

    def __init__(self, stream):
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(_tool_call_stream())


def test_tools_probe_sends_the_same_per_model_kwargs_as_the_chat_agent(monkeypatch):
    """gpt-5.6 400s on function tools unless reasoning_effort is "none".

    The chat agent has always sent it; the probe did not, so the probe recorded
    tools=False for a model whose chat works — and `require` then 422'd chat.
    """
    client = _RecordingClient(_tool_call_stream())
    monkeypatch.setattr(llm_capabilities.llm, "_get_client", lambda: client)

    llm_capabilities._probe_tools("gpt-5.6-luna")

    assert client.calls[0]["reasoning_effort"] == "none"


def test_tools_probe_omits_reasoning_effort_for_models_that_reject_it(monkeypatch):
    client = _RecordingClient(_tool_call_stream())
    monkeypatch.setattr(llm_capabilities.llm, "_get_client", lambda: client)

    llm_capabilities._probe_tools("gpt-4o")

    assert "reasoning_effort" not in client.calls[0]


def _compat_client_recording(constructed: list[dict], stream=None):
    """OpenAI-SDK stand-in that records constructor kwargs. No kwargs-swallowing."""

    class _CompatClient:
        def __init__(self, **kwargs):
            constructed.append(dict(kwargs))
            self.api_key = kwargs["api_key"]
            self.base_url = kwargs["base_url"]
            chunks = stream if stream is not None else _tool_call_stream()
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kw: iter(chunks))
            )

    return _CompatClient


def test_tools_probe_routes_gemini_through_compat_client(monkeypatch):
    """Hosted Gemini chat uses Google's OpenAI-compat URL, not the global client."""
    constructed: list[dict] = []
    monkeypatch.setattr(
        llm_capabilities.llm, "OpenAI", _compat_client_recording(constructed)
    )
    monkeypatch.setattr(llm_capabilities.llm, "get_gemini_key", lambda: "gem-test-key")
    monkeypatch.setattr(
        "app.services.model_settings.using_custom_endpoint", lambda session=None: False
    )
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(
        llm_capabilities.llm,
        "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True},
    )

    def boom_global():
        raise AssertionError("tools probe must not use the global OpenAI client")

    monkeypatch.setattr(llm_capabilities.llm, "_get_client", boom_global)
    llm_capabilities.llm._chat_clients.clear()

    report = llm_capabilities.probe("gemini-3.5-flash-lite")

    assert constructed == [
        {
            "api_key": "gem-test-key",
            "base_url": llm_capabilities.llm.GEMINI_OPENAI_COMPAT_URL,
        }
    ]
    assert report.tools is True
    assert report.errors.get("tools") is None


def test_tools_probe_custom_endpoint_does_not_hijack_gemini_id(monkeypatch):
    """A local Ollama model named gemini-* must stay on the custom endpoint."""
    client = _RecordingClient(_tool_call_stream())
    monkeypatch.setattr(llm_capabilities.llm, "_get_client", lambda: client)
    monkeypatch.setattr(
        "app.services.model_settings.using_custom_endpoint", lambda session=None: True
    )
    monkeypatch.setattr(
        llm_capabilities.llm, "get_base_url", lambda: "http://localhost:11434/v1"
    )
    monkeypatch.setattr(
        llm_capabilities.llm,
        "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True},
    )

    def boom_compat(**kwargs):
        raise AssertionError(f"must not construct Google compat client: {kwargs}")

    monkeypatch.setattr(llm_capabilities.llm, "OpenAI", boom_compat)
    llm_capabilities.llm._chat_clients.clear()

    report = llm_capabilities.probe("gemini-3.5-flash-lite")

    assert client.calls, "custom-endpoint Gemini id must use the global client"
    assert report.tools is True
