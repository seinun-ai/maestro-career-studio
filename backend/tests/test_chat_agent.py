import json
from copy import deepcopy
from types import SimpleNamespace

from app.models.base_resume import BaseResume
from app.models.chat import ChatSession
from app.services import base_resume_render, chat_agent
from app.services.resume_versions import get_versions

SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Summary",
    "skills": [],
    "experience": [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2020",
            "enabled": True,
            "bullets": ["Built pipeline."],
        }
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _delta_chunk(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


def _tool_call_delta(index, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeClient:
    """Yields one scripted stream (list of chunks) per completions.create call."""

    def __init__(self, streams):
        self._streams = list(streams)
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._streams.pop(0))


def _seed(db_session, monkeypatch, tmp_path):
    from app.services import resume_ops

    monkeypatch.setattr(base_resume_render, "render_base_resume", lambda *a, **k: None)
    monkeypatch.setattr(
        resume_ops.base_resume_render, "render_base_resume", lambda *a, **k: None
    )

    monkeypatch.setattr(resume_ops.settings, "base_resumes_dir", tmp_path)
    db_session.add(BaseResume(slug="ds", display_name="DS", data_json=deepcopy(SAMPLE_DATA)))
    session = ChatSession()
    db_session.add(session)
    db_session.commit()
    return session


def test_plain_text_turn_streams_and_persists(db_session, monkeypatch, tmp_path):
    session = _seed(db_session, monkeypatch, tmp_path)
    client = FakeClient([[_delta_chunk("Hel"), _delta_chunk("lo")]])

    events = list(
        chat_agent.run_turn(db_session, session, "hi", None, client=client, model="gpt-test")
    )

    kinds = [e["type"] for e in events]
    assert kinds == ["message", "delta", "delta", "message", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello"
    roles = [m.role for m in session.messages]
    assert roles == ["user", "assistant"]
    assert session.messages[1].content == "Hello"
    assert session.title == "hi"


def test_tool_call_turn_edits_resume_and_emits_change_card(db_session, monkeypatch, tmp_path):
    session = _seed(db_session, monkeypatch, tmp_path)
    args = json.dumps(
        {"kind": "base", "key": "ds", "ops": [{"kind": "replace_summary", "value": "Better."}]}
    )
    round1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(0, "call_1", "edit_resume", args[:10])]),
        _delta_chunk(tool_calls=[_tool_call_delta(0, None, None, args[10:])]),
    ]
    round2 = [_delta_chunk("Done — tightened the summary.")]
    client = FakeClient([round1, round2])

    events = list(
        chat_agent.run_turn(
            db_session,
            session,
            "tighten my summary",
            {"target_kind": "base", "target_key": "ds"},
            client=client,
            model="gpt-test",
        )
    )

    card = next(e for e in events if e["type"] == "change_card")
    assert card["resume_key"] == "ds" and card["version_number"] == 1

    versions = get_versions(db_session, "base", "ds")
    assert versions[0].source == "chat"
    # source_ref points at the triggering user message
    user_msg = session.messages[0]
    assert versions[0].source_ref == str(user_msg.id)

    # second LLM round got the tool result in its message array
    second_call_messages = client.calls[1]["messages"]
    assert any(m["role"] == "tool" and "change_card" in m["content"] for m in second_call_messages)
    # context block was injected as a system message
    assert any(
        m["role"] == "system" and "Pinned resume" in m["content"] for m in second_call_messages
    )

    roles = [m.role for m in session.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert events[-1]["type"] == "done"


def test_kb_capture_tool_result_emits_and_persists_card_meta(
    db_session, monkeypatch, tmp_path,
):
    session = _seed(db_session, monkeypatch, tmp_path)
    payload = {
        "entity_id": "89269a3d-f567-43b9-9d5f-630acfd2e6c3",
        "entity_title": "Orbit",
        "point_count": 2,
    }
    monkeypatch.setattr(
        chat_agent,
        "execute_tool",
        lambda ctx, name, arguments: {"kb_capture": payload},
    )
    round1 = [
        _delta_chunk(
            tool_calls=[
                _tool_call_delta(0, "call_kb", "kb_capture", json.dumps({"text": "shipped it"}))
            ]
        )
    ]
    client = FakeClient([round1, [_delta_chunk("Saved it to your Career KB inbox.")]])

    events = list(
        chat_agent.run_turn(
            db_session, session, "we shipped it", None, client=client, model="gpt-test"
        )
    )

    card = next(event for event in events if event["type"] == "kb_capture")
    assert {key: card[key] for key in payload} == payload
    tool_message = next(message for message in session.messages if message.role == "tool")
    assert tool_message.meta_json == {"kb_capture": payload}


def test_scope_violation_flows_back_as_tool_error(db_session, monkeypatch, tmp_path):
    session = _seed(db_session, monkeypatch, tmp_path)
    args = json.dumps(
        {"kind": "base", "key": "ds", "ops": [{"kind": "replace_summary", "value": "x"}]}
    )
    round1 = [_delta_chunk(tool_calls=[_tool_call_delta(0, "call_1", "edit_resume", args)])]
    round2 = [_delta_chunk("That edit is outside your selection.")]
    client = FakeClient([round1, round2])

    events = list(
        chat_agent.run_turn(
            db_session,
            session,
            "rewrite",
            {
                "target_kind": "base",
                "target_key": "ds",
                "selections": [{"section": "experience", "index": 0}],
            },
            client=client,
            model="gpt-test",
        )
    )

    assert not any(e["type"] == "change_card" for e in events)
    assert get_versions(db_session, "base", "ds") == []
    tool_msg = next(m for m in session.messages if m.role == "tool")
    assert "outside the user's selected scope" in tool_msg.content


def test_llm_failure_yields_error_event(db_session, monkeypatch, tmp_path):
    session = _seed(db_session, monkeypatch, tmp_path)

    class BoomClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("api down")

    events = list(
        chat_agent.run_turn(db_session, session, "hi", None, client=BoomClient, model="gpt-test")
    )
    assert events[-1]["type"] == "error"
    assert "api down" in events[-1]["detail"]


def test_gpt56_models_send_reasoning_effort_none(db_session, monkeypatch, tmp_path):
    session = _seed(db_session, monkeypatch, tmp_path)
    client = FakeClient([[_delta_chunk("ok")]])
    list(chat_agent.run_turn(db_session, session, "hi", None, client=client, model="gpt-5.6-luna"))
    assert client.calls[0]["reasoning_effort"] == "none"


def test_gpt4o_does_not_send_reasoning_effort(db_session, monkeypatch, tmp_path):
    session = _seed(db_session, monkeypatch, tmp_path)
    client = FakeClient([[_delta_chunk("ok")]])
    list(chat_agent.run_turn(db_session, session, "hi", None, client=client, model="gpt-4o"))
    assert "reasoning_effort" not in client.calls[0]


def test_run_turn_asks_factory_for_gemini_model(db_session, monkeypatch, tmp_path):
    """Without an injected client, a Gemini id must go through get_chat_client."""
    session = _seed(db_session, monkeypatch, tmp_path)
    client = FakeClient([[_delta_chunk("ok")]])
    factory_calls: list[str] = []

    def factory(model: str):
        factory_calls.append(model)
        return client

    monkeypatch.setattr(chat_agent, "get_chat_client", factory)
    list(
        chat_agent.run_turn(
            db_session, session, "hi", None, model="gemini-3.5-flash-lite"
        )
    )
    assert factory_calls == ["gemini-3.5-flash-lite"]
    assert client.calls, "factory client must be the one run_turn uses"
