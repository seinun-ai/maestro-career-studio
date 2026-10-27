"""Streamable HTTP contract, using only in-process ASGI requests."""

import asyncio
import contextlib
import inspect
import json
import logging
import subprocess
import sys
import threading
from pathlib import Path

import anyio.from_thread
import pytest
from mcp.server.caching import CACHEABLE_METHODS, CacheHint
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from opentelemetry.trace import INVALID_SPAN
from starlette.testclient import TestClient

from mcp_server import http as mcp_http
from mcp_server import server as srv
from mcp_server.client import BackendError
from mcp_server.profiles import PROFILE_ALLOWLISTS, allowed_tools
from mcp_server.tests._wire import (
    HDR, INIT, asgi_app, modern_rpc, rpc, serve_catalog, session, set_path,
)


@pytest.fixture
def client():
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        yield c


@pytest.mark.parametrize("profile", ["full", "profile", "hunt", "tailor", "apply", "track", "templates"])
def test_each_profile_lists_exactly_its_allowlist_in_registration_order(client, profile):
    path = set_path(profile)
    sid = session(client, path)
    names = [t["name"] for t in rpc(client, path, sid, "tools/list").json()["result"]["tools"]]
    assert names == srv.list_registered_tool_names(profile)
    allow = allowed_tools(profile)
    assert set(names) == (
        set(srv.list_registered_tool_names("full")) if allow is None else set(allow))


def test_each_set_is_its_own_server_holding_only_its_tools():
    served = mcp_http.McpEndpoint().servers["hunt"]
    assert isinstance(served, mcp_http._ServedSet)
    assert {t.name for t in served._tool_manager.list_tools()} == set(allowed_tools("hunt"))


def _kinds(server: MCPServer) -> list[type]:
    return [type(m) for m in server.middleware]


def test_every_server_traces_nothing_and_lets_no_client_cache_an_answer():
    """A configured Langfuse is OpenTelemetry-based: it sees model calls, never the SDK's span
    per MCP message (tool names, crash text). Only tracing goes; the SDK's other middleware stays.
    The registry is served directly in tests, so it is configured the same way."""
    # Imported here, not taken from server.py: if the SDK moves it, this fails in CI while the
    # app (server._SdkTracing None, dropped by name) still starts.
    from mcp.server._otel import OpenTelemetryMiddleware as tracing

    assert srv._SdkTracing is tracing
    sdk = _kinds(MCPServer("plain"))
    assert tracing in sdk  # what the SDK installs on its own
    kept = [k for k in sdk if k is not tracing]
    no_caching = {m: CacheHint(ttl_ms=0, scope="private") for m in CACHEABLE_METHODS}
    sets = mcp_http.McpEndpoint().servers.values()
    for served in (srv.mcp, *sets, *(srv.build_set(p) for p in PROFILE_ALLOWLISTS)):
        assert _kinds(served) == kept
        assert served._lowlevel_server.cache_hints == no_caching


def test_the_app_starts_and_drops_tracing_by_name_once_the_sdk_moves_its_class():
    """A later 2.x without mcp.server._otel.OpenTelemetryMiddleware: server.py still imports and
    every server still drops the SDK's tracing, matched by its class name."""
    script = (
        "import mcp.server._otel as otel; del otel.OpenTelemetryMiddleware\n"
        "import mcp_server.http as h, mcp_server.server as s\n"
        "print(s._SdkTracing, *sorted({type(m).__name__ for m in s.mcp.middleware}),"
        " *sorted({type(m).__name__ for m in h.McpEndpoint().servers['hunt'].middleware}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    kept = sorted({type(m).__name__ for m in MCPServer("plain").middleware} - {
        "OpenTelemetryMiddleware"})
    assert out == ["None", *kept, *kept]


class _Spans:
    """Stands in for the SDK's tracer: records each span it is asked to open."""

    def __init__(self) -> None:
        self.names: list[str] = []

    @contextlib.contextmanager
    def start_as_current_span(self, name, **_kwargs):
        self.names.append(name)
        yield INVALID_SPAN


def test_no_mcp_message_opens_a_span_on_either_era(monkeypatch, catalog):
    from mcp.server._otel import OpenTelemetryMiddleware
    from mcp.shared import _otel  # where the SDK opens each of its spans

    spans = _Spans()
    monkeypatch.setattr(_otel, "_tracer", spans)
    endpoint = mcp_http.McpEndpoint()
    # The control: tracing put back on one set shows the recorder sees the SDK's spans, so an
    # SDK that opened them elsewhere could not pass this test by recording nothing.
    endpoint.servers["track"].middleware.insert(0, OpenTelemetryMiddleware())
    removed = {"name": "explore_top_skills", "arguments": {}}
    with TestClient(asgi_app(endpoint)) as c:
        for path in ("/mcp/hunt", "/mcp/track"):
            assert spans.names == []
            sid = session(c, path)
            for method, params in (("tools/list", {}), ("prompts/list", {}), ("tools/call", removed)):
                assert rpc(c, path, sid, method, params).status_code == 200
                assert modern_rpc(c, path, method, params).status_code == 200
    assert spans.names.count("tools/call explore_top_skills") == 2  # the control, once per era
    assert "initialize" in spans.names


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


def _lifespan_runs(endpoint, count=2):
    """Each lifespan run's managers, by set."""
    runs = []
    for _ in range(count):
        with TestClient(asgi_app(endpoint)):
            runs.append(dict(endpoint.managers))
    return runs


def _settings_by_set(managers):
    return {p: (m.app, m.json_response, m.stateless,
                m.security_settings.enable_dns_rebinding_protection,
                m.session_idle_timeout, m.max_request_body_size) for p, m in managers.items()}


def test_each_lifespan_run_gives_every_set_a_fresh_manager_with_the_same_settings():
    endpoint = mcp_http.McpEndpoint()
    first, second = _lifespan_runs(endpoint)
    # JSON answers, the stateful 2025 path, the app's own Host check, a 6-hour idle, 16 MiB bodies.
    expected = {p: (served._lowlevel_server, True, False, False, 6 * 60 * 60, 16 * 1024 * 1024)
                for p, served in endpoint.servers.items()}
    assert _settings_by_set(first) == expected == _settings_by_set(second)
    assert not set(map(id, first.values())) & set(map(id, second.values()))


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


@pytest.fixture
def catalog(monkeypatch):
    return serve_catalog(monkeypatch)


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
