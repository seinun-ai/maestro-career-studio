"""propose_application: request shape and who-filed-it provenance."""

import json

import httpx
import respx

from mcp_server.client import BackendClient

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
