import httpx
import pytest
import respx

from mcp_server.client import BackendClient, BackendError

BASE = "http://test-backend"


@respx.mock
def test_list_base_resumes():
    respx.get(f"{BASE}/api/base-resumes").mock(
        return_value=httpx.Response(200, json=[{"slug": "master"}])
    )
    client = BackendClient(BASE)
    assert client.list_base_resumes() == [{"slug": "master"}]


@respx.mock
def test_list_referrals():
    respx.get(f"{BASE}/api/referrals").mock(
        return_value=httpx.Response(
            200, json=[{"id": "r1", "company": "Acme", "applications_count": 2}]
        )
    )
    client = BackendClient(BASE)
    assert client.list_referrals() == [
        {"id": "r1", "company": "Acme", "applications_count": 2}
    ]


@respx.mock
def test_list_kb_points_sends_limit_offset_and_state():
    route = respx.get(f"{BASE}/api/kb/points").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert BackendClient(BASE).list_kb_points(
        state="draft", limit=50, offset=10
    ) == []
    params = route.calls.last.request.url.params
    assert params["state"] == "draft"
    assert params["limit"] == "50"
    assert params["offset"] == "10"


@respx.mock
def test_list_kb_points_defaults_limit_500_offset_0():
    route = respx.get(f"{BASE}/api/kb/points").mock(
        return_value=httpx.Response(200, json=[])
    )
    BackendClient(BASE).list_kb_points()
    params = route.calls.last.request.url.params
    assert params["limit"] == "500"
    assert params["offset"] == "0"
    assert "state" not in params


@respx.mock
def test_get_base_resume():
    respx.get(f"{BASE}/api/base-resumes/master").mock(
        return_value=httpx.Response(200, json={"slug": "master", "data": {}})
    )
    client = BackendClient(BASE)
    assert client.get_base_resume("master")["slug"] == "master"


@respx.mock
def test_list_jobs_passes_params():
    route = respx.get(f"{BASE}/api/jobs").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = BackendClient(BASE)
    assert client.list_jobs(limit=5, offset=10, without_application=True) == []
    params = route.calls.last.request.url.params
    assert params["limit"] == "5"
    assert params["offset"] == "10"
    assert params["without_application"] == "true"


@respx.mock
def test_get_job_uses_detail_endpoint():
    route = respx.get(f"{BASE}/api/jobs/abc/detail").mock(
        return_value=httpx.Response(200, json={"job": {"id": "abc"}})
    )
    client = BackendClient(BASE)
    out = client.get_job("abc")
    assert out["job"]["id"] == "abc"
    assert route.called


@respx.mock
def test_get_quick_tailor_profile_unwraps_value():
    respx.get(f"{BASE}/api/settings/quick-tailor").mock(
        return_value=httpx.Response(
            200, json={"key": "quick_tailor_profile", "value": {"role_category": "data"}}
        )
    )
    # equality (not just a membership check) catches a method that forgets to
    # unwrap and returns the {key, value} envelope instead of value alone
    assert BackendClient(BASE).get_quick_tailor_profile() == {"role_category": "data"}


@respx.mock
def test_get_mcp_workflow_settings_reads_the_setting():
    respx.get(f"{BASE}/api/settings/mcp-workflow").mock(
        return_value=httpx.Response(200, json={"key": "mcp_workflow", "value": {"hints": True}})
    )
    assert BackendClient(BASE).get_mcp_workflow_settings() == {"hints": True}


@respx.mock
def test_get_setup_status_returns_the_body_unwrapped():
    # SetupStatus has no {key, value} envelope — a copy-pasted `.get("value", {})`
    # would silently return {} here (the field doesn't exist), so asserting a
    # real field is present catches that mistake instead of vacuously passing.
    body = {
        "import_resumes": {"done": True, "detail": {}},
        "autofill": {"done": False, "readiness": 0.5, "groups": {}, "blocking": []},
        "job_preferences": {"done": True, "detail": {}},
        "persona": {"done": False, "detail": {}},
        "template": {"done": True, "detail": {}},
        "suggested_bases": [],
        "complete": False,
    }
    respx.get(f"{BASE}/api/setup/status").mock(return_value=httpx.Response(200, json=body))
    out = BackendClient(BASE).get_setup_status()
    assert out == body
    assert out["complete"] is False


@respx.mock
def test_error_maps_to_backend_error():
    respx.get(f"{BASE}/api/base-resumes/missing").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    client = BackendClient(BASE)
    with pytest.raises(BackendError) as exc:
        client.get_base_resume("missing")
    assert exc.value.status_code == 404
    assert "not found" in str(exc.value)


@respx.mock
def test_connection_error_maps_to_backend_error():
    respx.get(f"{BASE}/api/jobs").mock(side_effect=httpx.ConnectError("refused"))
    client = BackendClient(BASE)
    with pytest.raises(BackendError) as exc:
        client.list_jobs()
    assert "running" in str(exc.value).lower()


@respx.mock
def test_list_endpoints_return_single_json_array():
    # Regression for audit #10 (refuted in code): the backend emits list[Model]
    # as ONE JSON array and client._request returns it via a single response.json()
    # — there is no concatenated `}{` object stream. Guard against a future change
    # that splits the response.
    jobs_payload = [{"id": "j1", "company": "Acme"}, {"id": "j2", "company": "Beta"}]
    apps_payload = [{"id": "a1", "job_id": "j1"}]
    respx.get(f"{BASE}/api/jobs").mock(
        return_value=httpx.Response(200, json=jobs_payload)
    )
    respx.get(f"{BASE}/api/applications").mock(
        return_value=httpx.Response(200, json=apps_payload)
    )
    client = BackendClient(BASE)

    jobs = client.list_jobs()
    apps = client.list_applications()
    assert isinstance(jobs, list) and [j["id"] for j in jobs] == ["j1", "j2"]
    assert isinstance(apps, list) and [a["id"] for a in apps] == ["a1"]


@respx.mock
def test_get_application_uses_id_endpoint():
    route = respx.get(f"{BASE}/api/applications/a1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "a1", "customized_json": {"summary": "x"}},
        )
    )
    client = BackendClient(BASE)
    out = client.get_application("a1")
    assert out["id"] == "a1"
    assert out["customized_json"] == {"summary": "x"}
    assert route.called
