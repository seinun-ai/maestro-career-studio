import base64
import io
from http.client import IncompleteRead
import json
import re
from urllib.error import HTTPError, URLError

import pytest

from app.services.llm_providers import gemini
from app.services.llm_providers.errors import LLMProviderError
from app.services.llm_providers.types import (
    Finish,
    ImagePart,
    Message,
    ModelRef,
    ProviderMeta,
    Request,
    TextDelta,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    ToolSpec,
)


def _req(model="gemini-2.5-flash", **kw):
    base = dict(model=ModelRef("gemini", model), messages=[Message("user", [TextPart("hi")])])
    base.update(kw)
    return Request(**base)


def test_text_payload_is_a_single_text_part_with_no_generation_config():
    assert gemini.build_generate_payload(_req()) == {"contents": [{"parts": [{"text": "hi"}]}]}


def test_json_output_sets_response_mime_type():
    payload = gemini.build_generate_payload(_req(output="json"))
    assert payload["generationConfig"] == {"responseMimeType": "application/json"}


def test_gemini_3_gets_a_thinking_level_pro_high_others_low():
    flash = gemini.build_generate_payload(_req("gemini-3-flash-preview", output="json"))
    assert flash["generationConfig"] == {"responseMimeType": "application/json",
                                         "thinkingConfig": {"thinkingLevel": "low"}}
    pro = gemini.build_generate_payload(_req("models/gemini-3-pro-preview"))
    assert pro["generationConfig"] == {"thinkingConfig": {"thinkingLevel": "high"}}


def test_images_become_inline_data_with_their_media_type():
    req = _req(messages=[Message("user", [TextPart("read"), ImagePart(b"png-bytes", "image/jpeg")])])
    parts = gemini.build_generate_payload(req)["contents"][0]["parts"]
    assert parts[0] == {"text": "read"}
    assert parts[1]["inlineData"]["mimeType"] == "image/jpeg"
    assert base64.b64decode(parts[1]["inlineData"]["data"]) == b"png-bytes"


# --- native chat stream (Task 10) -----------------------------------------------------------
REF = ModelRef("gemini", "gemini-3-flash-preview")
DUMMY = "skip_thought_signature_validator"


def _call(id_, name="t", args=None, sig=None, model="gemini-3-flash-preview", minted=False):
    data = {}
    if sig:
        data["thoughtSignature"] = sig
    if minted:
        data["id_minted"] = True
    meta = ProviderMeta("gemini", model, data) if data else None
    return ToolCallPart(id_, name, args if args is not None else {}, meta)


def _chat(messages, **kw):
    return gemini.build_chat_payload(Request(model=REF, messages=messages, **kw))


def test_chat_payload_system_tools_and_thinking_level():
    tool = ToolSpec("lookup", "find", {"type": "object", "properties": {"q": {"type": "string"}}})
    p = _chat([Message("user", [TextPart("hi")])], system="be brief", tools=[tool])
    assert p["systemInstruction"] == {"parts": [{"text": "be brief"}]}
    assert p["tools"] == [{"functionDeclarations": [
        {"name": "lookup", "description": "find", "parametersJsonSchema": tool.parameters}]}]
    assert p["generationConfig"] == {"thinkingConfig": {"thinkingLevel": "low"}}
    assert p["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    bare = _chat([Message("user", [TextPart("hi")])])
    assert "systemInstruction" not in bare and "tools" not in bare


def test_chat_payload_replays_calls_and_merges_consecutive_tool_results():
    msgs = [
        Message("user", [TextPart("go")]),
        Message("assistant", [TextPart("on it"), _call("a", "one", {"x": 1}, sig="SIG"),
                              _call("b", "two", {})]),
        Message("tool", [ToolResultPart("a", '{"ok": true}')]),
        Message("tool", [ToolResultPart("b", "plain words"), ]),
    ]
    c = _chat(msgs)["contents"]
    assert c[1] == {"role": "model", "parts": [
        {"text": "on it"},
        {"functionCall": {"name": "one", "args": {"x": 1}, "id": "a"}, "thoughtSignature": "SIG"},
        {"functionCall": {"name": "two", "args": {}, "id": "b"}}]}
    assert c[2] == {"role": "user", "parts": [
        {"functionResponse": {"name": "one", "id": "a", "response": {"ok": True}}},
        {"functionResponse": {"name": "two", "id": "b", "response": {"result": "plain words"}}}]}
    assert len(c) == 3


def test_tool_result_json_non_dict_is_wrapped_as_parsed_result():
    msgs = [Message("user", [TextPart("go")]),
            Message("assistant", [_call("a", "one", sig="S")]),
            Message("tool", [ToolResultPart("a", "[1, 2]")])]
    resp = _chat(msgs)["contents"][2]["parts"][0]["functionResponse"]["response"]
    assert resp == {"result": [1, 2]}


def test_current_turn_first_call_without_signature_gets_the_dummy():
    msgs = [Message("user", [TextPart("go")]),
            Message("assistant", [_call("a", "one"), _call("b", "two")]),
            Message("tool", [ToolResultPart("a", "{}"), ToolResultPart("b", "{}")]),
            Message("assistant", [_call("c", "three")])]
    c = _chat(msgs)["contents"]
    assert c[1]["parts"][0]["thoughtSignature"] == DUMMY
    assert "thoughtSignature" not in c[1]["parts"][1]
    assert c[3]["parts"][0]["thoughtSignature"] == DUMMY  # each model step


def test_earlier_turn_call_without_signature_gets_no_dummy_and_other_model_is_dropped_in_current_turn():
    msgs = [Message("user", [TextPart("first")]),
            Message("assistant", [_call("a", "one")]),
            Message("tool", [ToolResultPart("a", "{}")]),
            Message("assistant", [TextPart("done")]),
            Message("user", [TextPart("second")]),
            Message("assistant", [_call("b", "two", sig="OLD", model="gemini-2.5-pro")])]
    c = _chat(msgs)["contents"]
    assert "thoughtSignature" not in c[1]["parts"][0]            # earlier turn: bare
    assert c[5]["parts"][0]["thoughtSignature"] == DUMMY          # other model's: replaced in current turn


def test_a_same_model_signature_is_replayed_and_not_replaced():
    msgs = [Message("user", [TextPart("go")]),
            Message("assistant", [_call("a", "one", sig="REAL")])]
    assert _chat(msgs)["contents"][1]["parts"][0]["thoughtSignature"] == "REAL"


def test_minted_ids_are_not_sent_on_replay():
    msgs = [Message("user", [TextPart("go")]),
            Message("assistant", [_call("call_abc", "one", sig="S", minted=True)]),
            Message("tool", [ToolResultPart("call_abc", '{"v": 1}')])]
    c = _chat(msgs)["contents"]
    assert c[1]["parts"][0]["functionCall"] == {"name": "one", "args": {}}
    assert c[2]["parts"][0]["functionResponse"] == {"name": "one", "response": {"v": 1}}


def _sse(*chunks):
    return [(b"data: " + json.dumps(c).encode() + b"\n") if isinstance(c, dict) else c for c in chunks]


def _fc(name, args, **extra):
    return {"functionCall": {"name": name, "args": args}, **extra}


def test_parse_sse_text_then_one_finish_with_ordered_parts_and_usage():
    lines = _sse(
        {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]},
        b"\n",
        {"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True},
                                               {"text": "lo"}]}}]},
        {"candidates": [{"content": {"parts": [
            _fc("one", {"x": 1}, thoughtSignature="SIG"),
            {"functionCall": {"name": "two", "args": {}, "id": "real-id"}}]},
            "finishReason": "STOP"}],
         "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3}},
    )
    events = list(gemini.parse_sse(lines, REF))
    assert [e.text for e in events[:-1]] == ["Hel", "lo"]
    fin = events[-1]
    assert isinstance(fin, Finish) and fin.stop_reason == "stop" and fin.model == REF.model
    assert fin.usage.input == 7 and fin.usage.output == 3
    text, one, two = fin.message.parts
    assert text.text == "Hello"
    assert re.fullmatch(r"call_[0-9a-f]{12}", one.id) and one.name == "one" and one.arguments == {"x": 1}
    assert one.meta == ProviderMeta("gemini", REF.model, {"thoughtSignature": "SIG", "id_minted": True})
    assert two.id == "real-id" and two.meta is None


def test_minted_ids_are_unique_across_streams():
    line = [b"data: " + json.dumps({"candidates": [{"content": {"parts": [_fc("t", {})]}}]}).encode()]
    a = list(gemini.parse_sse(line, REF))[-1].message.parts[0].id
    b = list(gemini.parse_sse(line, REF))[-1].message.parts[0].id
    assert a != b


def test_parse_sse_signature_with_a_real_id_keeps_only_the_signature():
    line = [b"data: " + json.dumps({"candidates": [{"content": {"parts": [
        {"functionCall": {"name": "t", "args": {}, "id": "z"}, "thoughtSignature": "S"}]}}]}).encode()]
    call = list(gemini.parse_sse(line, REF))[-1].message.parts[0]
    assert call.meta == ProviderMeta("gemini", REF.model, {"thoughtSignature": "S"})


class _Resp:
    def __init__(self, lines, fail=None):
        self._lines, self._fail, self.closed = lines, fail, False

    def __iter__(self):
        yield from self._lines
        if self._fail:
            raise self._fail

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _provider(monkeypatch, opener):
    from app.services import llm

    monkeypatch.setattr(llm, "get_gemini_key", lambda: "k")
    monkeypatch.setattr(gemini, "urlopen", opener)
    return gemini.GeminiProvider()


_HELLO = [b'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]},"finishReason":"STOP"}]}\n']


def test_stream_posts_to_the_sse_endpoint_with_the_key_header(monkeypatch):
    seen = {}

    def opener(request, timeout=None):
        seen.update(url=request.full_url, key=request.get_header("X-goog-api-key"),
                    body=json.loads(request.data), timeout=timeout)
        return _Resp(_HELLO)

    events = list(_provider(monkeypatch, opener).stream(Request(model=REF, messages=[Message("user", [TextPart("x")])], timeout=9)))
    assert seen["url"] == ("https://generativelanguage.googleapis.com/v1beta/models/"
                           "gemini-3-flash-preview:streamGenerateContent?alt=sse")
    assert seen["key"] == "k" and seen["timeout"] == 9
    assert seen["body"]["contents"] == [{"role": "user", "parts": [{"text": "x"}]}]
    assert isinstance(events[-1], Finish)


def _hello_req():
    return Request(model=REF, messages=[Message("user", [TextPart("x")])])


def test_stream_http_error_at_open_maps_like_generate(monkeypatch):
    def opener(request, timeout=None):
        raise HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error": "API_KEY_INVALID"}'))

    with pytest.raises(LLMProviderError, match="Gemini refused your API key"):
        list(_provider(monkeypatch, opener).stream(_hello_req()))


def test_stream_timeout_and_connection_errors_at_open(monkeypatch):
    def timed_out(request, timeout=None):
        raise TimeoutError("slow")

    with pytest.raises(LLMProviderError, match="timed out") as caught:
        list(_provider(monkeypatch, timed_out).stream(_hello_req()))
    assert caught.value.timed_out  # attachment_extract words a slow file from this flag

    def refused(request, timeout=None):
        raise URLError(ConnectionRefusedError("no"))

    with pytest.raises(LLMProviderError, match="no connection") as caught:
        list(_provider(monkeypatch, refused).stream(_hello_req()))
    assert not caught.value.timed_out


def test_stream_mid_stream_errors_map_and_close_the_response(monkeypatch):
    resp = _Resp(_HELLO[:1], fail=TimeoutError("cut"))
    with pytest.raises(LLMProviderError, match="timed out"):
        list(_provider(monkeypatch, lambda r, timeout=None: resp).stream(_hello_req()))
    assert resp.closed


def test_stream_closes_the_response_on_early_stop(monkeypatch):
    resp = _Resp(_HELLO)
    gen = _provider(monkeypatch, lambda r, timeout=None: resp).stream(_hello_req())
    assert isinstance(next(gen), TextDelta)
    gen.close()
    assert resp.closed


def test_earlier_turn_call_with_another_models_signature_is_replayed_bare():
    msgs = [Message("user", [TextPart("first")]),
            Message("assistant", [_call("a", "one", sig="OLD", model="gemini-2.5-pro")]),
            Message("tool", [ToolResultPart("a", "{}")]),
            Message("assistant", [TextPart("done")]),
            Message("user", [TextPart("second")])]
    part = _chat(msgs)["contents"][1]["parts"][0]
    assert "thoughtSignature" not in part


def test_stream_incomplete_read_mid_stream_maps_and_closes(monkeypatch):
    resp = _Resp(_HELLO[:1], fail=IncompleteRead(b""))
    with pytest.raises(LLMProviderError, match="didn't answer"):
        list(_provider(monkeypatch, lambda r, timeout=None: resp).stream(_hello_req()))
    assert resp.closed


def test_stream_error_event_raises():
    with pytest.raises(LLMProviderError, match="didn't answer"):
        list(gemini.parse_sse([b'data: {"error": {"message": "overloaded"}}\n'], REF))


def test_stream_blocked_prompt_raises_with_the_reason():
    with pytest.raises(LLMProviderError, match="prompt was blocked: SAFETY"):
        list(gemini.parse_sse([b'data: {"promptFeedback": {"blockReason": "SAFETY"}}\n'], REF))
