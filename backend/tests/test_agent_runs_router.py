"""The run log over HTTP."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_proposals_models import _mk_job

client = TestClient(app)
MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"}


@pytest.fixture(autouse=True)
def _isolated_runs(db_session):
    """Clear the shared test database before and after each HTTP test."""
    yield


def _post(json, headers=MCP):
    return client.post("/api/agent-runs", json=json, headers=headers)


def _ids(runs):
    return [run["id"] for run in runs]


def test_an_agent_records_a_run_and_its_name_is_kept():
    response = _post({"automation": "mail-status", "outcome": "partial",
                      "counts": {"updated": 2}, "digest": "Acme: interview"})
    assert response.status_code == 201
    body = response.json()
    assert (body["agent"], body["title"], body["counts"]) == (
        "claude-ai", "Mail status", {"updated": 2})
    assert body["digest"] == "Acme: interview"
    assert uuid.UUID(body["id"])
    assert body["finished_at"].endswith("Z")


def test_a_run_without_mcp_headers_has_no_agent_name():
    response = _post({"automation": "job-hunt", "outcome": "ok"}, headers={})
    assert response.status_code == 201
    assert response.json()["agent"] is None


def test_unknown_count_keys_are_refused():
    assert _post({"automation": "job-hunt", "outcome": "ok",
                  "counts": {"x": 1}}).status_code == 422


def test_latest_and_recent_read_back():
    old = _post({"automation": "tailor-run", "outcome": "ok"})
    other = _post({"automation": "mail-status", "outcome": "partial"})
    newest = _post({"automation": "tailor-run", "outcome": "failed", "digest": "no AI key"})
    assert newest.status_code == 201
    latest = client.get("/api/agent-runs/latest")
    assert latest.status_code == 200
    assert _ids(latest.json()["items"]) == [
        newest.json()["id"], other.json()["id"]]
    assert latest.json()["items"][0]["outcome"] == "failed"
    recent = client.get("/api/agent-runs", params={"limit": 1})
    assert recent.status_code == 200
    assert _ids(recent.json()["items"]) == [newest.json()["id"]]
    history = client.get("/api/agent-runs").json()["items"]
    assert _ids(history) == [
        newest.json()["id"], other.json()["id"], old.json()["id"]]


@pytest.mark.parametrize("limit", [0, 201, "many"], ids=["zero", "too-high", "not-integer"])
def test_recent_requires_a_limit_between_one_and_200(limit):
    assert client.get("/api/agent-runs", params={"limit": limit}).status_code == 422


@pytest.mark.parametrize("extra", [
    {"counts": {"found": -1}},
    {"outcome": "unknown"},
    {"automation": "   "},
    {"automation": "x" * 41},
    {"agent": "forged"},
    {"job_ids": ["not-a-uuid"]},
], ids=["negative-count", "unknown-outcome", "blank-name", "long-name", "extra-field", "bad-id"])
def test_invalid_reports_are_refused_without_recording_a_run(extra):
    response = _post({"automation": "job-hunt", "outcome": "ok", **extra})
    assert response.status_code == 422
    assert client.get("/api/agent-runs").json() == {"items": []}


@pytest.mark.parametrize("headers", [
    {"X-Maestro-CS-Origin-Detail": "forged"},
    {"X-Maestro-CS-Origin": "web", "X-Maestro-CS-Origin-Detail": "forged"},
], ids=["detail-only", "unknown-origin"])
def test_a_client_name_is_kept_only_for_an_mcp_origin(headers):
    response = _post({"automation": "job-hunt", "outcome": "ok"}, headers=headers)
    assert response.status_code == 201
    assert response.json()["agent"] is None


def test_an_encoded_client_name_round_trips():
    response = _post({"automation": "custom-run", "outcome": "ok"}, headers={
        "X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "Caf%C3%A9 Agent"})
    assert response.status_code == 201
    assert (response.json()["agent"], response.json()["title"]) == ("Café Agent", "custom-run")


@pytest.mark.parametrize("path", ["/api/agent-runs", "/api/agent-runs/latest"])
def test_an_empty_log_reads_as_an_empty_list(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"items": [], **({"refused_requests": []} if path.endswith("latest") else {})}


def test_recent_defaults_to_twenty_runs():
    for n in range(21):
        response = _post({"automation": "job-hunt", "outcome": "ok", "digest": str(n)})
        assert response.status_code == 201
    recent = client.get("/api/agent-runs").json()["items"]
    assert [run["digest"] for run in recent] == [str(n) for n in range(20, 0, -1)]


def test_long_reports_are_trimmed_and_only_known_jobs_are_returned(db_session):
    job = _mk_job(db_session, title="Data Scientist", company="Acme")
    response = _post({"automation": "job-hunt", "outcome": "ok", "digest": "x" * 2500,
                      "job_ids": [str(job.id)] + [str(uuid.uuid4()) for _ in range(60)]})
    assert response.status_code == 201
    body = response.json()
    assert len(body["digest"]) == 2000 and body["digest"].endswith("…")
    assert body["jobs"] == [{"id": str(job.id), "title": "Data Scientist", "company": "Acme"}]
