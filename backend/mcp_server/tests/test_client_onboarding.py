"""Onboarding MCP client methods: ingest-parsed, bulk-state, from-kb."""

import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_kb_ingest_resume_posts_single_source_with_origin_headers():
    route = respx.post(f"{BASE}/api/kb/ingest-parsed").mock(
        return_value=httpx.Response(200, json={"entities": [], "points": []})
    )
    client = BackendClient(BASE)
    data = {"contact": {"name": "A", "email": "a@x.com"}}
    out = client.kb_ingest_resume("ds_resume", data, origin_detail="Claude Desktop")
    assert out == {"entities": [], "points": []}
    request = route.calls.last.request
    # Provenance travels in headers like every other KB write — the request
    # model forbids extras, so an origin_detail in the body would be a 422.
    assert json.loads(request.read()) == {
        "sources": [{"key": "ds_resume", "data": data}],
    }
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "Claude Desktop"


@respx.mock
def test_kb_ingest_resume_sends_origin_even_without_a_client_label():
    route = respx.post(f"{BASE}/api/kb/ingest-parsed").mock(
        return_value=httpx.Response(200, json={"entities": [], "points": []})
    )
    BackendClient(BASE).kb_ingest_resume("ds", {"contact": {"name": "A", "email": "a@x.com"}})
    request = route.calls.last.request
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert "X-Maestro-CS-Origin-Detail" not in request.headers


@respx.mock
def test_kb_approve_points_posts_bulk_state():
    route = respx.post(f"{BASE}/api/kb/points/bulk-state").mock(
        return_value=httpx.Response(200, json={"results": [{"id": "p1", "ok": True, "state": "approved"}]})
    )
    client = BackendClient(BASE)
    out = client.kb_approve_points(["p1", "p2"], state="retired")
    assert out["results"][0]["ok"] is True
    assert json.loads(route.calls.last.request.read()) == {
        "ids": ["p1", "p2"],
        "state": "retired",
    }


@respx.mock
def test_kb_approve_points_defaults_to_approved():
    route = respx.post(f"{BASE}/api/kb/points/bulk-state").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client = BackendClient(BASE)
    client.kb_approve_points(["p1"])
    assert json.loads(route.calls.last.request.read()) == {
        "ids": ["p1"],
        "state": "approved",
    }


@respx.mock
def test_create_base_resume_from_kb_posts_entity_ids():
    route = respx.post(f"{BASE}/api/base-resumes/from-kb").mock(
        return_value=httpx.Response(200, json={"slug": "ds"})
    )
    client = BackendClient(BASE)
    out = client.create_base_resume_from_kb(
        ["e1", "e2"],
        role_category="data_scientist",
        role_label="DS",
        display_name="Data Scientist",
        include_summary=True,
        summary="Reviewed summary",
    )
    assert out == {"slug": "ds"}
    body = json.loads(route.calls.last.request.read())
    assert body["entity_ids"] == ["e1", "e2"]
    assert body["role_category"] == "data_scientist"
    assert body["role_label"] == "DS"
    assert body["display_name"] == "Data Scientist"
    assert body["include_summary"] is True
    assert body["summary"] == "Reviewed summary"
