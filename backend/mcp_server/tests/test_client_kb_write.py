"""Career KB write methods: request shape, forced demotion, provenance headers."""

import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_kb_capture_sends_origin_headers():
    route = respx.post(f"{BASE}/api/kb/capture").mock(
        return_value=httpx.Response(200, json={"entity_id": "e1", "point_ids": []})
    )
    client = BackendClient(BASE)
    client.kb_capture("Passed AWS SAA on 12 July.", origin_detail="Claude Desktop")
    request = route.calls.last.request
    assert json.loads(request.read()) == {"text": "Passed AWS SAA on 12 July."}
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "Claude Desktop"


@respx.mock
def test_kb_edit_point_forces_draft_when_text_changes():
    route = respx.patch(f"{BASE}/api/kb/points/p1").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    client = BackendClient(BASE)
    client.kb_edit_point("p1", text="Reworded bullet.")
    # The demotion rides in the SAME patch as the text: one call, no
    # read-modify-write race against a concurrent web edit.
    assert json.loads(route.calls.last.request.read()) == {
        "text": "Reworded bullet.",
        "state": "draft",
    }


@respx.mock
def test_kb_edit_point_tags_only_does_not_demote():
    route = respx.patch(f"{BASE}/api/kb/points/p1").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    client = BackendClient(BASE)
    client.kb_edit_point("p1", tags=["aws"])
    assert json.loads(route.calls.last.request.read()) == {"tags": ["aws"]}


@respx.mock
def test_kb_edit_entity_omits_unset_fields():
    route = respx.patch(f"{BASE}/api/kb/entities/e1").mock(
        return_value=httpx.Response(200, json={"id": "e1"})
    )
    client = BackendClient(BASE)
    client.kb_edit_entity("e1", end_date="2026-07")
    assert json.loads(route.calls.last.request.read()) == {"end_date": "2026-07"}


@respx.mock
def test_kb_edit_profile_sends_only_given_fields():
    route = respx.patch(f"{BASE}/api/kb/profile").mock(
        return_value=httpx.Response(200, json={"summary": "New"})
    )
    client = BackendClient(BASE)
    client.kb_edit_profile(summary="New")
    assert json.loads(route.calls.last.request.read()) == {"summary": "New"}


@respx.mock
def test_kb_reads_need_no_origin_header():
    respx.get(f"{BASE}/api/kb/entities").mock(return_value=httpx.Response(200, json=[]))
    client = BackendClient(BASE)
    assert client.list_kb_entities() == []
