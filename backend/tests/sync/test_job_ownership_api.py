"""Task 13: the browser sees the guard's ownership and uses its handover actions."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.job import Job
from app.models.sync import SyncRequest
from app.services.sync import status

OFF = {"owned_here": True, "owner": None, "handover": None, "pending_requests": 0}
QUEUED = {"queued": True, "detail": "Sent at the next sync."}


@pytest.fixture
def client(db_session):
    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _job(db, owner=None, handover=None):
    row = Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex,
              title="Engineer", company="Example employer", owner_machine=owner, handover=handover)
    db.info["sync_apply"] = True
    try:
        db.add(row)
        db.commit()
    finally:
        db.info.pop("sync_apply", None)
    return row


def _views(client, job):
    single = client.get(f"/api/jobs/{job.id}")
    detail = client.get(f"/api/jobs/{job.id}/detail")
    listed = client.get("/api/jobs")
    assert single.status_code == detail.status_code == listed.status_code == 200
    return [single.json(), detail.json()["job"], listed.json()[0]]


@pytest.mark.parametrize("case", [
    (None, None, True, "laptop"),
    ("other-copy", None, False, "bot"),
    (None, "offered", False, "laptop"),
])
def test_home_reads_match_guard(client, db_session, sync_on, case):
    owner, handover, owned, label = case
    job = _job(db_session, owner, handover)
    for view in _views(client, job):
        assert view["ownership"] == {"owned_here": owned, "owner": label,
                                     "handover": handover, "pending_requests": 0}


@pytest.mark.parametrize("case", [
    (None, None, True, "bot"),
    ("other-copy", None, False, "laptop"),
    (None, "returning", False, "bot"),
])
def test_remote_labels_are_relative(client, db_session, sync_remote, case):
    owner, handover, owned, label = case
    job = _job(db_session, owner, handover)
    for view in _views(client, job):
        assert view["ownership"] == {"owned_here": owned, "owner": label,
                                     "handover": handover, "pending_requests": 0}


def test_counts_only_viewers_unanswered_requests(client, db_session, sync_on):
    job = _job(db_session, "other-copy")
    db_session.add_all([
        SyncRequest(job_id=job.id, kind="take_over", payload_json={}, origin=origin, status=state)
        for origin, state in [("local", "pending"), ("local", "sent"),
                              ("local", "refused"), ("remote", "pending")]
    ])
    db_session.commit()
    assert all(view["ownership"]["pending_requests"] == 2 for view in _views(client, job))


def test_sync_off_never_marks_or_locks_stored_replicas(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    job = _job(db_session, "other-copy", "offered")
    assert all(view["ownership"] == OFF for view in _views(client, job))
    patch = client.patch(f"/api/jobs/{job.id}", json={"source_url": "https://example.test/job"})
    assert patch.status_code == 200 and patch.json()["ownership"] == OFF
    for action in ["keep-here", "work-here"]:
        assert client.post(f"/api/jobs/{job.id}/{action}").status_code == 404
    assert client.get("/api/sync/hello").status_code == 404


def test_keep_here_cancels_offer_and_restores_normal_writes(client, db_session, sync_on):
    job = _job(db_session, handover="offered")
    before = job.sync_rev
    response = client.post(f"/api/jobs/{job.id}/keep-here")
    assert response.status_code == 200
    assert response.json()["ownership"] == {"owned_here": True, "owner": "laptop",
                                            "handover": None, "pending_requests": 0}
    db_session.refresh(job)
    assert job.owner_machine is None and job.handover is None and job.sync_rev > before
    assert not db_session.info.get("sync_apply")
    assert client.patch(f"/api/jobs/{job.id}", json={"source_url": "https://example.test/job"}).status_code == 200
    assert client.post(f"/api/jobs/{job.id}/keep-here").status_code == 200


def test_keep_here_never_unlocks_a_replica(client, db_session, sync_on):
    job = _job(db_session, "other-copy", "offered")
    assert client.post(f"/api/jobs/{job.id}/keep-here").status_code == 409
    db_session.refresh(job)
    assert (job.owner_machine, job.handover) == ("other-copy", "offered")


def test_work_here_enqueues_once_and_keeps_replica_unchanged(client, db_session, sync_on):
    job = _job(db_session, "other-copy")
    before = job.sync_rev
    for _ in range(2):
        response = client.post(f"/api/jobs/{job.id}/work-here")
        assert (response.status_code, response.json()) == (202, QUEUED)
    rows = db_session.scalars(select(SyncRequest)).all()
    assert len(rows) == 1
    assert (rows[0].kind, rows[0].job_id, rows[0].payload_json) == ("take_over", job.id, {})
    db_session.refresh(job)
    assert job.owner_machine == "other-copy" and job.sync_rev == before
    assert all(view["ownership"]["pending_requests"] == 1 for view in _views(client, job))


@pytest.mark.parametrize("action", ["keep-here", "work-here"])
def test_handover_buttons_are_home_only(client, db_session, sync_remote, action):
    job = _job(db_session, "other-copy")
    assert client.post(f"/api/jobs/{job.id}/{action}").status_code == 409
    assert not db_session.scalars(select(SyncRequest)).all()


@pytest.mark.parametrize("action", ["keep-here", "work-here"])
def test_handover_buttons_need_a_job(client, sync_on, action):
    assert client.post(f"/api/jobs/{uuid.uuid4()}/{action}").status_code == 404


@pytest.mark.parametrize("handover", [None, "offered"])
def test_work_here_does_not_request_a_home_job(client, db_session, sync_on, handover):
    job = _job(db_session, status.machine_id(db_session), handover)
    assert client.post(f"/api/jobs/{job.id}/work-here").status_code == 409
    assert not db_session.scalars(select(SyncRequest)).all()


def test_ingest_and_dedup_keep_ownership_in_the_response(client, db_session, sync_on):
    body = {"raw_text": "Example captured role", "extracted_json": {"title": "Engineer", "company": "Example employer"}}
    created = client.post("/api/jobs/ingest", json=body)
    assert created.status_code == 200
    assert created.json()["ownership"]["owner"] == "laptop"
    job = db_session.get(Job, uuid.UUID(created.json()["id"]))
    db_session.info["sync_apply"] = True
    try:
        job.owner_machine = "other-copy"
        db_session.commit()
    finally:
        db_session.info.pop("sync_apply", None)
    duplicate = client.post("/api/jobs/ingest", json=body)
    assert duplicate.status_code == 200
    assert duplicate.json()["already_existed"] is True
    assert duplicate.json()["ownership"]["owner"] == "bot"
    assert duplicate.json()["ownership"]["owned_here"] is False
