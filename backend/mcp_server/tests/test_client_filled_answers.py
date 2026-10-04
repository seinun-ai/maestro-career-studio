"""record_filled_answers' request shape, and the client's own EEO strip on the final review."""

import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"
FIELDS = [{"question": "First name", "answer": "Ada", "source": "profile"}]


@respx.mock
def test_record_filled_answers_posts_one_agent_page_run():
    route = respx.post(f"{BASE}/api/jobs/j1/filled-answers").mock(
        return_value=httpx.Response(201, json={"id": "r1", "flag_count": 0, "flags": []}))
    BackendClient(BASE).record_filled_answers("j1", FIELDS, step="2")
    assert json.loads(route.calls.last.request.read()) == {
        "channel": "agent", "fields": FIELDS, "step": "2"}


@respx.mock
def test_the_final_review_never_hands_an_agent_an_eeo_value():
    respx.get(f"{BASE}/api/proposals/p1/final-review").mock(return_value=httpx.Response(200, json={
        "flags": [{"question": "Gender", "eeo": True, "answer": "Female", "flags": []},
                  {"question": "Relocate?", "eeo": False, "answer": "No", "flags": []}]}))
    review = BackendClient(BASE).get_final_review("p1")
    assert ["answer" in flag for flag in review["flags"]] == [False, True]


def test_no_mcp_path_reads_the_receipt_endpoint():
    """GET /api/jobs/{id}/filled-answers serves EEO values to the web UI; the MCP server only
    ever POSTs to it (SYSTEM.md {#inv-filled-answers-local})."""
    import re
    from pathlib import Path

    import mcp_server

    pattern = re.compile(r'_request\(\s*"(\w+)",\s*f?"[^"]*filled-answers')
    calls = [call for source in Path(mcp_server.__file__).parent.glob("*.py")
             for call in pattern.findall(source.read_text())]
    assert calls == ["POST"]
