"""Who writes for an agent request (design 2026-10-26): the request mark and the setting."""
import contextlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_writer
from app.schemas.mcp_workflow import McpWorkflowSettings
from app.services import llm, mcp_workflow


def _writer(monkeypatch, writer):
    monkeypatch.setattr(mcp_workflow, "peek_settings", lambda session=None: McpWorkflowSettings(writer=writer))


def test_maestro_always_writes_outside_an_agent_request(monkeypatch):
    _writer(monkeypatch, "agent")
    assert agent_writer.maestro_writes() is True  # the web app and the Companion


def test_an_agent_request_in_agent_mode_gets_no_maestro_writing(monkeypatch):
    _writer(monkeypatch, "agent")
    with agent_writer.agent_request():
        assert agent_writer.maestro_writes() is False
    _writer(monkeypatch, "maestro")
    with agent_writer.agent_request():
        assert agent_writer.maestro_writes() is True


def test_model_available_needs_a_key_and_maestro_writing(monkeypatch):
    _writer(monkeypatch, "agent")
    monkeypatch.setattr(llm, "any_model_key_configured", lambda: True)
    assert agent_writer.model_available() is True
    with agent_writer.agent_request():
        assert agent_writer.model_available() is False


def test_a_missing_setting_means_the_agent_app_writes(db_session, tmp_path, monkeypatch):
    # The real read, no stub: no Setting row and no file mirror is the default, so an agent request on a
    # fresh install gets no Maestro writing.
    from app.services import text_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    with agent_writer.agent_request():
        assert agent_writer.maestro_writes() is False
    mcp_workflow.set_settings(McpWorkflowSettings(writer="maestro"), db_session)
    with agent_writer.agent_request():
        assert agent_writer.maestro_writes() is True


def test_the_middleware_marks_only_requests_with_the_mcp_origin(client, monkeypatch):
    seen = []
    monkeypatch.setattr(agent_writer, "_on_request", lambda: seen.append(agent_writer.is_agent_request()))
    client.get("/api/health", headers={"X-Maestro-CS-Origin": "mcp"})
    client.get("/api/health")
    client.get("/api/health", headers={"X-Maestro-CS-Origin": "someone"})
    assert seen == [True, False, False]
    assert agent_writer.is_agent_request() is False  # the mark ends with its request


def test_the_agent_mark_is_the_innermost_middleware():
    # user_middleware runs first-to-last, outermost first: the mark sits inside Host → Origin → CORS
    # and refuses nothing, so it cannot change what those let through.
    from app.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert names[-1] == "AgentRequestMiddleware"
    assert names.index("SyncPublicHostMiddleware") < names.index("OriginGuardMiddleware") < names.index("CORSMiddleware")


def test_the_mark_reaches_a_sync_route_on_the_threadpool():
    # The reason for a ContextVar in a pure ASGI middleware: a sync handler runs on a worker thread, and
    # the context is copied into it.
    inner = FastAPI()

    @inner.get("/probe")
    def probe():
        return {"agent": agent_writer.is_agent_request()}

    wrapped = TestClient(agent_writer.AgentRequestMiddleware(inner))
    assert wrapped.get("/probe", headers={"X-Maestro-CS-Origin": "mcp"}).json() == {"agent": True}
    assert wrapped.get("/probe").json() == {"agent": False}


def _model_must_not_run(*_a, **_k):
    raise AssertionError("model reached")


def test_no_model_call_runs_for_an_agent_request_in_agent_mode(monkeypatch):
    _writer(monkeypatch, "agent")
    monkeypatch.setattr(llm, "_call_model", _model_must_not_run)
    with agent_writer.agent_request():
        with pytest.raises(agent_writer.AgentWritesError):
            llm.call_openai(prompt="p", model="m")


@pytest.mark.parametrize(("writer", "agent"), [("agent", False), ("maestro", True), ("maestro", False)])
def test_the_model_is_reached_outside_agent_mode(tmp_path, monkeypatch, writer, agent):
    _writer(monkeypatch, writer)
    monkeypatch.setattr(llm.settings, "logs_dir", str(tmp_path))  # _log_call's record of the call
    calls = []
    monkeypatch.setattr(llm, "_call_model", lambda *a, **k: (calls.append(a), ('{"ok": true}', None))[1])
    with agent_writer.agent_request() if agent else contextlib.nullcontext():
        assert llm.call_openai(prompt="p", model="m") == {"ok": True}
    assert len(calls) == 1


def test_the_backstop_answers_an_agent_request_with_a_409(client, tmp_path, monkeypatch):
    # Whichever route asked, the refusal reaches the caller as the sentence, not a 500. The real setting
    # read, on the threadpool of a sync route: no saved row is the default, the agent app.
    from app.main import app
    from app.services import text_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    monkeypatch.setattr(llm.settings, "logs_dir", str(tmp_path))
    calls = []
    monkeypatch.setattr(llm, "_call_model", lambda *a, **k: (calls.append(a), ('{"ok": true}', None))[1])

    @app.get("/api/_test/agent-writes-backstop")
    def _asks_the_model():
        return llm.call_openai(prompt="p", model="m")

    mcp = {"X-Maestro-CS-Origin": "mcp"}
    try:
        refused = client.get("/api/_test/agent-writes-backstop", headers=mcp)
        web = client.get("/api/_test/agent-writes-backstop")
        client.put("/api/settings/mcp-workflow", json={"value": {"hints": True, "writer": "maestro"}})
        maestro = client.get("/api/_test/agent-writes-backstop", headers=mcp)
    finally:
        app.router.routes.pop()
    assert refused.status_code == 409
    assert refused.json() == {"detail": agent_writer.AGENT_WRITES}
    assert web.json() == maestro.json() == {"ok": True}
    assert len(calls) == 2
