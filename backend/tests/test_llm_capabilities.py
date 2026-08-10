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
