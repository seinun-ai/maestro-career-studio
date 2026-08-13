"""POST /api/kb/points/bulk-state — batch approve/retire with honest per-id results."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.career_kb import KBPoint


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _draft(client, db_session, text="draft point"):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    point = KBPoint(
        entity_id=uuid.UUID(eid), text=text, state="draft", origin="ingested",
    )
    db_session.add(point)
    db_session.commit()
    return point


def test_bulk_state_mixed_unknown_ids_partial_success(client, db_session):
    a = _draft(client, db_session, "one")
    missing = uuid.uuid4()
    r = client.post("/api/kb/points/bulk-state", json={
        "ids": [str(a.id), str(missing)],
        "state": "approved",
    })
    assert r.status_code == 200, r.text
    results = {row["id"]: row for row in r.json()["results"]}
    assert results[str(a.id)]["ok"] is True
    assert results[str(a.id)]["state"] == "approved"
    assert results[str(missing)]["ok"] is False
    assert results[str(missing)]["detail"] == "not found"
    db_session.refresh(a)
    assert a.state == "approved"
    assert a.approved_at is not None


def test_bulk_state_draft_to_approved_stamps_approved_at(client, db_session):
    before = datetime.now(UTC)
    point = _draft(client, db_session)
    r = client.post("/api/kb/points/bulk-state", json={
        "ids": [str(point.id)], "state": "approved",
    })
    assert r.status_code == 200
    db_session.refresh(point)
    assert point.state == "approved"
    assert point.approved_at is not None
    assert point.approved_at >= before
    # Re-approving an already-approved point must not clear approved_at.
    stamped = point.approved_at
    client.post("/api/kb/points/bulk-state", json={
        "ids": [str(point.id)], "state": "approved",
    })
    db_session.refresh(point)
    assert point.approved_at == stamped


def test_bulk_state_approved_to_retired_clears_approved_at(client, db_session):
    point = _draft(client, db_session)
    client.post("/api/kb/points/bulk-state", json={
        "ids": [str(point.id)], "state": "approved",
    })
    db_session.refresh(point)
    assert point.approved_at is not None
    r = client.post("/api/kb/points/bulk-state", json={
        "ids": [str(point.id)], "state": "retired",
    })
    assert r.status_code == 200
    assert r.json()["results"][0]["ok"] is True
    assert r.json()["results"][0]["state"] == "retired"
    db_session.refresh(point)
    assert point.state == "retired"
    assert point.approved_at is None


def test_bulk_state_collapses_repeated_ids_to_one_result(client, db_session):
    point = _draft(client, db_session)
    r = client.post("/api/kb/points/bulk-state", json={
        "ids": [str(point.id), str(point.id)], "state": "approved",
    })
    assert r.status_code == 200, r.text
    assert [row["id"] for row in r.json()["results"]] == [str(point.id)]


@pytest.mark.parametrize(
    "ids", [[], [str(uuid.uuid4()) for _ in range(501)]], ids=["empty", "over-cap"]
)
def test_bulk_state_bounds_the_batch(client, ids):
    r = client.post("/api/kb/points/bulk-state", json={"ids": ids, "state": "approved"})
    assert r.status_code == 422, r.text


def test_bulk_state_rejects_draft_target(client, db_session):
    point = _draft(client, db_session)
    r = client.post("/api/kb/points/bulk-state", json={
        "ids": [str(point.id)], "state": "draft",
    })
    assert r.status_code == 422
    db_session.refresh(point)
    assert point.state == "draft"
