"""Sync calls expose counts and ownership, never the channel's contents."""

import json

import httpx
import pytest
import respx

from mcp_server import server as srv
from mcp_server.client import BackendClient, BackendError

BASE = "http://test-backend"


@pytest.mark.parametrize("summary", [
    {"ok": True, "outcome": "ok", "steps": {"push_jobs": {"sent": 2}}},
    {"ok": False, "outcome": "transient", "error": "Your laptop isn't reachable.", "steps": {}},
    {"ok": False, "outcome": "needs_person", "error": "Pair the copies first.", "steps": {}},
    {"ok": False, "outcome": "ok", "skipped": "Synced moments ago."},
])
@respx.mock
def test_sync_now_forces_a_round_and_preserves_its_summary(summary, monkeypatch):
    route = respx.post(f"{BASE}/api/sync/round").mock(
        return_value=httpx.Response(200, json=summary))
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))

    assert srv.sync_now() == summary
    assert json.loads(route.calls.last.request.content) == {"force": True}
    assert "origin" not in route.calls.last.request.headers
    assert "x-maestro-sync-key" not in route.calls.last.request.headers


@pytest.mark.parametrize(("sync", "sentence"), [
    ({"enabled": False, "role": None}, "Sync isn't set up."),
    ({"enabled": True, "role": "home"},
     "This is your laptop's copy; your bot runs the sync"),
])
@respx.mock
def test_sync_now_distinguishes_home_from_sync_off(sync, sentence, monkeypatch):
    respx.post(f"{BASE}/api/sync/round").mock(
        return_value=httpx.Response(404, json={"detail": "Not found."}))
    respx.get(f"{BASE}/api/jobs/search-brief").mock(
        return_value=httpx.Response(200, json={"sync": sync}))
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))

    assert srv.sync_now() == sentence


@pytest.mark.parametrize("code", [403, 409, 500])
@respx.mock
def test_sync_now_does_not_mislabel_other_errors_as_sync_off(code):
    respx.post(f"{BASE}/api/sync/round").mock(
        return_value=httpx.Response(code, json={"detail": "Round unavailable."}))

    with pytest.raises(BackendError) as error:
        BackendClient(BASE).sync_now()
    assert error.value.status_code == code


@respx.mock
def test_sync_now_does_not_hide_a_remote_route_404():
    respx.post(f"{BASE}/api/sync/round").mock(
        return_value=httpx.Response(404, json={"detail": "Not found."}))
    respx.get(f"{BASE}/api/jobs/search-brief").mock(
        return_value=httpx.Response(200, json={"sync": {"enabled": True, "role": "remote"}}))

    with pytest.raises(BackendError) as error:
        BackendClient(BASE).sync_now()
    assert error.value.status_code == 404


@respx.mock
def test_job_tools_preserve_replica_ownership(monkeypatch):
    ownership = {"owned_here": False, "owner": "laptop", "handover": None,
                 "pending_requests": 2}
    job = {"id": "j1", "ownership": ownership}
    respx.get(f"{BASE}/api/jobs").mock(return_value=httpx.Response(200, json=[job]))
    respx.get(f"{BASE}/api/jobs/j1/detail").mock(
        return_value=httpx.Response(200, json={"job": job, "application": None}))
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))

    assert srv.list_jobs()[0]["ownership"] == ownership
    assert srv.get_job("j1")["job"]["ownership"] == ownership
