"""POST /api/autofill/reason: the Companion's own origin only; the answer level is the server's."""

import json

from app.services import llm, model_settings
from tests.fake_provider import FakeProvider, install

# conftest's `client` fixture routes `get_db` to this test's `db_session`; the made-up extension id is the one
# conftest allows (tests/test_companion_job_site_login.py uses the same).
EXT = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}
BODY = {"why": "open_questions", "round": 1,
        "fields": [{"fid": "f4", "question": "Field of study", "shape": "text", "required": True}]}


def test_anyone_but_the_companion_is_refused(client, db_session):
    assert client.post("/api/autofill/reason", json=BODY).status_code == 403
    # An unlisted Origin is refused by the origin guard before routing (inv-browser-boundary), 403 either way.
    assert client.post("/api/autofill/reason", json=BODY, headers={"Origin": "https://jobs.acme.test"}).status_code == 403


def test_a_refused_caller_never_reaches_the_model(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_openai", lambda **kw: calls.append(kw))
    client.post("/api/autofill/reason", json=BODY)
    assert calls == []


def test_a_body_carrying_a_value_is_refused(client, db_session):
    bad = {**BODY, "fields": [{**BODY["fields"][0], "value": "Mathematics"}]}
    assert client.post("/api/autofill/reason", json=bad, headers=EXT).status_code == 422


def test_the_level_is_read_server_side_so_careful_turns_write_off(client, db_session, monkeypatch):
    monkeypatch.setattr(llm, "_log_call", lambda *a, **k: None)
    model_settings.set_answer_level(db_session, "facts")
    install(monkeypatch, FakeProvider([[json.dumps({"note": "Write it.", "actions": [{"type": "write", "fid": "f4"}]})]],
                                      name="anthropic"), model="reasoner-test")
    monkeypatch.setattr(model_settings, "get_reasoning_model", lambda *_: "reasoner-test")
    r = client.post("/api/autofill/reason", json=BODY, headers=EXT)
    assert r.status_code == 200
    assert r.json()["actions"][0]["type"] == "ask_user" and r.json()["rejected"] == ["careful_level"]


def test_the_default_level_lets_a_write_through(client, db_session, monkeypatch):
    monkeypatch.setattr(llm, "_log_call", lambda *a, **k: None)
    install(monkeypatch, FakeProvider([[json.dumps({"note": "Write it.", "actions": [{"type": "write", "fid": "f4"}]})]],
                                      name="anthropic"), model="reasoner-test")
    monkeypatch.setattr(model_settings, "get_reasoning_model", lambda *_: "reasoner-test")
    r = client.post("/api/autofill/reason", json=BODY, headers=EXT)
    assert r.json()["actions"] == [{"type": "write", "fid": "f4"}] and r.json()["rejected"] == []
