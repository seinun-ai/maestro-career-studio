"""Who writes for an agent request (design 2026-10-26): the request mark and the setting."""
import asyncio
import contextlib

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import agent_writer
from app.schemas.mcp_workflow import McpWorkflowSettings
from app.services import llm, mcp_workflow
from app.write_origin import WriteOrigin, get_write_origin


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


def test_the_agent_mark_is_the_innermost_middleware():
    # user_middleware runs first-to-last, outermost first: the mark sits inside Host → Origin → CORS
    # and refuses nothing, so it cannot change what those let through.
    from app.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert names[-1] == "AgentRequestMiddleware"
    assert names.index("SyncPublicHostMiddleware") < names.index("OriginGuardMiddleware") < names.index("CORSMiddleware")


_probe = FastAPI()


@_probe.get("/probe")
def _probe_route(origin: WriteOrigin = Depends(get_write_origin)):
    # A sync handler, so it runs on a worker thread: the reason for a ContextVar in a pure ASGI
    # middleware is that the context is copied into it.
    return {"agent": agent_writer.is_agent_request(), "origin": origin.origin}


@pytest.mark.parametrize(
    ("headers", "agent"),
    [
        ({"X-Maestro-CS-Origin": "mcp"}, True),
        ({"X-Career-Studio-Origin": "mcp"}, True),  # the pre-rename header, a one-release alias
        ({"X-Maestro-CS-Origin": " MCP "}, True),  # trimmed, any case
        ({}, False),  # the web app and the Companion
        ({"X-Maestro-CS-Origin": "someone"}, False),
    ],
    ids=["mcp", "legacy-header", "trimmed-any-case", "no-header", "unknown"],
)
def test_the_mark_follows_the_origin_header_on_a_sync_route(headers, agent):
    # One rule, two readers: the mark and the write origin the KB and resume routes record agree.
    response = TestClient(agent_writer.AgentRequestMiddleware(_probe)).get("/probe", headers=headers)
    assert response.json() == {"agent": agent, "origin": "mcp" if agent else None}


@pytest.mark.parametrize("inner_fails", [False, True], ids=["answered", "raised"])
def test_the_mark_ends_with_its_request(inner_fails):
    # Driven in one context on purpose: TestClient runs each request in its own task, where a mark
    # left set would never be seen again, so only a direct call shows the reset.
    seen = []

    async def inner(scope, receive, send):
        seen.append(agent_writer.is_agent_request())
        if inner_fails:
            raise RuntimeError("the route failed")

    async def one_request():
        scope = {"type": "http", "headers": [(b"x-maestro-cs-origin", b"mcp")]}
        with contextlib.suppress(RuntimeError):
            await agent_writer.AgentRequestMiddleware(inner)(scope, None, None)
        return agent_writer.is_agent_request()

    assert asyncio.run(one_request()) is False
    assert seen == [True]


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

    def _asks_the_model():
        return llm.call_openai(prompt="p", model="m")

    app.add_api_route("/api/_test/agent-writes-backstop", _asks_the_model, methods=["GET"])
    route = next(r for r in app.router.routes if getattr(r, "endpoint", None) is _asks_the_model)
    mcp = {"X-Maestro-CS-Origin": "mcp"}
    try:
        refused = client.get("/api/_test/agent-writes-backstop", headers=mcp)
        web = client.get("/api/_test/agent-writes-backstop")
        client.put("/api/settings/mcp-workflow", json={"value": {"hints": True, "writer": "maestro"}})
        maestro = client.get("/api/_test/agent-writes-backstop", headers=mcp)
    finally:
        app.router.routes.remove(route)
    assert refused.status_code == 409
    assert refused.json() == {"detail": agent_writer.AGENT_WRITES}
    assert web.json() == maestro.json() == {"ok": True}
    assert len(calls) == 2
