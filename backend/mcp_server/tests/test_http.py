"""Streamable HTTP contract, using only in-process ASGI requests."""

import asyncio
import inspect
import json
import logging
import threading

import anyio.from_thread
import pytest
from mcp import Client, MCPError
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.testclient import TestClient

from mcp_server import http as mcp_http
from mcp_server import server as srv
from mcp_server.client import BackendError
from mcp_server.profiles import allowed_tools
from mcp_server.tests._wire import HDR, INIT, asgi_app, rpc, session


@pytest.fixture
def client():
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        yield c


@pytest.mark.parametrize("profile", ["full", "profile", "hunt", "tailor", "apply", "track", "templates"])
def test_each_profile_lists_exactly_its_allowlist(client, profile):
    path = "/mcp" if profile == "full" else f"/mcp/{profile}"
    sid = session(client, path)
    names = {t["name"] for t in rpc(client, path, sid, "tools/list").json()["result"]["tools"]}
    allow = allowed_tools(profile)
    assert names == (set(srv.list_registered_tool_names("full")) if allow is None else set(allow))


def test_each_set_is_its_own_server_holding_only_its_tools():
    served = mcp_http.McpEndpoint().servers["hunt"]
    assert isinstance(served, mcp_http._ServedSet)
    assert {t.name for t in served._tool_manager.list_tools()} == set(allowed_tools("hunt"))


@pytest.mark.parametrize("old, new", [("career", "profile"), ("explore", "track")])
def test_an_old_set_name_serves_its_new_set_for_one_release(client, old, new):
    sid = session(client, f"/mcp/{old}")
    names = {t["name"] for t in rpc(client, f"/mcp/{old}", sid, "tools/list").json()["result"]["tools"]}
    assert names == set(allowed_tools(new))


def test_a_hidden_tool_is_refused_with_todays_text(client):
    sid = session(client, "/mcp/hunt")
    hidden = next(
        n for n in srv.list_registered_tool_names("full") if n not in allowed_tools("hunt")
    )
    res = rpc(
        client, "/mcp/hunt", sid, "tools/call", {"name": hidden, "arguments": {}}
    ).json()["result"]
    assert res["isError"] is True and f"Unknown tool: {hidden}" in res["content"][0]["text"]


@pytest.mark.parametrize("path", ["/mcp", "/mcp/profile"])
def test_kb_approve_points_refuses_an_old_retire_state_over_http(client, monkeypatch, path):
    calls = []
    monkeypatch.setattr(
        srv._client, "kb_approve_points", lambda *a, **k: calls.append((a, k)) or {"results": []}
    )
    sid = session(client, path)
    args = {"point_ids": ["p1"], "state": "retired"}
    res = rpc(
        client, path, sid, "tools/call", {"name": "kb_approve_points", "arguments": args}
    ).json()["result"]
    assert res["isError"] is True
    assert res["content"][0]["text"] == (
        "kb_approve_points only approves; kb_retire_points retires points."
    )
    assert calls == []


@pytest.mark.parametrize("profile", ["full", "profile", "hunt", "tailor", "apply", "track", "templates"])
def test_a_removed_name_answers_with_its_replacement_on_every_set(client, profile):
    from mcp_server import replaced

    path = "/mcp" if profile == "full" else f"/mcp/{profile}"
    sid = session(client, path)
    for id_, name in enumerate(sorted(replaced.REPLACED_TOOLS), start=2):
        res = rpc(
            client, path, sid, "tools/call", {"name": name, "arguments": {}}, id_
        ).json()["result"]
        assert res["isError"] is True, (profile, name)
        expected = replaced.replaced_message(name, served=allowed_tools(profile))
        assert res["content"][0]["text"] == expected, (profile, name)


@pytest.mark.parametrize(
    "path, suffix",
    [("/mcp/track", ""), ("/mcp", ""), ("/mcp/hunt", ", in the track set")],
)
def test_a_removed_name_says_which_set_holds_its_replacement_only_when_this_one_lacks_it(
    client, path, suffix
):
    sid = session(client, path)
    res = rpc(
        client, path, sid, "tools/call", {"name": "explore_top_skills", "arguments": {}}
    ).json()["result"]
    assert res["content"][0]["text"] == (
        f'explore_top_skills was replaced by explore_trends(view="top_skills"){suffix}.'
    )


def test_a_plain_registry_still_answers_a_removed_name():
    """Every set is a _ServedSet whatever registry it is built from, so even a plain MCPServer's
    full set answers a removed name with its replacement."""
    from mcp_server import replaced

    plain = MCPServer("plain")

    @plain.tool()
    def scratch_tool() -> str:
        return "ok"

    with TestClient(asgi_app(mcp_http.McpEndpoint(plain))) as c:
        sid = session(c)
        res = rpc(
            c, "/mcp", sid, "tools/call", {"name": "quick_tailor", "arguments": {}}
        ).json()["result"]
    assert res["isError"] is True
    assert res["content"][0]["text"] == replaced.replaced_message(
        "quick_tailor", served={"scratch_tool"}
    )


@pytest.mark.parametrize("path", ["/mcp", "/mcp/track"])
def test_a_name_never_served_keeps_the_plain_error(client, path):
    sid = session(client, path)
    res = rpc(
        client, path, sid, "tools/call", {"name": "no_such_tool", "arguments": {}}
    ).json()["result"]
    assert res["isError"] is True
    assert res["content"][0]["text"] == "Unknown tool: no_such_tool"


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
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        response = c.post(path, json=INIT, headers=HDR)
        assert response.status_code == 200, response.text
        assert response.json()["result"]["serverInfo"]["version"] == expected


def test_an_unknown_profile_is_404(client):
    assert client.post("/mcp/nope", json=INIT, headers=HDR).status_code == 404


def test_a_stale_session_is_404_so_the_bridge_can_replay(client):
    r = rpc(client, "/mcp", "deadbeef", "tools/list")
    assert r.status_code == 404


def test_sdk_dns_rebinding_protection_is_off():
    """The app's Host/Origin middleware is the one definition (SYSTEM.md §6)."""
    endpoint = mcp_http.McpEndpoint()
    assert endpoint.security.enable_dns_rebinding_protection is False


def test_registered_tools_run_off_the_event_loop_but_module_functions_stay_sync():
    scratch = srv._ServedMCP("offload-test")
    seen = {}

    @scratch.tool()
    def worker_thread() -> dict:
        seen["worker"] = threading.get_ident()
        return {"items": []}

    @scratch.tool()
    async def loop_thread() -> dict:
        seen["loop"] = threading.get_ident()
        return {"items": []}

    with TestClient(asgi_app(mcp_http.McpEndpoint(scratch))) as c:
        sid = session(c)
        for id_, name in enumerate(("worker_thread", "loop_thread"), start=2):
            res = rpc(c, "/mcp", sid, "tools/call", {"name": name}, id_).json()["result"]
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
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        sid = session(c)
        res = rpc(c, "/mcp", sid, "tools/call", {"name": "list_templates"}).json()["result"]
        assert not res["isError"], res
    assert seen == [False]


def test_request_body_larger_than_sdk_default_is_accepted(client):
    sid = session(client)
    response = rpc(client, "/mcp", sid, "ping", {"padding": "x" * (5 * 1024 * 1024)})
    assert response.status_code != 413, response.text


def test_offloading_is_idempotent_and_preserves_async_tools():
    scratch = MCPServer("idempotent-test")

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
    scratch = srv._ServedMCP("context-test")
    monkeypatch.setenv("MAESTRO_CS_MCP_PROFILE", "hunt")

    @scratch.tool()
    def list_templates(ctx: Context) -> dict:
        allow = srv._active_allowed_tools()
        return {
            "profile": srv.CURRENT_PROFILE.get(),
            "allowed": sorted(allow) if allow is not None else None,
            "client": srv._client_label(ctx),
        }

    with TestClient(asgi_app(mcp_http.McpEndpoint(scratch))) as c:
        for id_, profile in enumerate(("templates", "full"), start=2):
            path = f"/mcp/{profile}"
            sid = session(c, path)
            res = rpc(c, path, sid, "tools/call", {"name": "list_templates"}, id_).json()[
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
    sid = session(client, "/mcp/hunt")
    assert rpc(client, "/mcp/apply", sid, "tools/list").status_code == 404
    assert rpc(client, "/mcp/hunt", sid, "tools/list").status_code == 200


def test_lifespan_can_restart_and_forgets_old_sessions():
    asgi = asgi_app(mcp_http.McpEndpoint())
    with TestClient(asgi) as c:
        old_sid = session(c)
        assert rpc(c, "/mcp", old_sid, "tools/list").status_code == 200
    with TestClient(asgi) as c:
        assert rpc(c, "/mcp", old_sid, "tools/list").status_code == 404
        sid = session(c)
        assert rpc(c, "/mcp", sid, "tools/list").status_code == 200


def _scratch_answer(raised: Exception, name: str = "refused") -> dict:
    """What an agent reads when a scratch tool raises `raised` on /mcp."""
    scratch = srv._ServedMCP("error-test")

    def tool() -> str:
        raise raised

    scratch.add_tool(tool, name=name)
    with TestClient(asgi_app(mcp_http.McpEndpoint(scratch))) as c:
        sid = session(c)
        return rpc(c, "/mcp", sid, "tools/call", {"name": name}).json()["result"]


def test_a_backend_refusal_reaches_the_agent_word_for_word():
    """The backstop for a BackendError raised outside _guard (every registered tool has one):
    the agent still reads the backend's words."""
    res = _scratch_answer(BackendError("Maestro writes for this app; use store_cover_letter."))
    assert res["isError"] is True
    assert res["content"][0]["text"] == (
        "Error executing tool refused: Maestro writes for this app; use store_cover_letter."
    )


def test_a_deliberate_tool_error_reads_word_for_word():
    res = _scratch_answer(ToolError("bad input"))
    assert res["isError"] is True
    assert res["content"][0]["text"] == "Error executing tool refused: bad input"


def test_a_crash_reads_the_generic_text_and_keeps_its_traceback_in_the_log(caplog):
    with caplog.at_level(logging.ERROR):
        res = _scratch_answer(ValueError("broken input"), name="broken")
    assert res["isError"] is True
    assert res["content"][0]["text"] == "Error executing tool broken"
    assert "ValueError: broken input" in caplog.text


def test_set_tools_run_on_the_dedicated_limiter():
    """2.x runs sync tools on threads itself, on anyio's default limiter (FastAPI's sync
    endpoints draw on it too); a set's tools take a token from Maestro's own."""
    scratch = srv._ServedMCP("limiter-test")

    @scratch.tool()
    def list_templates() -> dict:
        return {"borrowed": anyio.from_thread.run_sync(
            lambda: mcp_http._LIMITER.get().borrowed_tokens
        )}

    with TestClient(asgi_app(mcp_http.McpEndpoint(scratch))) as c:
        sid = session(c, "/mcp/templates")
        res = rpc(c, "/mcp/templates", sid, "tools/call", {"name": "list_templates"}).json()
    assert not res["result"]["isError"], res
    assert json.loads(res["result"]["content"][0]["text"]) == {"borrowed": 1}


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
    sid = session(client, "/mcp/tailor")
    prompts = rpc(client, "/mcp/tailor", sid, "prompts/list").json()["result"]["prompts"]
    assert [p["name"] for p in prompts] == ["tailor-run"]
    assert prompts[0]["description"] == catalog["tailor-run"]["summary"]


def test_the_full_set_offers_every_playbook(client, catalog):
    sid = session(client, "/mcp")
    prompts = rpc(client, "/mcp", sid, "prompts/list").json()["result"]["prompts"]
    assert [p["name"] for p in prompts] == list(catalog)


def test_a_prompt_is_exactly_the_copy_prompt(client, catalog):
    sid = session(client, "/mcp/tailor")
    got = rpc(client, "/mcp/tailor", sid, "prompts/get", {"name": "tailor-run"}).json()["result"]
    assert got["messages"] == [
        {"role": "user", "content": {"type": "text", "text": catalog["tailor-run"]["prompt"]}}
    ]


def test_a_playbook_from_another_set_is_not_served(client, catalog):
    sid = session(client, "/mcp/tailor")
    res = rpc(client, "/mcp/tailor", sid, "prompts/get", {"name": "job-hunt"}).json()
    assert "error" in res


@pytest.mark.parametrize("mode", ["legacy", "2026-07-28"])
async def test_an_unknown_prompt_reads_its_name_on_both_eras(catalog, mode):
    served = srv.build_set("tailor", cls=mcp_http._ServedSet)
    async with Client(served, mode=mode) as client:
        with pytest.raises(MCPError) as refused:
            await client.get_prompt("job-hunt")
    assert (refused.value.code, refused.value.message) == (0, "Unknown prompt: job-hunt")


@pytest.mark.parametrize("mode", ["legacy", "2026-07-28"])
async def test_a_backend_refusal_behind_the_prompts_reads_its_words_on_both_eras(
    monkeypatch, mode
):
    said = "Backend returned 503: the automations catalog is unavailable"

    def refuse():
        raise BackendError(said, status_code=503)

    monkeypatch.setattr(srv._client, "get_automations", refuse)
    served = srv.build_set("tailor", cls=mcp_http._ServedSet)
    async with Client(served, mode=mode) as client:
        for ask in (client.list_prompts, lambda: client.get_prompt("tailor-run")):
            with pytest.raises(MCPError) as refused:
                await ask()
            assert (refused.value.code, refused.value.message) == (0, said)
