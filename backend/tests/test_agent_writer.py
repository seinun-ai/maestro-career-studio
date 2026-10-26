"""Who writes for an agent request (design 2026-10-26): the request mark and the setting."""
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
