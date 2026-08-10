import httpx
import respx

from mcp_server import server as srv
from mcp_server.client import BackendClient


@respx.mock
def test_client_get_career_export_reads_markdown_text():
    route = respx.get("http://backend.test/api/exports/career").mock(
        return_value=httpx.Response(200, text="# Career Profile\n", headers={"content-type": "text/markdown"})
    )
    result = BackendClient("http://backend.test").get_career_export()
    assert route.called
    assert result == "# Career Profile\n"


def test_get_career_export_tool_registered_and_read_only():
    assert "get_career_export" in {tool.name for tool in srv.mcp._tool_manager.list_tools()}
    doc = " ".join((srv.get_career_export.__doc__ or "").lower().split())
    assert "exact" in doc
    assert "markdown" in doc
    assert "read-only" in doc


def test_get_career_export_tool_calls_client(monkeypatch):
    monkeypatch.setattr(srv._client, "get_career_export", lambda: "# Career Profile\n")
    assert srv.get_career_export() == "# Career Profile\n"
