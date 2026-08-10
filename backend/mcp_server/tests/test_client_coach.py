import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_explore_top_skills_passes_filters():
    route = respx.get(f"{BASE}/api/explore/top-skills").mock(
        return_value=httpx.Response(200, json={"top": [], "rest": []})
    )
    client = BackendClient(BASE)
    client.explore_top_skills(role_category="data_engineer", limit=10)
    params = route.calls.last.request.url.params
    assert params["role_category"] == "data_engineer"
    assert params["limit"] == "10"
    # None-valued filters must be dropped, not sent as "None"
    assert "level" not in params
    assert "employment_type" not in params


@respx.mock
def test_explore_heatmap_and_simple_gets():
    respx.get(f"{BASE}/api/explore/heatmap").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/api/explore/role-mix-over-time").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/api/explore/fit-distribution").mock(return_value=httpx.Response(200, json=[]))
    client = BackendClient(BASE)
    assert client.explore_skill_heatmap(limit=5) == []
    assert client.explore_role_mix_over_time() == []
    assert client.explore_fit_distribution() == []


@respx.mock
def test_explore_gap_frequency_passes_filters():
    route = respx.get(f"{BASE}/api/explore/gap-frequency").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = BackendClient(BASE)
    assert client.explore_gap_frequency(role_category="data_engineer", limit=10) == []
    params = route.calls.last.request.url.params
    assert params["role_category"] == "data_engineer"
    assert params["limit"] == "10"
    # None-valued filters must be dropped, not sent as "None"
    assert "level" not in params
    assert "employment_type" not in params


@respx.mock
def test_explore_ats_over_time_passes_filters():
    route = respx.get(f"{BASE}/api/explore/ats-over-time").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = BackendClient(BASE)
    assert client.explore_ats_over_time(role_category="data_engineer", level="senior") == []
    params = route.calls.last.request.url.params
    assert params["role_category"] == "data_engineer"
    assert params["level"] == "senior"
    assert "employment_type" not in params


@respx.mock
def test_explore_tailoring_lift_passes_filters():
    route = respx.get(f"{BASE}/api/explore/tailoring-lift").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = BackendClient(BASE)
    assert client.explore_tailoring_lift(employment_type="full_time") == []
    params = route.calls.last.request.url.params
    assert params["employment_type"] == "full_time"
    assert "role_category" not in params
    assert "level" not in params


@respx.mock
def test_list_applications_and_export_jobs():
    appsroute = respx.get(f"{BASE}/api/applications").mock(return_value=httpx.Response(200, json=[]))
    exproute = respx.get(f"{BASE}/api/jobs/export").mock(return_value=httpx.Response(200, json=[]))
    client = BackendClient(BASE)
    assert client.list_applications(status="draft", limit=25, offset=50) == []
    apps_params = appsroute.calls.last.request.url.params
    assert apps_params["status"] == "draft"
    assert apps_params["limit"] == "25"
    assert apps_params["offset"] == "50"
    assert client.export_jobs(skill="sql", role_category="data_engineer") == []
    exp_params = exproute.calls.last.request.url.params
    assert exp_params["skill"] == "sql"
    assert exp_params["role_category"] == "data_engineer"
