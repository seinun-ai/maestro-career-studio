import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server import server as srv
from mcp_server.client import BackendClient

BASE = "http://test-backend"


# explore_trends: each view reads the route its old tool read, with only the
# parameters that view takes; None-valued filters are dropped, never sent as "None".
@pytest.mark.parametrize(
    "view, route, kwargs, params",
    [
        ("top_skills", "top-skills", {"role_category": "operations", "limit": 10},
         {"role_category": "operations", "limit": "10"}),
        ("heatmap", "heatmap", {"limit": 5}, {"limit": "5"}),
        ("heatmap", "heatmap", {"level": "senior", "limit": 5}, {"level": "senior", "limit": "5"}),
        ("role_mix", "role-mix-over-time", {}, {}),
        ("role_mix", "role-mix-over-time", {"role_category": "operations", "employment_type": "contract"},
         {"role_category": "operations", "employment_type": "contract"}),
        ("fit_distribution", "fit-distribution", {}, {}),
        ("ats_over_time", "ats-over-time", {"role_category": "operations", "level": "senior"},
         {"role_category": "operations", "level": "senior"}),
        ("tailoring_lift", "tailoring-lift", {"employment_type": "full_time"},
         {"employment_type": "full_time"}),
    ],
)
def test_explore_trends_reads_each_views_route(monkeypatch, view, route, kwargs, params):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        called = respx.get(f"{BASE}/api/explore/{route}").mock(
            return_value=httpx.Response(200, json=[])
        )
        assert srv.explore_trends(view, **kwargs) == []
    assert dict(called.calls.last.request.url.params) == params


@pytest.mark.parametrize(
    "view, kwargs, refusal",
    [
        ("fit_distribution", {"employment_type": "full_time"}, "fit_distribution takes no filters"),
        ("fit_distribution", {"role_category": "operations"}, "fit_distribution takes no filters"),
        ("role_mix", {"limit": 5}, "role_mix takes no limit"),
        ("fit_distribution", {"limit": 5}, "fit_distribution takes no limit"),
        ("ats_over_time", {"limit": 5}, "ats_over_time takes no limit"),
        ("tailoring_lift", {"limit": 5}, "tailoring_lift takes no limit"),
    ],
)
def test_explore_trends_refuses_what_a_view_does_not_take_before_any_request(
    monkeypatch, view, kwargs, refusal
):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock(assert_all_called=False) as router:
        explore = router.get(url__startswith=f"{BASE}/api/explore/").mock(
            return_value=httpx.Response(200, json=[])
        )
        with pytest.raises(ToolError, match=f"^{refusal}$"):
            srv.explore_trends(view, **kwargs)
    assert not explore.called


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
