from unittest.mock import MagicMock

import httpx
import openai
import pytest

from app.services import llm
from app.services.llm_providers import registry
from app.services.llm_providers.errors import LLMProviderError
from app.services.llm_providers.openai_compat import OpenAICompatProvider
from app.services.llm_providers.types import Message, ModelRef, Request, TextPart

REF = ModelRef("openrouter", "anthropic/claude-opus-5-5")
NO_ZDR = "OpenRouter has no zero-retention provider for this model. Pick another model."


def _req(**kw):
    return Request(model=REF, messages=[Message("user", [TextPart("hi")])], **kw)


def _provider(client):
    return OpenAICompatProvider("openrouter", lambda: client, lambda: True, lambda: "OpenRouter",
                                extra_body=llm.OPENROUTER_PRIVACY)


def _status_error(status, message):
    request = httpx.Request("POST", llm.OPENROUTER_BASE_URL + "/chat/completions")
    response = httpx.Response(status, request=request, json={"error": {"message": message}})
    return openai.APIStatusError(message, response=response, body={"message": message})


def test_privacy_preferences_are_forced_on_every_request():
    assert llm.OPENROUTER_PRIVACY == {"provider": {"data_collection": "deny", "zdr": True}}
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = "ok"
    _provider(client).generate(_req())
    assert client.chat.completions.create.call_args.kwargs["extra_body"] == {
        "provider": {"data_collection": "deny", "zdr": True}}


def test_privacy_preferences_also_ride_the_timeout_client():
    client = MagicMock()
    timed = client.with_options.return_value
    timed.chat.completions.create.return_value.choices[0].message.content = "ok"
    _provider(client).generate(_req(timeout=3.0))
    assert timed.chat.completions.create.call_args.kwargs["extra_body"] == llm.OPENROUTER_PRIVACY


def test_registered_openrouter_adapter_carries_the_privacy_body():
    registry._adapters.pop("openrouter", None)
    adapter = registry.get("openrouter")
    assert adapter.name == "openrouter" and adapter._extra_body == llm.OPENROUTER_PRIVACY
    assert adapter._label() == "OpenRouter" and adapter._json_mode() is True


def test_client_base_url_is_code_owned_and_has_no_attribution_headers(monkeypatch):
    monkeypatch.setattr(llm, "get_openrouter_key", lambda: "sk-or-test")
    llm._chat_clients.pop(("openrouter", "sk-or-test"), None)
    client = llm._get_openrouter_client()
    assert str(client.base_url).rstrip("/") == llm.OPENROUTER_BASE_URL
    assert llm.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert "HTTP-Referer" not in client.default_headers and "X-Title" not in client.default_headers
    assert llm._get_openrouter_client() is client  # cached per key


def test_ready_without_a_key_raises_the_openrouter_sentence(monkeypatch):
    monkeypatch.setattr(llm, "get_openrouter_key", lambda: None)
    registry._adapters.pop("openrouter", None)
    with pytest.raises(LLMProviderError) as ei:
        registry.get("openrouter").ready()
    assert str(ei.value) == "No OpenRouter API key is set. Add one in Settings › Basics."


@pytest.mark.parametrize("message", [
    "No endpoints found matching your data policy (Zero data retention).",
    "No allowed providers are available for the selected model under your zero data retention setting.",
])
def test_openrouter_404_without_a_zdr_endpoint_gets_its_own_sentence(message):
    client = MagicMock()
    client.chat.completions.create.side_effect = _status_error(404, message)
    with pytest.raises(LLMProviderError) as ei:
        _provider(client).generate(_req())
    assert str(ei.value) == NO_ZDR
    assert message in ei.value.provider_detail


def test_other_openrouter_404_keeps_the_model_not_found_wording():
    client = MagicMock()
    client.chat.completions.create.side_effect = _status_error(404, "Model does not exist")
    with pytest.raises(LLMProviderError) as ei:
        _provider(client).generate(_req())
    assert "that model wasn't found" in str(ei.value)
    assert str(ei.value) != NO_ZDR


def test_openrouter_capability_404_keeps_the_model_wording_not_the_zdr_sentence():
    client = MagicMock()
    client.chat.completions.create.side_effect = _status_error(404, "No endpoints found that support tool use")
    with pytest.raises(LLMProviderError) as ei:
        _provider(client).generate(_req())
    assert str(ei.value) != NO_ZDR
    assert "that model wasn't found" in str(ei.value)


def test_the_zdr_branch_is_openrouter_only():
    client = MagicMock()
    client.chat.completions.create.side_effect = _status_error(404, "No endpoints found matching your data policy")
    plain = OpenAICompatProvider("openai", lambda: client, lambda: True, lambda: "OpenAI")
    with pytest.raises(LLMProviderError) as ei:
        plain.generate(_req())
    assert str(ei.value) != NO_ZDR


def test_map_error_is_the_single_place_for_error_mapping():
    err = _provider(MagicMock())._map_error(_status_error(404, "No endpoints found matching your data policy"))
    assert isinstance(err, LLMProviderError) and str(err) == NO_ZDR
