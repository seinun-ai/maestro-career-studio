"""propose_application: request shape and who-filed-it provenance."""

import json

import httpx
import pytest
import respx
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Implementation

import mcp_server.server as srv
from app.write_origin import decode_detail
from mcp_server.client import BackendClient, _origin_headers

BASE = "http://test-backend"


@respx.mock
def test_propose_application_names_the_client_in_the_origin_headers():
    route = respx.post(f"{BASE}/api/proposals").mock(
        return_value=httpx.Response(201, json={"id": "p1"})
    )
    BackendClient(BASE).propose_application(
        "j1", plan={"summary": "fit"}, origin_detail="claude-ai"
    )
    request = route.calls.last.request
    # The filer travels in headers, never the body: the body's proposed_by is
    # the web app's "you", which an agent must not be able to send.
    assert json.loads(request.read()) == {"job_id": "j1", "plan": {"summary": "fit"}}
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "claude-ai"


@respx.mock
def test_an_unnamed_client_still_files_as_mcp_never_as_you():
    route = respx.post(f"{BASE}/api/proposals").mock(
        return_value=httpx.Response(201, json={"id": "p1"})
    )
    BackendClient(BASE).propose_application("j1")
    request = route.calls.last.request
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert "X-Maestro-CS-Origin-Detail" not in request.headers
    assert "proposed_by" not in json.loads(request.read())


_LONG = "x" * 5000


@pytest.mark.parametrize(
    ("declared", "filed_as"),
    [
        ("claude-ai", "claude-ai"),
        ("Café Agent", "Café Agent"),
        ("クロード", "クロード"),
        ("Bad\r\nX-Injected: 1\x00", "BadX-Injected: 1"),
        (_LONG, _LONG[:120]),
        ("ク" * 500, "ク" * 120),
    ],
    ids=["ascii", "latin", "japanese", "control-chars", "long-ascii", "long-japanese"],
)
async def test_any_client_name_can_file_a_proposal(monkeypatch, declared, filed_as):
    """End to end through the in-memory MCP session: an HTTP header value must
    be ASCII, so a raw non-ASCII clientInfo.name used to fail the tool call with
    UnicodeEncodeError. The name travels percent-encoded, without control
    characters, bounded, and the backend decodes it back to the real name."""
    monkeypatch.delenv("MAESTRO_CS_MCP_CLIENT", raising=False)
    monkeypatch.delenv("CAREER_STUDIO_MCP_CLIENT", raising=False)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(url__regex=r".*/api/proposals$").mock(
            return_value=httpx.Response(201, json={"id": "p1"})
        )
        async with create_connected_server_and_client_session(
            srv.mcp, client_info=Implementation(name=declared, version="0.1.0")
        ) as session:
            result = await session.call_tool("propose_application", {"job_id": "j1"})
    assert not result.isError, result.content
    sent = route.calls.last.request.headers["X-Maestro-CS-Origin-Detail"]
    assert sent.isascii() and sent.isprintable() and len(sent) <= 120 * 9
    assert decode_detail(sent) == filed_as


def test_an_ascii_client_name_travels_unchanged():
    # KB writes' stored origin_detail must not change for the names already in use.
    assert _origin_headers("Claude Desktop (beta) v1.2")["X-Maestro-CS-Origin-Detail"] == (
        "Claude Desktop (beta) v1.2"
    )
