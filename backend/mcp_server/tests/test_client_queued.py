"""A write the backend queues for the other copy reaches the agent as its own sentence."""

import json

import httpx
import respx
from mcp.shared.memory import create_connected_server_and_client_session

import mcp_server.server as srv
from mcp_server.client import BackendClient

QUEUED = {"queued": True, "detail": "Sent at the next sync."}


async def test_a_queued_transition_passes_the_202_text_through_unchanged(monkeypatch):
    monkeypatch.setattr(srv, "_client", BackendClient("http://test-backend"))
    with respx.mock(assert_all_called=False) as mock:
        mock.patch("http://test-backend/api/proposals/p1").mock(
            return_value=httpx.Response(202, json=QUEUED))
        async with create_connected_server_and_client_session(srv.mcp) as session:
            result = await session.call_tool("record_consent", {
                "proposal_id": "p1", "action": "rejected", "channel": "mcp", "note": "no"})
    assert not result.isError, result.content
    assert json.loads(result.content[0].text) == QUEUED
