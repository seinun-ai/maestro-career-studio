import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"

SAMPLE_REPORT = {
    "score": 78,
    "grade": "B",
    "tier": "send_with_edits",
    "gates": [],
    "counts": {"strong": 4, "weak": 2},
    "findings": [],
}


@respx.mock
def test_run_health_check_posts_to_run_endpoint():
    route = respx.post(f"{BASE}/api/resume-lint/base/my-slug/run").mock(
        return_value=httpx.Response(200, json=SAMPLE_REPORT)
    )
    client = BackendClient(BASE)
    out = client.run_health_check("base", "my-slug")
    assert out == SAMPLE_REPORT
    assert route.called
    assert route.calls.last.request.method == "POST"


@respx.mock
def test_get_health_report_gets_latest_by_kind_key():
    uuid = "11111111-2222-3333-4444-555555555555"
    route = respx.get(f"{BASE}/api/resume-lint/application/{uuid}").mock(
        return_value=httpx.Response(200, json=SAMPLE_REPORT)
    )
    client = BackendClient(BASE)
    out = client.get_health_report("application", uuid)
    assert out == SAMPLE_REPORT
    assert route.called
    assert route.calls.last.request.method == "GET"


@respx.mock
def test_judge_health_bullets_posts_classifications_with_the_client_name():
    import json

    route = respx.post(f"{BASE}/api/resume-lint/base/my-slug/judgments").mock(
        return_value=httpx.Response(200, json={**SAMPLE_REPORT, "accepted": [], "rejected": []})
    )
    entries = [{"id": "0123456789abcdef", "level": "direct"}]
    client = BackendClient(BASE)
    client.judge_health_bullets("base", "my-slug", entries, origin_detail="claude-ai")
    request = route.calls.last.request
    assert json.loads(request.content) == {"classifications": entries}
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "claude-ai"
