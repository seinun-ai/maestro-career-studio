import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_get_job_search_brief():
    route = respx.get(f"{BASE}/api/jobs/search-brief").mock(
        return_value=httpx.Response(
            200,
            json={
                "persona": "",
                "warnings": [],
                "referrals": [],
                "generated_at": "2026-07-21T00:00:00+00:00",
                "windows": {
                    "role_mix": "all_time",
                    "top_skills": "all_time",
                    "build_areas": "all_time",
                    "captured_last_30_days": "last_30_days",
                },
            },
        )
    )
    client = BackendClient(BASE)
    out = client.get_job_search_brief()
    assert out["warnings"] == []
    # Provenance labels pass through the MCP client unchanged.
    assert out["generated_at"] == "2026-07-21T00:00:00+00:00"
    assert out["windows"]["captured_last_30_days"] == "last_30_days"
    assert route.called


@respx.mock
def test_find_job_by_url_found_with_application():
    list_route = respx.get(f"{BASE}/api/jobs").mock(
        return_value=httpx.Response(200, json=[{"id": "j1", "company": "Acme"}])
    )
    respx.get(f"{BASE}/api/jobs/j1/detail").mock(
        return_value=httpx.Response(
            200, json={"job": {"id": "j1"}, "application": {"id": "a1", "status": "applied"}}
        )
    )
    client = BackendClient(BASE)
    out = client.find_job_by_url("https://x.test/jobs/1")
    assert out == {
        "found": True,
        "job": {"id": "j1", "company": "Acme"},
        "application_exists": True,
        "application_id": "a1",
    }
    params = list_route.calls.last.request.url.params
    assert params["source_url"] == "https://x.test/jobs/1"


@respx.mock
def test_find_job_by_url_found_without_application():
    respx.get(f"{BASE}/api/jobs").mock(
        return_value=httpx.Response(200, json=[{"id": "j2"}])
    )
    respx.get(f"{BASE}/api/jobs/j2/detail").mock(
        return_value=httpx.Response(200, json={"job": {"id": "j2"}, "application": None})
    )
    out = BackendClient(BASE).find_job_by_url("https://x.test/jobs/2")
    assert out["found"] is True
    assert out["application_exists"] is False
    assert out["application_id"] is None


@respx.mock
def test_find_job_by_url_not_found():
    respx.get(f"{BASE}/api/jobs").mock(return_value=httpx.Response(200, json=[]))
    out = BackendClient(BASE).find_job_by_url("https://x.test/jobs/none")
    assert out == {
        "found": False,
        "job": None,
        "application_exists": False,
        "application_id": None,
    }


@respx.mock
def test_find_job_by_url_strips_before_building_params():
    # Defense in depth: the client strips the URL so the exact-match filter
    # (which stores stripped URLs) can't miss on trailing whitespace.
    list_route = respx.get(f"{BASE}/api/jobs").mock(
        return_value=httpx.Response(200, json=[{"id": "j9"}])
    )
    respx.get(f"{BASE}/api/jobs/j9/detail").mock(
        return_value=httpx.Response(200, json={"job": {"id": "j9"}, "application": None})
    )
    out = BackendClient(BASE).find_job_by_url("  https://x.test/jobs/9\n")
    assert out["found"] is True
    params = list_route.calls.last.request.url.params
    assert params["source_url"] == "https://x.test/jobs/9"
