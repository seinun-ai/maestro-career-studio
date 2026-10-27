"""Streamable HTTP contract, using only in-process ASGI requests."""

import asyncio
import contextlib
import inspect
import json
import threading

import pytest
from mcp.server.fastmcp import Context, FastMCP
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_server import http as mcp_http
from mcp_server import server as srv
from mcp_server.profiles import allowed_tools

HDR = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest-client", "version": "1"},
    },
}


def _app(endpoint):
    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with endpoint.run():
            yield

    return Starlette(
        routes=[Route("/mcp", endpoint=endpoint), Route("/mcp/{profile}", endpoint=endpoint)],
        lifespan=lifespan,
    )


@pytest.fixture
def client():
    with TestClient(_app(mcp_http.McpEndpoint())) as c:
        yield c


def _session(c, path="/mcp"):
    r = c.post(path, json=INIT, headers=HDR)
    assert r.status_code == 200, r.text
    sid = r.headers["mcp-session-id"]
    initialized = c.post(
        path,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={**HDR, "Mcp-Session-Id": sid},
    )
    assert initialized.status_code == 202, initialized.text
    return sid


def _rpc(c, path, sid, method, params=None, id_=2):
    body = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}
    return c.post(path, json=body, headers={**HDR, "Mcp-Session-Id": sid})


@pytest.mark.parametrize("profile", ["full", "profile", "hunt", "tailor", "apply", "track", "templates"])
def test_each_profile_lists_exactly_its_allowlist(client, profile):
    path = "/mcp" if profile == "full" else f"/mcp/{profile}"
    sid = _session(client, path)
    names = {t["name"] for t in _rpc(client, path, sid, "tools/list").json()["result"]["tools"]}
    allow = allowed_tools(profile)
    assert names == (set(srv.list_registered_tool_names("full")) if allow is None else set(allow))


@pytest.mark.parametrize("old, new", [("career", "profile"), ("explore", "track")])
def test_an_old_set_name_serves_its_new_set_for_one_release(client, old, new):
    sid = _session(client, f"/mcp/{old}")
    names = {t["name"] for t in _rpc(client, f"/mcp/{old}", sid, "tools/list").json()["result"]["tools"]}
    assert names == set(allowed_tools(new))


def test_a_hidden_tool_is_refused_with_todays_text(client):
    sid = _session(client, "/mcp/hunt")
    hidden = next(
        n for n in srv.list_registered_tool_names("full") if n not in allowed_tools("hunt")
    )
    res = _rpc(
        client, "/mcp/hunt", sid, "tools/call", {"name": hidden, "arguments": {}}
    ).json()["result"]
    assert res["isError"] is True and f"Unknown tool: {hidden}" in res["content"][0]["text"]


@pytest.mark.parametrize("path", ["/mcp", "/mcp/profile"])
def test_kb_approve_points_refuses_an_old_retire_state_over_http(client, monkeypatch, path):
    calls = []
    monkeypatch.setattr(
        srv._client, "kb_approve_points", lambda *a, **k: calls.append((a, k)) or {"results": []}
    )
    sid = _session(client, path)
    args = {"point_ids": ["p1"], "state": "retired"}
    res = _rpc(
        client, path, sid, "tools/call", {"name": "kb_approve_points", "arguments": args}
    ).json()["result"]
    assert res["isError"] is True
    assert res["content"][0]["text"] == (
        "kb_approve_points only approves; kb_retire_points retires points."
    )
    assert calls == []


def test_responses_are_json_and_stateful(client):
    r = client.post("/mcp", json=INIT, headers=HDR)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers.get("mcp-session-id")


@pytest.mark.parametrize("profile", ["full", "profile", "hunt", "tailor", "apply", "track", "templates"])
@pytest.mark.parametrize("app_version, expected", [("0.9.0", "0.9.0"), (None, "dev")])
def test_initialize_reports_maestro_version_for_every_profile(
    monkeypatch, profile, app_version, expected
):
    if app_version is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", app_version)
    path = "/mcp" if profile == "full" else f"/mcp/{profile}"
    with TestClient(_app(mcp_http.McpEndpoint())) as c:
        response = c.post(path, json=INIT, headers=HDR)
        assert response.status_code == 200, response.text
        assert response.json()["result"]["serverInfo"]["version"] == expected


def test_an_unknown_profile_is_404(client):
    assert client.post("/mcp/nope", json=INIT, headers=HDR).status_code == 404


def test_a_stale_session_is_404_so_the_bridge_can_replay(client):
    r = _rpc(client, "/mcp", "deadbeef", "tools/list")
    assert r.status_code == 404


def test_sdk_dns_rebinding_protection_is_off():
    """The app's Host/Origin middleware is the one definition (SYSTEM.md §6)."""
    endpoint = mcp_http.McpEndpoint()
    assert endpoint.security.enable_dns_rebinding_protection is False


def test_registered_tools_run_off_the_event_loop_but_module_functions_stay_sync():
    scratch = FastMCP("offload-test")
    seen = {}

    @scratch.tool()
    def worker_thread() -> dict:
        seen["worker"] = threading.get_ident()
        return {"items": []}

    @scratch.tool()
    async def loop_thread() -> dict:
        seen["loop"] = threading.get_ident()
        return {"items": []}

    with TestClient(_app(mcp_http.McpEndpoint(scratch))) as c:
        sid = _session(c)
        for id_, name in enumerate(("worker_thread", "loop_thread"), start=2):
            res = _rpc(c, "/mcp", sid, "tools/call", {"name": name}, id_).json()["result"]
            assert not res["isError"], res
    assert seen["worker"] != seen["loop"]
    assert callable(srv.list_templates) and not inspect.iscoroutinefunction(srv.list_templates)


def test_real_registered_tool_runs_without_an_event_loop(monkeypatch):
    seen = []

    def list_templates():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            seen.append(False)
        else:
            seen.append(True)
        return {"items": []}

    monkeypatch.setattr(srv._client, "list_templates", list_templates)
    # Other endpoint constructions may already have wrapped the shared registry.
    # Restore this real registration's sync function so this constructor must offload it.
    tool = srv.mcp._tool_manager.get_tool("list_templates")
    monkeypatch.setattr(tool, "fn", srv.list_templates)
    monkeypatch.setattr(tool, "is_async", False)
    with TestClient(_app(mcp_http.McpEndpoint())) as c:
        sid = _session(c)
        res = _rpc(c, "/mcp", sid, "tools/call", {"name": "list_templates"}).json()["result"]
        assert not res["isError"], res
    assert seen == [False]


def test_request_body_larger_than_sdk_default_is_accepted(client):
    sid = _session(client)
    response = _rpc(client, "/mcp", sid, "ping", {"padding": "x" * (5 * 1024 * 1024)})
    assert response.status_code != 413, response.text


def test_offloading_is_idempotent_and_preserves_async_tools():
    scratch = FastMCP("idempotent-test")

    @scratch.tool()
    def sync_tool() -> str:
        return "sync"

    @scratch.tool()
    async def async_tool() -> str:
        return "async"

    async_fn = scratch._tool_manager.get_tool("async_tool").fn
    assert mcp_http.offload_tools(scratch) == 1
    wrapped = scratch._tool_manager.get_tool("sync_tool").fn
    assert mcp_http.offload_tools(scratch) == 0
    assert scratch._tool_manager.get_tool("sync_tool").fn is wrapped
    assert scratch._tool_manager.get_tool("async_tool").fn is async_fn


def test_worker_receives_request_profile_and_client_info(monkeypatch):
    scratch = FastMCP("context-test")
    monkeypatch.setenv("MAESTRO_CS_MCP_PROFILE", "hunt")

    @scratch.tool()
    def list_templates(ctx: Context) -> dict:
        allow = srv._active_allowed_tools()
        return {
            "profile": srv.CURRENT_PROFILE.get(),
            "allowed": sorted(allow) if allow is not None else None,
            "client": srv._client_label(ctx),
        }

    with TestClient(_app(mcp_http.McpEndpoint(scratch))) as c:
        for id_, profile in enumerate(("templates", "full"), start=2):
            path = f"/mcp/{profile}"
            sid = _session(c, path)
            res = _rpc(c, path, sid, "tools/call", {"name": "list_templates"}, id_).json()[
                "result"
            ]
            assert not res["isError"], res
            assert json.loads(res["content"][0]["text"]) == {
                "profile": profile,
                "allowed": sorted(allowed_tools(profile)) if profile != "full" else None,
                "client": "pytest-client",
            }
    assert srv.CURRENT_PROFILE.get() is None


def test_sessions_cannot_cross_profiles(client):
    sid = _session(client, "/mcp/hunt")
    assert _rpc(client, "/mcp/apply", sid, "tools/list").status_code == 404
    assert _rpc(client, "/mcp/hunt", sid, "tools/list").status_code == 200


def test_lifespan_can_restart_and_forgets_old_sessions():
    app = _app(mcp_http.McpEndpoint())
    with TestClient(app) as c:
        old_sid = _session(c)
        assert _rpc(c, "/mcp", old_sid, "tools/list").status_code == 200
    with TestClient(app) as c:
        assert _rpc(c, "/mcp", old_sid, "tools/list").status_code == 404
        sid = _session(c)
        assert _rpc(c, "/mcp", sid, "tools/list").status_code == 200


def test_offloaded_tool_errors_keep_todays_text():
    scratch = FastMCP("error-test")

    @scratch.tool()
    def broken() -> str:
        raise ValueError("broken input")

    with TestClient(_app(mcp_http.McpEndpoint(scratch))) as c:
        sid = _session(c)
        res = _rpc(c, "/mcp", sid, "tools/call", {"name": "broken"}).json()["result"]
    assert res["isError"] is True
    assert res["content"][0]["text"] == "Error executing tool broken: broken input"


@pytest.mark.parametrize("profile", ["full", "profile", "tailor", "templates"])
def test_initialize_carries_the_sets_own_instructions(client, profile):
    from mcp_server import orientation

    path = "/mcp" if profile == "full" else f"/mcp/{profile}"
    result = client.post(path, json=INIT, headers=HDR).json()["result"]
    assert result["instructions"] == orientation.instructions_for(profile)


@pytest.fixture
def catalog(monkeypatch):
    """The automation cards as GET /api/automations serves them (no backend in these tests)."""
    from app.services import automations

    body = automations.catalog().model_dump(mode="json")
    monkeypatch.setattr(srv._client, "get_automations", lambda: body)
    return {c["id"]: c for c in body["cards"]}


def test_a_set_offers_the_playbooks_that_use_it_as_prompts(client, catalog):
    sid = _session(client, "/mcp/tailor")
    prompts = _rpc(client, "/mcp/tailor", sid, "prompts/list").json()["result"]["prompts"]
    assert [p["name"] for p in prompts] == ["tailor-run"]
    assert prompts[0]["description"] == catalog["tailor-run"]["summary"]


def test_the_full_set_offers_every_playbook(client, catalog):
    sid = _session(client, "/mcp")
    prompts = _rpc(client, "/mcp", sid, "prompts/list").json()["result"]["prompts"]
    assert [p["name"] for p in prompts] == list(catalog)


def test_a_prompt_is_exactly_the_copy_prompt(client, catalog):
    sid = _session(client, "/mcp/tailor")
    got = _rpc(client, "/mcp/tailor", sid, "prompts/get", {"name": "tailor-run"}).json()["result"]
    assert got["messages"] == [
        {"role": "user", "content": {"type": "text", "text": catalog["tailor-run"]["prompt"]}}
    ]


def test_a_playbook_from_another_set_is_not_served(client, catalog):
    sid = _session(client, "/mcp/tailor")
    res = _rpc(client, "/mcp/tailor", sid, "prompts/get", {"name": "job-hunt"}).json()
    assert "error" in res
