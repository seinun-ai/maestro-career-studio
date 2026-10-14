"""With sync on, a saved-again job fills its apply link only where this copy owns the job."""

import uuid

import pytest

from app.models.job import Job

APPLY = "https://acme.example/careers/apply/1"
BODY = {"raw_text": "Analyst at Globex", "extracted_json": {"company": "Globex", "title": "Analyst"}}


def _replica(db, job_id):
    """The way a sync apply leaves a job the other copy owns."""
    db.info["sync_apply"] = True
    try:
        db.get(Job, uuid.UUID(job_id)).owner_machine = "other-copy"
        db.commit()
    finally:
        db.info.pop("sync_apply", None)


def test_an_owned_job_still_gains_a_missing_link(client, db_session, sync_on):
    first = client.post("/api/jobs/ingest", json=BODY).json()

    again = client.post("/api/jobs/ingest", json={**BODY, "apply_url": APPLY})

    assert again.status_code == 200
    assert (again.json()["id"], again.json()["apply_url"]) == (first["id"], APPLY)


@pytest.mark.parametrize("route", ["ingest", "create"])
def test_a_replica_answers_a_saved_again_post_and_keeps_its_link_null(
    client, db_session, sync_on, monkeypatch, route
):
    from app.routers import jobs

    monkeypatch.setattr(jobs.jd_extraction, "extract_jd", lambda raw_text, session=None: {"title": "Analyst"})
    path, body = ("/api/jobs/ingest", BODY) if route == "ingest" else ("/api/jobs", {"raw_text": BODY["raw_text"]})
    first = client.post(path, json=body).json()
    _replica(db_session, first["id"])

    again = client.post(path, json={**body, "apply_url": APPLY})

    assert again.status_code == 200
    assert again.json()["already_existed"] is True
    assert again.json()["ownership"]["owned_here"] is False
    assert again.json()["apply_url"] is None
    db_session.expire_all()
    assert db_session.get(Job, uuid.UUID(first["id"])).apply_url is None


def test_a_job_offered_to_the_other_copy_is_left_alone_too(client, db_session, sync_on):
    first = client.post("/api/jobs/ingest", json=BODY).json()
    db_session.info["sync_apply"] = True
    try:
        db_session.get(Job, uuid.UUID(first["id"])).handover = "offered"
        db_session.commit()
    finally:
        db_session.info.pop("sync_apply", None)

    again = client.post("/api/jobs/ingest", json={**BODY, "apply_url": APPLY})

    assert again.status_code == 200 and again.json()["apply_url"] is None


def test_a_replica_refuses_a_patched_apply_link(client, db_session, sync_on):
    """The Companion's save of the page it ran on goes through the ordinary route: a job the other copy
    owns is not written here."""
    first = client.post("/api/jobs/ingest", json=BODY).json()
    _replica(db_session, first["id"])

    response = client.patch(f"/api/jobs/{first['id']}", json={"apply_url": APPLY})

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Job, uuid.UUID(first["id"])).apply_url is None


def test_an_owned_job_takes_a_patched_apply_link(client, db_session, sync_on):
    first = client.post("/api/jobs/ingest", json=BODY).json()

    response = client.patch(f"/api/jobs/{first['id']}", json={"apply_url": APPLY})

    assert response.status_code == 200 and response.json()["apply_url"] == APPLY
