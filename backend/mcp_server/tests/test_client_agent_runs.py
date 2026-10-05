"""record_run's request shape: the report is flattened, the client name rides the headers."""

import json

import httpx
import pytest
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_record_run_posts_the_report_and_names_the_client():
    route = respx.post(f"{BASE}/api/agent-runs").mock(
        return_value=httpx.Response(201, json={"id": "r1"})
    )
    result = BackendClient(BASE).record_run(
        "job-hunt", "ok", {"counts": {"found": 3}, "digest": "d"}, origin_detail="claude-ai"
    )
    request = route.calls.last.request
    assert result == {"id": "r1"}
    assert json.loads(request.read()) == {
        "automation": "job-hunt", "outcome": "ok", "counts": {"found": 3}, "digest": "d"
    }
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "claude-ai"


@pytest.mark.parametrize(
    ("report", "fields"),
    [
        (None, {}),
        ({}, {}),
        ({"counts": None, "digest": None, "job_ids": None}, {}),
        ({"counts": {"found": 0}, "digest": "", "job_ids": []},
         {"counts": {"found": 0}, "digest": "", "job_ids": []}),
        ({"job_ids": ["00000000-0000-0000-0000-000000000001"]},
         {"job_ids": ["00000000-0000-0000-0000-000000000001"]}),
    ],
)
@respx.mock
def test_record_run_omits_null_report_fields_and_keeps_empty_values(report, fields):
    route = respx.post(f"{BASE}/api/agent-runs").mock(
        return_value=httpx.Response(201, json={"id": "r1"})
    )
    BackendClient(BASE).record_run("custom-run", "partial", report)
    request = route.calls.last.request
    assert json.loads(request.read()) == {"automation": "custom-run", "outcome": "partial", **fields}
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert "X-Maestro-CS-Origin-Detail" not in request.headers


@respx.mock
def test_record_run_encodes_a_unicode_client_name():
    route = respx.post(f"{BASE}/api/agent-runs").mock(
        return_value=httpx.Response(201, json={"id": "r1"})
    )
    BackendClient(BASE).record_run("job-hunt", "failed", None, origin_detail="クロード")
    assert route.calls.last.request.headers["X-Maestro-CS-Origin-Detail"] == (
        "%E3%82%AF%E3%83%AD%E3%83%BC%E3%83%89"
    )
