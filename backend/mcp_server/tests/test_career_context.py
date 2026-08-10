"""MCP get_career_context: read-only career grounding for social posts/outreach."""

import httpx
import respx

from mcp_server import server as srv
from mcp_server.client import BackendClient


@respx.mock
def test_client_get_career_context_hits_kb_context():
    route = respx.get("http://backend.test/api/kb/context").mock(
        return_value=httpx.Response(
            200, json={"resume": {"summary": "DS"}, "memory": "IDENTITY: ..."}
        )
    )
    client = BackendClient("http://backend.test")
    out = client.get_career_context()
    assert route.called
    assert out["memory"].startswith("IDENTITY")


def test_get_career_context_tool_registered_and_grounded():
    assert "get_career_context" in {t.name for t in srv.mcp._tool_manager.list_tools()}
    doc = " ".join((srv.get_career_context.__doc__ or "").lower().split())
    assert "never invent" in doc  # grounding rule travels in the docstring
    assert "delete" not in "get_career_context"


def test_get_career_context_tool_calls_client(monkeypatch):
    monkeypatch.setattr(
        srv._client, "get_career_context", lambda: {"resume": {}, "memory": "m"}
    )
    assert srv.get_career_context() == {"resume": {}, "memory": "m"}
