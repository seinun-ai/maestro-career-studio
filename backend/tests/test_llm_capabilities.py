from unittest.mock import patch

import pytest

from app.services import llm, llm_capabilities
from app.services.llm_providers import errors


def _capable_fake(monkeypatch, scripts):
    from tests.fake_provider import FakeProvider, install

    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(
        llm_capabilities.llm,
        "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True},
    )
    return install(monkeypatch, FakeProvider(scripts))


def test_probe_reports_all_three_when_model_is_capable(monkeypatch):
    from app.services.llm_providers.types import ToolCallPart

    _capable_fake(monkeypatch, [[[ToolCallPart("c1", "report_ok", {"ok": True})]]])

    report = llm_capabilities.probe("fake-model")

    assert (report.text, report.json, report.tools) == (True, True, True)
    assert report.errors == {}


def test_probe_records_the_reason_a_capability_failed(monkeypatch):
    """A small local model typically clears text+json and fails tools."""
    _capable_fake(monkeypatch, [["I will not call tools."]])
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: "http://localhost:11434/v1")

    report = llm_capabilities.probe("fake-model")

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


def test_require_names_the_missing_capability(db_session, caplog):
    caplog.set_level("INFO", logger="app.services.llm_capabilities")
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
    assert message == (
        "The model llama3.2:3b can't use tools. Pick a different model in Settings › "
        "Advanced › Model per job. The Fast, Smart and Assistant models are set separately.")
    # The probe's reason is for a developer: the log keeps it.
    assert "model streamed no tool call" in caplog.text


def _fail_with(monkeypatch, message: str):
    def boom(**kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(llm_capabilities.llm, "call_openai", boom)
    return boom


def test_a_bad_key_is_not_evidence_about_the_model(monkeypatch):
    """A 401 measures the KEY. Recording it as "the model cannot" is a lie.

    A key pasted wrong into a fresh install made the probe store
    text/json/tools all false for a model that does all three, the UI announced
    "gpt-5.6-luna cannot do: text, json, tools", and the stored row outlived the
    bad key — so the model stayed "broken" after the key was fixed.
    """
    boom = _fail_with(
        monkeypatch,
        "OpenAI API request failed: Error code: 401 - Incorrect API key provided",
    )
    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.side_effect = boom
        report = llm_capabilities.probe("gpt-5.6-luna")

    assert report.reachable is False


def test_an_unreachable_probe_is_never_persisted(db_session, monkeypatch):
    boom = _fail_with(monkeypatch, "Error code: 401 - Incorrect API key provided")
    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.side_effect = boom
        llm_capabilities.probe_and_save(db_session, "gpt-5.6-luna")

    assert llm_capabilities.load(db_session, "gpt-5.6-luna") is None


def test_an_unreachable_probe_does_not_clobber_an_earlier_good_record(
    db_session, monkeypatch
):
    good = llm_capabilities.CapabilityReport(
        model="gpt-5.6-luna", text=True, json=True, tools=True
    )
    llm_capabilities.save(db_session, good)

    boom = _fail_with(monkeypatch, "Connection refused")
    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.side_effect = boom
        llm_capabilities.probe_and_save(db_session, "gpt-5.6-luna")

    kept = llm_capabilities.load(db_session, "gpt-5.6-luna")
    assert (kept.text, kept.json, kept.tools) == (True, True, True)


def test_a_real_capability_refusal_is_still_recorded(db_session, monkeypatch):
    # The guard must not swallow genuine Nos: a model that answers but cannot
    # stream a tool call is exactly what this probe exists to catch.
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(llm_capabilities.llm, "call_openai", lambda **kw: "ok")

    def no_tool_call(**kwargs):
        raise RuntimeError("model streamed no tool call")

    with patch("app.services.llm._get_client") as get_client:
        get_client.return_value.chat.completions.create.side_effect = no_tool_call
        report = llm_capabilities.probe_and_save(db_session, "some-local-model")

    assert report.reachable is True
    stored = llm_capabilities.load(db_session, "some-local-model")
    assert stored is not None and stored.tools is False


def test_anthropic_error_vocabulary_is_unreachable_not_a_capability_no():
    from app.services.llm_providers.errors import LLMProviderError
    for sign in ("authentication_error", "permission_error", "rate_limit_error",
                 "overloaded_error", "Error code: 529", "No Claude API key is set."):
        exc = LLMProviderError("The AI model didn't answer.", provider_detail=sign)
        assert llm_capabilities._never_reached_the_model(exc), sign


# --- the tools probe goes through the registry (Task 7) --------------------------------------

def test_tools_probe_passes_when_the_adapter_streams_a_tool_call(monkeypatch):
    from app.services.llm_providers.types import ToolCallPart
    from tests.fake_provider import FakeProvider, install

    fake = install(monkeypatch, FakeProvider([[[ToolCallPart("c1", "report_ok", {"ok": True})]]]))

    llm_capabilities._probe_tools("fake-model")

    sent = fake.requests[0]
    assert [t.name for t in sent.tools] == ["report_ok"]
    assert sent.model.provider == "fake"


def test_tools_probe_fails_on_text_only(monkeypatch):
    from tests.fake_provider import FakeProvider, install

    install(monkeypatch, FakeProvider([["I cannot call tools."]]))

    with pytest.raises(RuntimeError, match="streamed no tool call"):
        llm_capabilities._probe_tools("fake-model")


def test_probe_reports_tools_for_an_anthropic_tagged_model(monkeypatch):
    from app.services.llm_providers.types import ToolCallPart
    from tests.fake_provider import FakeProvider, install

    install(monkeypatch, FakeProvider([[[ToolCallPart("c1", "report_ok", {"ok": True})]]]))
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(
        llm_capabilities.llm, "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True})

    report = llm_capabilities.probe("fake-model")

    assert report.tools is True


def test_tools_probe_makes_the_chat_call_shape(monkeypatch):
    """Chat sends system + tools + cache through `provider.ready()` then `stream`; the probe's
    stream call carries the same switches (SYSTEM.md §12: a probe issues the SAME call)."""
    from app.services.llm_providers.types import ToolCallPart
    from tests.fake_provider import FakeProvider, install

    order: list[str] = []
    fake = FakeProvider([[[ToolCallPart("c1", "report_ok", {"ok": True})]]])
    real_ready, real_stream = fake.ready, fake.stream
    fake.ready = lambda: order.append("ready") or real_ready()
    fake.stream = lambda req: order.append("stream") or real_stream(req)
    install(monkeypatch, fake)

    llm_capabilities._probe_tools("fake-model")

    assert order == ["ready", "stream"]
    assert fake.requests[0].cache is True


def test_a_provider_that_is_not_ready_is_unreachable_not_a_no(db_session, monkeypatch):
    from app.services.llm_providers.errors import LLMProviderError
    from tests.fake_provider import FakeProvider, install

    fake = FakeProvider([])

    def not_ready():
        raise LLMProviderError("No Gemini API key is set.", provider_detail="No Claude API key is set.")

    fake.ready = not_ready
    install(monkeypatch, fake)
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)
    monkeypatch.setattr(
        llm_capabilities.llm, "call_openai",
        lambda **kw: "ok" if kw["response_format"] == "text" else {"ok": True})

    report = llm_capabilities.probe_and_save(db_session, "fake-model")

    assert report.reachable is False
    assert llm_capabilities.load(db_session, "fake-model") is None


def test_no_adapter_error_is_special_cased_as_unreachable():
    """The Task 7 NotImplementedError exemption is gone: every adapter streams now."""
    assert not llm_capabilities._never_reached_the_model(NotImplementedError())


@pytest.mark.parametrize("message", [
    errors.NO_KEY_MESSAGE,
    errors.NO_GEMINI_KEY_MESSAGE,
    errors.NO_ANTHROPIC_KEY_MESSAGE,
    llm.NO_OPENROUTER_KEY_MESSAGE,
])
def test_every_no_key_sentence_is_unreachable_and_stores_nothing(db_session, monkeypatch, message):
    from app.services.llm_providers.errors import LLMProviderError
    from tests.fake_provider import FakeProvider, install

    fake = FakeProvider([])

    def not_ready():
        raise LLMProviderError("shown to user", provider_detail=message)

    fake.ready = not_ready
    install(monkeypatch, fake)
    monkeypatch.setattr(llm_capabilities.llm, "get_base_url", lambda: None)

    report = llm_capabilities.probe_and_save(db_session, "fake-model")

    assert report.reachable is False
    assert llm_capabilities.load(db_session, "fake-model") is None
