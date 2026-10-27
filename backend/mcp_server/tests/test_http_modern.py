"""Both protocol eras side by side. A 2026-07-28 client has no handshake and no session: each
request names its version, client and capabilities in `_meta`. It reads what a 2025 client
reads, word for word: the golden record's answer, or the 2025 path's own."""

import json

import anyio
import pytest
from mcp import Client, MCPError
from mcp.server.mcpserver import Context
from mcp.types import METHOD_NOT_FOUND, SERVER_INFO_META_KEY
from starlette.testclient import TestClient

from mcp_server import http as mcp_http
from mcp_server import orientation, replaced
from mcp_server import server as srv
from mcp_server.client import BackendError
from mcp_server.profiles import PROFILE_ALLOWLISTS, allowed_tools
from mcp_server.tests._golden_cases import CALLS, REQUESTS, call_case, expected_record
from mcp_server.tests._wire import (
    HDR, INIT, MODERN, asgi_app, modern_rpc, normalise_response, rpc, serve_catalog, session,
    set_path,
)

PROFILES = list(PROFILE_ALLOWLISTS)
LEGACY = INIT["params"]["protocolVersion"]
ERAS = (LEGACY, MODERN)


@pytest.fixture
def client():
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        yield c


@pytest.fixture
def catalog(monkeypatch):
    return serve_catalog(monkeypatch)


def _modern(c, path, method, params=None, **kwargs):
    """modern_rpc's answer, checked to come from the 2026-07-28 path: a 200 with no session
    (the stateful 2025 path refuses any session-less request but initialize)."""
    response = modern_rpc(c, path, method, params, **kwargs)
    assert response.status_code == 200, response.text
    assert "mcp-session-id" not in response.headers
    return response.json()


def _ask(era, c, path, method, params=None):
    """One request's answer on `era`'s path: on a fresh 2025 session, or on its own."""
    if era == MODERN:
        return _modern(c, path, method, params)
    response = rpc(c, path, session(c, path), method, params)
    assert response.status_code == 200, response.text
    return response.json()


def _both_eras(c, path, method, params=None):
    """One request's answer on the 2025 path, then on the 2026-07-28 path, both normalised."""
    legacy, modern = (normalise_response(_ask(era, c, path, method, params)) for era in ERAS)
    return legacy, modern


def _introduction(era, c, path):
    """The set's instructions and serverInfo, as a client first learns them: from 2025's
    initialize, or from 2026-07-28's server/discover, which carries serverInfo in _meta."""
    if era == MODERN:
        result = _modern(c, path, "server/discover")["result"]
        return result["instructions"], result["_meta"][SERVER_INFO_META_KEY]
    response = c.post(path, json=INIT, headers=HDR)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    return result["instructions"], result["serverInfo"]


@pytest.mark.parametrize("era", ERAS)
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("app_version, expected", [("0.9.0", "0.9.0"), (None, "dev")])
def test_a_client_learns_the_sets_instructions_and_maestro_version(
    monkeypatch, era, profile, app_version, expected
):
    if app_version is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", app_version)
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        instructions, server_info = _introduction(era, c, set_path(profile))
    assert instructions == orientation.instructions_for(profile)
    assert server_info == {"name": "maestro-career-studio", "version": expected}


@pytest.mark.parametrize("profile", PROFILES)
def test_discover_offers_no_list_subscriptions_as_initialize_does(client, profile):
    """The owner's call: no subscriptions/listen. On 2026-07-28 the SDK derives listChanged and
    subscribe from whether that method is served."""
    path = set_path(profile)
    discovered = _modern(client, path, "server/discover")["result"]["capabilities"]
    initialized = client.post(path, json=INIT, headers=HDR).json()["result"]["capabilities"]
    assert normalise_response(discovered) == normalise_response(initialized)
    flags = (
        discovered["tools"]["listChanged"], discovered["prompts"]["listChanged"],
        discovered["resources"]["listChanged"], discovered["resources"]["subscribe"],
    )
    assert flags == (False, False, False, False)


@pytest.mark.parametrize("profile", [None, *PROFILES])
async def test_no_server_opens_a_listen_stream(profile):
    """Every set and the registry (None) leave subscriptions/listen unserved. In process, so a
    server that did serve it fails within the bound instead of streaming forever."""
    served = srv.mcp if profile is None else srv.build_set(profile, cls=mcp_http._ServedSet)
    async with Client(served, mode=MODERN) as client:
        with anyio.fail_after(5), pytest.raises(MCPError) as refused:
            async with client.listen(tools_list_changed=True):
                pass
    assert refused.value.code == METHOD_NOT_FOUND


@pytest.mark.parametrize("profile", PROFILES)
def test_a_set_lists_the_same_tools_and_prompts_as_on_the_2025_path(client, catalog, profile):
    answers = {m: _both_eras(client, set_path(profile), m) for m in ("tools/list", "prompts/list")}
    for method, (legacy, modern) in answers.items():
        assert modern == legacy, method
    _, tools = answers["tools/list"]
    assert [t["name"] for t in tools["result"]["tools"]] == srv.list_registered_tool_names(profile)


@pytest.mark.parametrize("profile", PROFILES)
def test_a_2026_client_is_told_to_keep_no_list(client, catalog, profile):
    for method in ("tools/list", "prompts/list"):
        result = _modern(client, set_path(profile), method)["result"]
        assert (result["ttlMs"], result["cacheScope"]) == (0, "private"), method


@pytest.fixture(scope="module")
def golden_record():
    return expected_record()


class _ModernWire:
    """The golden record's wire on the 2026-07-28 revision: each request on its own."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def ask(self, path, method, params=None):
        return _modern(self.client, path, method, params)


@pytest.mark.parametrize("asked", REQUESTS, ids=lambda asked: asked.method)
def test_a_golden_request_reads_its_recorded_answer(client, golden_record, asked):
    """The resources lists and an unknown method: the record's 2025 answer, with Method not
    found as a 404 on this path."""
    response = modern_rpc(client, asked.path, asked.method)
    assert response.status_code == asked.modern_status, response.text
    assert normalise_response(response.json()) == golden_record[f"{asked.method} {asked.path}"]


@pytest.mark.parametrize("call", CALLS, ids=lambda call: call.entry)
def test_a_golden_call_reads_its_recorded_answer(client, monkeypatch, golden_record, call):
    """Every recorded call: each answer shape, each refusal kind (a removed name, a removed
    argument, a tool outside the set, the schema, the backend's words, CLEAR_TAKES_A_LIST)
    and the crash."""
    reached = []
    monkeypatch.setattr(srv._client, "_send", lambda method, path, **_: reached.append(path))
    got = call_case(_ModernWire(client), call)
    assert reached == []
    assert normalise_response(got) == golden_record[f"tools/call {call.entry}"]


@pytest.mark.parametrize("profile", PROFILES)
def test_a_removed_name_answers_with_its_replacement_on_every_set(client, profile):
    path = set_path(profile)
    for name in sorted(replaced.REPLACED_TOOLS):
        legacy, modern = _both_eras(client, path, "tools/call", {"name": name, "arguments": {}})
        assert modern == legacy, name
        expected = replaced.replaced_message(name, served=allowed_tools(profile))
        assert modern["result"]["isError"] is True, name
        assert modern["result"]["content"][0]["text"] == expected, name


@pytest.mark.parametrize("name", ["job-hunt", "no-such-playbook"])
def test_a_prompt_the_set_lacks_reads_the_same_refusal(client, catalog, name):
    """job-hunt is another set's playbook; the other is no playbook at all."""
    legacy, modern = _both_eras(client, "/mcp/tailor", "prompts/get", {"name": name})
    assert modern == legacy == {"error": {"code": 0, "message": f"Unknown prompt: {name}"}}


@pytest.mark.parametrize(
    "method, params", [("prompts/list", {}), ("prompts/get", {"name": "tailor-run"})]
)
def test_a_backend_refusal_behind_the_prompts_reads_the_same_words(
    client, monkeypatch, method, params
):
    said = "Backend returned 503: the automations catalog is unavailable"

    def refuse():
        raise BackendError(said, status_code=503)

    monkeypatch.setattr(srv._client, "get_automations", refuse)
    legacy, modern = _both_eras(client, "/mcp/tailor", method, params)
    assert modern == legacy == {"error": {"code": 0, "message": said}}


def _context_registry() -> srv._ServedMCP:
    """A registry whose one tool, list_templates (the templates and full sets serve it), answers
    what its call sees: the set, that set's tools, the client's label and the protocol version."""
    scratch = srv._ServedMCP("context-test")

    @scratch.tool()
    def list_templates(ctx: Context) -> dict:
        allow = srv._active_allowed_tools()
        return {
            "profile": srv.CURRENT_PROFILE.get(),
            "allowed": sorted(allow) if allow is not None else None,
            "client": srv._client_label(ctx),
            "protocol": ctx.protocol_version,
        }

    return scratch


_LOOK = {"name": "list_templates", "arguments": {}}


def _seen(answer):
    """What _context_registry's list_templates saw, from its tools/call answer."""
    res = answer["result"]
    assert not res["isError"], res
    return json.loads(res["content"][0]["text"])


@pytest.mark.parametrize("era", ERAS)
def test_a_tool_sees_its_set_and_the_client_the_request_names(monkeypatch, era):
    """The client named at initialize (2025) or in the request's _meta (2026-07-28)."""
    monkeypatch.setenv("MAESTRO_CS_MCP_PROFILE", "hunt")  # the request's set wins over this
    monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", "env-client")  # and the named client over this
    with TestClient(asgi_app(mcp_http.McpEndpoint(_context_registry()))) as c:
        for profile in ("templates", "full"):
            assert _seen(_ask(era, c, set_path(profile), "tools/call", _LOOK)) == {
                "profile": profile,
                "allowed": sorted(allowed_tools(profile)) if profile != "full" else None,
                "client": "pytest-client",
                "protocol": era,
            }
    assert srv.CURRENT_PROFILE.get() is None


@pytest.mark.parametrize("env, label", [("env-client", "env-client"), (None, None)])
def test_a_request_naming_no_client_takes_the_env_label_then_none(monkeypatch, env, label):
    if env is None:
        monkeypatch.delenv("MAESTRO_CS_MCP_CLIENT", raising=False)
    else:
        monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", env)
    with TestClient(asgi_app(mcp_http.McpEndpoint(_context_registry()))) as c:
        seen = _seen(_modern(c, "/mcp/templates", "tools/call", _LOOK, client_info=None))
    assert (seen["client"], seen["protocol"]) == (label, MODERN)


@pytest.mark.parametrize("era", ERAS)
def test_a_15_mib_body_reaches_the_tool(era):
    """A 10 MB evidence upload grows by 4/3 once base64-encoded in a tool's arguments, past the
    SDK's 4 MiB default."""
    scratch = srv._ServedMCP("body-test")

    @scratch.tool()
    def measure(padding: str) -> dict:
        return {"length": len(padding)}

    padding = "x" * (15 * 1024 * 1024)
    call = {"name": "measure", "arguments": {"padding": padding}}
    with TestClient(asgi_app(mcp_http.McpEndpoint(scratch))) as c:
        res = _ask(era, c, "/mcp", "tools/call", call)["result"]
    assert json.loads(res["content"][0]["text"]) == {"length": len(padding)}


@pytest.mark.parametrize(
    "first_request",
    [
        pytest.param(lambda c, path: c.post(path, json=INIT, headers=HDR), id=LEGACY),
        pytest.param(lambda c, path: modern_rpc(c, path, "tools/list"), id=MODERN),
    ],
)
def test_an_unknown_set_is_404(client, first_request):
    assert first_request(client, "/mcp/nope").status_code == 404


def test_a_2026_request_opens_no_session():
    endpoint = mcp_http.McpEndpoint()
    with TestClient(asgi_app(endpoint)) as c:
        for method in ("server/discover", "tools/list"):
            _modern(c, "/mcp/hunt", method)  # no Mcp-Session-Id header
        assert endpoint.managers["hunt"]._server_instances == {}  # and none held for one
        session(c, "/mcp/hunt")  # the control: a 2025 client's session is held
        assert len(endpoint.managers["hunt"]._server_instances) == 1
