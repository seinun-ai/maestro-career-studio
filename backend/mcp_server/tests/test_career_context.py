"""MCP get_career_context: read-only career grounding, as JSON or as the portable career.md."""

import httpx
import respx

from mcp_server import server as srv
from mcp_server.client import BackendClient


@respx.mock
def test_client_get_career_context_hits_kb_context():
    route = respx.get("http://backend.test/api/kb/context").mock(
        return_value=httpx.Response(
            200, json={"resume": {"summary": "Nurse"}, "memory": "IDENTITY: ..."}
        )
    )
    client = BackendClient("http://backend.test")
    out = client.get_career_context()
    assert route.called
    assert out["memory"].startswith("IDENTITY")


@respx.mock
def test_client_markdown_format_reads_the_career_export_text_unchanged():
    kb = respx.get("http://backend.test/api/kb/context").mock(
        return_value=httpx.Response(200, json={})
    )
    export = respx.get("http://backend.test/api/exports/career").mock(
        return_value=httpx.Response(
            200, text="# Career Profile\n", headers={"content-type": "text/markdown"}
        )
    )
    out = BackendClient("http://backend.test").get_career_context(format="markdown")
    assert out == "# Career Profile\n"
    assert export.called and not kb.called


def test_get_career_context_tool_registered_and_grounded():
    assert "get_career_context" in {t.name for t in srv.mcp._tool_manager.list_tools()}
    doc = " ".join((srv.get_career_context.__doc__ or "").lower().split())
    assert "never invent" in doc  # grounding rule travels in the docstring
    assert "career.md" in doc and "exact" in doc  # the markdown format's promise
    assert "delete" not in "get_career_context"


async def test_get_career_context_format_is_json_or_markdown_and_export_is_gone():
    from mcp_server.profiles import PROFILE_ALLOWLISTS

    tools = {t.name: t for t in await srv.mcp.list_tools()}
    fmt = tools["get_career_context"].input_schema["properties"]["format"]
    assert fmt["enum"] == ["json", "markdown"] and fmt["default"] == "json"
    assert tools["get_career_context"].annotations.read_only_hint is True
    assert "get_career_export" not in tools
    assert all("get_career_export" not in allow for allow in PROFILE_ALLOWLISTS.values() if allow)


def test_get_career_context_tool_passes_the_format(monkeypatch):
    seen = []

    def fake(format="json"):
        seen.append(format)
        return {"resume": {}, "memory": "m"} if format == "json" else "# Career Profile\n"

    monkeypatch.setattr(srv._client, "get_career_context", fake)
    assert srv.get_career_context() == {"resume": {}, "memory": "m"}
    assert srv.get_career_context(format="markdown") == "# Career Profile\n"
    assert seen == ["json", "markdown"]
