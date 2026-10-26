"""Every request the MCP client sends says it came from an agent app (design 2026-10-26): the
backend reads the mark to decide who writes (app/agent_writer.py)."""

import httpx
import pytest
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"
ORIGIN = "X-Maestro-CS-Origin"


@pytest.mark.parametrize(
    ("method", "path", "call"),
    [
        ("GET", "/api/jobs/j1/detail", lambda c: c.get_job("j1")),
        ("POST", "/api/qa", lambda c: c.generate_cover_letter("a1", "balanced")),
        ("POST", "/api/resume-lint/base/data_analyst/run",
         lambda c: c.run_health_check("base", "data_analyst")),
        ("POST", "/api/tailoring-sessions",
         lambda c: c.create_tailoring_session("j1", "data_analyst", enrich=False)),
        ("POST", "/api/tailoring-sessions/s1/tailor", lambda c: c.tailor_session("s1")),
    ],
    ids=["get_job", "generate_cover_letter", "run_health_check", "create_tailoring_session",
         "tailor_session"],
)
def test_every_request_says_it_came_from_an_agent_app(method, path, call):
    with respx.mock:
        route = respx.route(method=method, url=f"{BASE}{path}").mock(
            return_value=httpx.Response(200, json={})
        )
        call(BackendClient(BASE))
    assert route.calls.last.request.headers.get_list(ORIGIN) == ["mcp"]


def test_a_call_that_names_its_client_sends_one_origin_and_the_name():
    with respx.mock:
        route = respx.post(f"{BASE}/api/kb/entities/e1/drafts").mock(
            return_value=httpx.Response(200, json={"entity_id": "e1", "point_ids": []})
        )
        BackendClient(BASE).kb_add_points("e1", ["Shipped the churn model"], origin_detail="Claude")
    headers = route.calls.last.request.headers
    assert headers.get_list(ORIGIN) == ["mcp"]
    assert headers["X-Maestro-CS-Origin-Detail"] == "Claude"
