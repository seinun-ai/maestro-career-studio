"""Image (vision) plumbing in the LLM client: both providers accept page images."""

import base64
import io
import json

from app.services import llm as llm_module


def test_call_model_openai_builds_multimodal_content(monkeypatch):
    captured = {}

    class _FakeClient:
        class chat:  # noqa: N801 — mimic SDK shape
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)

                    class _Msg:
                        content = "transcript"

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]
                        usage = None

                    return _Resp()

    monkeypatch.setattr(llm_module, "_get_client", lambda: _FakeClient)
    text, _ = llm_module._call_model("read this", "gpt-4o", "text", images=[b"png-bytes"])
    assert text == "transcript"

    content = captured["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "read this"}
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == b"png-bytes"


def test_call_model_openai_without_images_keeps_plain_prompt(monkeypatch):
    captured = {}

    class _FakeClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)

                    class _Msg:
                        content = "ok"

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]
                        usage = None

                    return _Resp()

    monkeypatch.setattr(llm_module, "_get_client", lambda: _FakeClient)
    llm_module._call_model("hi", "gpt-4o", "text")
    assert captured["messages"][0]["content"] == "hi"


def test_call_gemini_includes_inline_image_data(monkeypatch):
    monkeypatch.setattr(llm_module, "get_gemini_key", lambda: "test-key")
    seen = {}

    def fake_urlopen(request, timeout=0):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        body = json.dumps(
            {"candidates": [{"content": {"parts": [{"text": "transcript"}]}}]}
        ).encode("utf-8")
        return io.BytesIO(body)

    monkeypatch.setattr(llm_module, "urlopen", fake_urlopen)
    text, _ = llm_module._call_gemini(
        "read this", "gemini-3-flash-preview", "text", images=[b"png-bytes"]
    )
    assert text == "transcript"

    parts = seen["payload"]["contents"][0]["parts"]
    assert parts[0] == {"text": "read this"}
    inline = parts[1]["inlineData"]
    assert inline["mimeType"] == "image/png"
    assert base64.b64decode(inline["data"]) == b"png-bytes"
