from unittest.mock import MagicMock, patch

import pytest

from app.services import llm


def _fake_response(content: str) -> MagicMock:
    return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])


def _patched_client():
    """Patch the accessor, never the `_client` global.

    Patching `_client` only worked while the cache key compared equal to its
    unset sentinel. The moment that key gained a base_url component these tests
    silently rebuilt a real client and called the LIVE OpenAI API. `_get_client`
    is the actual seam and no cache logic can bypass it.
    """
    return patch("app.services.llm._get_client")


def test_call_openai_json_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", tmp_path)

    with _patched_client() as get_client:
        client = get_client.return_value
        client.chat.completions.create.return_value = _fake_response('{"a": 1}')

        result = llm.call_openai(prompt="hi", model="gpt-4o-mini", response_format="json")

    assert result == {"a": 1}
    client.chat.completions.create.assert_called_once()
    assert client.chat.completions.create.call_args.kwargs["response_format"] == {
        "type": "json_object"
    }
    assert len(list((tmp_path / "llm_calls").glob("*.json"))) == 1


def test_call_openai_retries_on_bad_json(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", tmp_path)

    with _patched_client() as get_client:
        client = get_client.return_value
        client.chat.completions.create.side_effect = [
            _fake_response("not json"),
            _fake_response('{"ok": true}'),
        ]

        result = llm.call_openai(
            prompt="hi", model="gpt-4o-mini", response_format="json", max_retries=1
        )

    assert result == {"ok": True}
    assert client.chat.completions.create.call_count == 2
    assert len(list((tmp_path / "llm_calls").glob("*.json"))) == 2


def test_call_openai_text_returns_string(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", tmp_path)

    with _patched_client() as get_client:
        client = get_client.return_value
        client.chat.completions.create.return_value = _fake_response("plain answer")

        result = llm.call_openai(prompt="hi", model="gpt-4o", response_format="text")

    assert result == "plain answer"
    assert "response_format" not in client.chat.completions.create.call_args.kwargs


def test_call_openai_routes_gemini_json(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", tmp_path)
    monkeypatch.setattr(llm.settings, "gemini_api_key", "gemini-test")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                b'{"candidates":[{"content":{"parts":[{"text":"{\\"ok\\":true}"}]}}]}'
            )

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)

    result = llm.call_openai(
        prompt="hi",
        model="gemini-3-flash-preview",
        response_format="json",
    )

    assert result == {"ok": True}
    assert "gemini-3-flash-preview:generateContent" in captured["request"].full_url
    body = captured["request"].data.decode("utf-8")
    assert '"responseMimeType": "application/json"' in body
    assert '"thinkingLevel": "low"' in body
    assert captured["timeout"] == 120


def test_call_openai_routes_gemini_pro_with_high_thinking(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", tmp_path)
    monkeypatch.setattr(llm.settings, "gemini_api_key", "gemini-test")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"answer"}]}}]}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return FakeResponse()

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)

    result = llm.call_openai(
        prompt="hi",
        model="gemini-3.1-pro-preview",
        response_format="text",
    )

    assert result == "answer"
    assert "gemini-3.1-pro-preview:generateContent" in captured["request"].full_url
    body = captured["request"].data.decode("utf-8")
    assert '"responseMimeType"' not in body
    assert '"thinkingLevel": "high"' in body


def test_get_keys_fallback(monkeypatch):
    monkeypatch.setattr(llm.settings, "openai_api_key", "env-openai")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "env-gemini")
    from app.services import model_settings
    monkeypatch.setattr(model_settings, "get_openai_api_key", lambda session=None: None)
    monkeypatch.setattr(model_settings, "get_gemini_api_key", lambda session=None: None)

    assert llm.get_openai_key() == "env-openai"
    assert llm.get_gemini_key() == "env-gemini"

    monkeypatch.setattr(model_settings, "get_openai_api_key", lambda session=None: "db-openai")
    monkeypatch.setattr(model_settings, "get_gemini_api_key", lambda session=None: "db-gemini")

    assert llm.get_openai_key() == "db-openai"
    assert llm.get_gemini_key() == "db-gemini"


def test_extract_json_object_salvages_fenced_and_chatty_output():
    """Local models wrap JSON in fences or preamble even when told not to."""
    assert llm._extract_json_object('{"a": 1}') == '{"a": 1}'
    assert llm._extract_json_object('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert llm._extract_json_object('Sure! Here you go:\n{"a": 1}\nHope that helps.') == '{"a": 1}'


def test_json_mode_off_by_default_for_custom_endpoint(monkeypatch):
    """An arbitrary OpenAI-compatible server may hard-400 on response_format."""
    monkeypatch.setattr(llm.settings, "openai_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(llm, "get_base_url", lambda: "http://localhost:11434/v1")
    monkeypatch.setattr("app.services.model_settings.get_json_mode", lambda *a, **k: "auto")
    assert llm._json_mode_supported() is False

    monkeypatch.setattr("app.services.model_settings.get_json_mode", lambda *a, **k: "on")
    assert llm._json_mode_supported() is True


def test_custom_endpoint_skips_response_format(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", tmp_path)
    monkeypatch.setattr(llm, "_json_mode_supported", lambda: False)

    with _patched_client() as get_client:
        client = get_client.return_value
        client.chat.completions.create.return_value = _fake_response('```json\n{"a": 1}\n```')

        result = llm.call_openai(prompt="hi", model="llama3.2:3b", response_format="json")

    assert result == {"a": 1}
    assert "response_format" not in client.chat.completions.create.call_args.kwargs


def test_missing_key_names_both_ways_to_fix_it(monkeypatch):
    """No key anywhere used to become api_key="local" and an opaque 401 from
    api.openai.com. A first-run user cannot act on that; the error must name the
    two places a key can go."""
    from app.services import model_settings

    monkeypatch.setattr(llm.settings, "openai_api_key", None)
    monkeypatch.setattr(model_settings, "get_openai_api_key", lambda session=None: None)
    monkeypatch.setattr(model_settings, "get_base_url", lambda session=None: None)
    monkeypatch.setattr(llm.settings, "openai_base_url", None)
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_client_key", None)

    with pytest.raises(llm.LLMProviderError) as exc:
        llm._get_client()

    message = str(exc.value)
    assert "Settings" in message
    assert "OPENAI_API_KEY" in message


def test_custom_endpoint_still_works_without_a_key(monkeypatch):
    """Ollama / LM Studio / vLLM ignore the key entirely, so a local endpoint
    must NOT be blocked by the missing-key guard — only api.openai.com is."""
    from app.services import model_settings

    monkeypatch.setattr(llm.settings, "openai_api_key", None)
    monkeypatch.setattr(model_settings, "get_openai_api_key", lambda session=None: None)
    monkeypatch.setattr(
        model_settings, "get_base_url", lambda session=None: "http://localhost:11434/v1"
    )
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_client_key", None)

    client = llm._get_client()

    assert str(client.base_url).startswith("http://localhost:11434")
