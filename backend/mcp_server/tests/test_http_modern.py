"""Clients on the 2026-07-28 revision: no handshake and no session, each request naming its
version, client and capabilities in `_meta`. They read what a 2025 client reads, word for word:
the golden record's answer, or the 2025 path's own."""

import json

import anyio
import pytest
from mcp import Client, MCPError
from mcp.types import SERVER_INFO_META_KEY
from starlette.testclient import TestClient

from mcp_server import http as mcp_http
from mcp_server import orientation, replaced
from mcp_server import server as srv
from mcp_server.client import BackendError
from mcp_server.profiles import PROFILE_ALLOWLISTS, allowed_tools
from mcp_server.tests import test_wire_golden as golden
from mcp_server.tests._wire import (
    HDR, INIT, MODERN, asgi_app, context_registry, modern_rpc, normalise_record,
    normalise_response, rpc, serve_catalog, session,
)

PROFILES = list(PROFILE_ALLOWLISTS)


@pytest.fixture
def client():
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        yield c


@pytest.fixture
def catalog(monkeypatch):
    return serve_catalog(monkeypatch)


def _path(profile: str) -> str:
    return "/mcp" if profile == "full" else f"/mcp/{profile}"


def _modern(c, path, method, params=None, **kwargs):
    """modern_rpc's answer, checked to come from the 2026-07-28 path: a 200 with no session
    (the stateful 2025 path refuses any session-less request but initialize)."""
    response = modern_rpc(c, path, method, params, **kwargs)
    assert response.status_code == 200, response.text
    assert "mcp-session-id" not in response.headers
    return response.json()


def _both_eras(c, path, method, params=None):
    """One request's answer on the 2025 path, then on the 2026-07-28 path, both normalised."""
    legacy = rpc(c, path, session(c, path), method, params)
    assert legacy.status_code == 200, legacy.text
    return normalise_response(legacy.json()), normalise_response(_modern(c, path, method, params))


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("app_version, expected", [("0.9.0", "0.9.0"), (None, "dev")])
def test_discover_gives_the_sets_instructions_and_maestro_version(
    monkeypatch, profile, app_version, expected
):
    if app_version is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", app_version)
    with TestClient(asgi_app(mcp_http.McpEndpoint())) as c:
        result = _modern(c, _path(profile), "server/discover")["result"]
    assert result["instructions"] == orientation.instructions_for(profile)
    # The revision moves serverInfo out of the handshake into each result's _meta.
    assert result["_meta"][SERVER_INFO_META_KEY] == {
        "name": "maestro-career-studio", "version": expected,
    }


@pytest.mark.parametrize("profile", PROFILES)
def test_discover_offers_no_list_subscriptions_as_initialize_does(client, profile):
    """The owner's call: no subscriptions/listen. On 2026-07-28 the SDK derives listChanged and
    subscribe from whether that method is served."""
    path = _path(profile)
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
    """Every set and the registry (None) refuse subscriptions/listen. In process, so a server
    that did serve it fails within the bound instead of streaming forever."""
    served = srv.mcp if profile is None else srv.build_set(profile, cls=mcp_http._ServedSet)
    async with Client(served, mode=MODERN) as client:
        with anyio.fail_after(5), pytest.raises(MCPError):
            async with client.listen(tools_list_changed=True):
                pass


@pytest.mark.parametrize("profile", PROFILES)
def test_a_set_lists_the_same_tools_and_prompts_as_on_the_2025_path(client, catalog, profile):
    answers = {m: _both_eras(client, _path(profile), m) for m in ("tools/list", "prompts/list")}
    for method, (legacy, modern) in answers.items():
        assert modern == legacy, method
    _, tools = answers["tools/list"]
    assert [t["name"] for t in tools["result"]["tools"]] == srv.list_registered_tool_names(profile)


@pytest.fixture(scope="module")
def golden_record():
    entries = json.loads(golden.FIXTURE.read_text(encoding="utf-8"))
    return normalise_record({**entries, **golden.EXPECTED_CHANGES})


class _ModernWire:
    """The golden record's wire on the 2026-07-28 revision: each request on its own."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def ask(self, path, method, params=None):
        return _modern(self.client, path, method, params)


@pytest.mark.parametrize("call", golden.CALLS, ids=lambda call: call.entry)
def test_a_golden_call_reads_its_recorded_answer(client, monkeypatch, golden_record, call):
    """Every recorded call: each answer shape, each refusal kind (a removed name, a removed
    argument, a tool outside the set, the schema, the backend's words, CLEAR_TAKES_A_LIST)
    and the crash."""
    reached = []
    monkeypatch.setattr(srv._client, "_send", lambda method, path, **_: reached.append(path))
    got = golden._called(_ModernWire(client), call)
    assert reached == []
    assert normalise_response(got) == golden_record[f"tools/call {call.entry}"]


@pytest.mark.parametrize("profile", PROFILES)
def test_a_removed_name_reads_the_same_on_every_set(client, profile):
    path = _path(profile)
    for name in sorted(replaced.REPLACED_TOOLS):
        legacy, modern = _both_eras(client, path, "tools/call", {"name": name, "arguments": {}})
        assert modern == legacy, name
        expected = replaced.replaced_message(name, served=allowed_tools(profile))
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


def _seen(c, path, **kwargs):
    """What context_registry's list_templates saw on a 2026-07-28 call."""
    call = {"name": "list_templates", "arguments": {}}
    res = _modern(c, path, "tools/call", call, **kwargs)["result"]
    assert not res["isError"], res
    return json.loads(res["content"][0]["text"])


def test_a_tool_sees_its_set_and_the_client_its_request_names(monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_MCP_PROFILE", "hunt")  # the request's set wins over this
    monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", "env-client")  # and the named client over this
    with TestClient(asgi_app(mcp_http.McpEndpoint(context_registry()))) as c:
        for profile in ("templates", "full"):
            assert _seen(c, _path(profile)) == {
                "profile": profile,
                "allowed": sorted(allowed_tools(profile)) if profile != "full" else None,
                "client": "pytest-client",
                "protocol": MODERN,
            }
    assert srv.CURRENT_PROFILE.get() is None


@pytest.mark.parametrize("env, label", [("env-client", "env-client"), (None, None)])
def test_a_request_naming_no_client_takes_the_env_label_then_none(monkeypatch, env, label):
    if env is None:
        monkeypatch.delenv("MAESTRO_CS_MCP_CLIENT", raising=False)
    else:
        monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", env)
    with TestClient(asgi_app(mcp_http.McpEndpoint(context_registry()))) as c:
        seen = _seen(c, "/mcp/templates", client_info=None)
    assert (seen["client"], seen["protocol"]) == (label, MODERN)


def test_a_15_mib_body_reaches_the_tool():
    """A 10 MB evidence upload grows by 4/3 once base64-encoded in a tool's arguments."""
    scratch = srv._ServedMCP("body-test")

    @scratch.tool()
    def measure(padding: str) -> dict:
        return {"length": len(padding)}

    padding = "x" * (15 * 1024 * 1024)
    call = {"name": "measure", "arguments": {"padding": padding}}
    with TestClient(asgi_app(mcp_http.McpEndpoint(scratch))) as c:
        res = _modern(c, "/mcp", "tools/call", call)["result"]
    assert json.loads(res["content"][0]["text"]) == {"length": len(padding)}


def test_an_unknown_set_is_404(client):
    assert modern_rpc(client, "/mcp/nope", "tools/list").status_code == 404


def test_no_answer_opens_a_session():
    endpoint = mcp_http.McpEndpoint()
    with TestClient(asgi_app(endpoint)) as c:
        for method in ("server/discover", "tools/list"):
            _modern(c, "/mcp/hunt", method)  # no Mcp-Session-Id header
        assert endpoint.managers["hunt"]._server_instances == {}  # and none held for one
