"""POST /api/autofill/reason: the Companion's own origin only; the answer level is the server's."""

import json

from app.schemas.auto_apply import AutoApplySettings
from app.schemas.companion_apply import CompanionApplySettings
from app.services import auto_apply_settings, companion_apply, llm, model_settings
from tests.fake_provider import FakeProvider, install

# conftest's `client` fixture routes `get_db` to this test's `db_session`; the made-up extension id is the one
# conftest allows (tests/test_companion_job_site_login.py uses the same).
EXT = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}


def _switches(db, *, full=True, think=True, stop=False):
    """The two switches the route obeys on its own: stale panel facts never decide whether the model is paid."""
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=full), db)
    companion_apply.set_settings(CompanionApplySettings(think_when_stuck=think, stop_each_step=stop), db)


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
    _switches(db_session)
    monkeypatch.setattr(llm, "_log_call", lambda *a, **k: None)
    model_settings.set_answer_level(db_session, "facts")
    install(monkeypatch, FakeProvider([[json.dumps({"note": "Write it.", "actions": [{"type": "write", "fid": "f4"}]})]],
                                      name="anthropic"), model="reasoner-test")
    monkeypatch.setattr(model_settings, "get_reasoning_model", lambda *_: "reasoner-test")
    r = client.post("/api/autofill/reason", json=BODY, headers=EXT)
    assert r.status_code == 200
    assert r.json()["actions"][0]["type"] == "ask_user" and r.json()["rejected"] == ["careful_level"]


def test_the_default_level_lets_a_write_through(client, db_session, monkeypatch):
    _switches(db_session)
    monkeypatch.setattr(llm, "_log_call", lambda *a, **k: None)
    install(monkeypatch, FakeProvider([[json.dumps({"note": "Write it.", "actions": [{"type": "write", "fid": "f4"}]})]],
                                      name="anthropic"), model="reasoner-test")
    monkeypatch.setattr(model_settings, "get_reasoning_model", lambda *_: "reasoner-test")
    r = client.post("/api/autofill/reason", json=BODY, headers=EXT)
    assert r.json()["actions"] == [{"type": "write", "fid": "f4"}] and r.json()["rejected"] == []


def test_with_full_automation_or_think_when_stuck_off_the_route_asks_the_user_without_calling_the_model(
        client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_openai", lambda **kw: calls.append(kw))
    for full, think in ((False, True), (True, False), (False, False)):
        _switches(db_session, full=full, think=think)
        r = client.post("/api/autofill/reason", json=BODY, headers=EXT)
        assert r.status_code == 200
        assert r.json()["actions"][0]["type"] == "ask_user" and r.json()["rejected"] == ["switched_off"]
    assert calls == []


def test_a_fresh_install_has_full_automation_off_so_the_route_does_not_spend(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_openai", lambda **kw: calls.append(kw))
    assert client.post("/api/autofill/reason", json=BODY, headers=EXT).json()["rejected"] == ["switched_off"]
    assert calls == []


def test_with_stop_after_each_step_on_the_route_asks_the_user_without_calling_the_model(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_openai", lambda **kw: calls.append(kw))
    _switches(db_session, stop=True)
    r = client.post("/api/autofill/reason", json=BODY, headers=EXT)
    assert r.status_code == 200 and r.json()["actions"][0]["type"] == "ask_user" and r.json()["rejected"] == ["switched_off"]
    assert calls == []
