import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_create_tailoring_session_posts_payload():
    route = respx.post(f"{BASE}/api/tailoring-sessions").mock(
        return_value=httpx.Response(200, json={"id": "s1", "status": "open"})
    )
    client = BackendClient(BASE)
    assert client.create_tailoring_session("job1", "hybrid") == {"id": "s1", "status": "open"}
    body = json.loads(route.calls.last.request.read())
    assert body == {"job_id": "job1", "base_resume": "hybrid", "enrich": True}


@respx.mock
def test_create_tailoring_session_enrich_false():
    route = respx.post(f"{BASE}/api/tailoring-sessions").mock(
        return_value=httpx.Response(200, json={"id": "s1"})
    )
    BackendClient(BASE).create_tailoring_session("job1", "hybrid", enrich=False)
    assert json.loads(route.calls.last.request.read())["enrich"] is False


@respx.mock
def test_get_tailoring_session_gets_by_id():
    respx.get(f"{BASE}/api/tailoring-sessions/s1").mock(
        return_value=httpx.Response(200, json={"id": "s1", "status": "open"})
    )
    assert BackendClient(BASE).get_tailoring_session("s1")["id"] == "s1"


@respx.mock
def test_list_tailoring_sessions_gets_by_job_id():
    route = respx.get(f"{BASE}/api/tailoring-sessions").mock(
        return_value=httpx.Response(
            200, json=[{"id": "s2", "status": "open"}, {"id": "s1", "status": "abandoned"}]
        )
    )
    out = BackendClient(BASE).list_tailoring_sessions("job1")
    assert [s["id"] for s in out] == ["s2", "s1"]
    assert route.calls.last.request.url.params["job_id"] == "job1"


@respx.mock
def test_close_tailoring_session_posts_close():
    route = respx.post(f"{BASE}/api/tailoring-sessions/s1/close").mock(
        return_value=httpx.Response(200, json={"id": "s1", "status": "abandoned"})
    )
    out = BackendClient(BASE).close_tailoring_session("s1")
    assert out["status"] == "abandoned"
    assert route.called
    assert route.calls.last.request.method == "POST"


@respx.mock
def test_apply_quick_tailor_profile_posts_to_the_session():
    route = respx.post(f"{BASE}/api/tailoring-sessions/s1/apply-profile").mock(
        return_value=httpx.Response(200, json={"id": "s1", "status": "open"})
    )
    assert BackendClient(BASE).apply_quick_tailor_profile("s1")["id"] == "s1"
    assert route.called
    assert route.calls.last.request.method == "POST"


@respx.mock
def test_resolve_gaps_patches_resolutions():
    route = respx.patch(f"{BASE}/api/tailoring-sessions/s1").mock(
        return_value=httpx.Response(200, json={"id": "s1"})
    )
    resolutions = [{"gap_id": "skill:python", "action": "user_input", "payload": {"text": "3y"}}]
    BackendClient(BASE).resolve_gaps("s1", resolutions)
    assert json.loads(route.calls.last.request.read()) == {"resolutions": resolutions}


@respx.mock
def test_tailor_session_posts_and_drops_none_prompt():
    route = respx.post(f"{BASE}/api/tailoring-sessions/s1/tailor").mock(
        return_value=httpx.Response(200, json={"session": {"id": "s1"}, "compare": None})
    )
    client = BackendClient(BASE)
    out = client.tailor_session("s1")
    assert out["session"]["id"] == "s1"
    assert json.loads(route.calls.last.request.read()) == {}
    client.tailor_session("s1", user_prompt="keep it terse")
    assert json.loads(route.calls.last.request.read()) == {"user_prompt": "keep it terse"}


@respx.mock
def test_tailor_session_includes_ops_when_supplied():
    route = respx.post(f"{BASE}/api/tailoring-sessions/s1/tailor").mock(
        return_value=httpx.Response(200, json={"session": {"id": "s1"}, "compare": None})
    )
    ops = [{"kind": "add_skill_item", "category": "Languages", "item": "Salesforce"}]
    BackendClient(BASE).tailor_session("s1", ops=ops)
    # caller-supplied ops travel in the POST body verbatim
    assert json.loads(route.calls.last.request.read()) == {"ops": ops}


@respx.mock
def test_tailor_session_ops_and_user_prompt_both_sent():
    route = respx.post(f"{BASE}/api/tailoring-sessions/s1/tailor").mock(
        return_value=httpx.Response(200, json={"session": {"id": "s1"}, "compare": None})
    )
    ops = [{"kind": "add_skill_item", "category": "Languages", "item": "Salesforce"}]
    BackendClient(BASE).tailor_session("s1", user_prompt="keep it terse", ops=ops)
    assert json.loads(route.calls.last.request.read()) == {
        "user_prompt": "keep it terse",
        "ops": ops,
    }


@respx.mock
def test_tailor_session_omits_ops_when_absent():
    route = respx.post(f"{BASE}/api/tailoring-sessions/s1/tailor").mock(
        return_value=httpx.Response(200, json={"session": {"id": "s1"}, "compare": None})
    )
    # no ops arg -> no "ops" key in the body (None is dropped, not sent as null)
    BackendClient(BASE).tailor_session("s1")
    assert "ops" not in json.loads(route.calls.last.request.read())
