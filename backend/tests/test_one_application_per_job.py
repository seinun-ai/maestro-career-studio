"""A job has one application: a tailor or a from-base with another base resume updates the job's
newest application in place (its base moves with it) instead of inserting a second one, and
version history keeps the draft it replaced (docs/entities/application.md, reuse policy)."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.application import Application
from app.models.referral import Referral
from tests.ats.fixtures import SAMPLE_RESUME
from tests.test_tailoring_sessions_router import (
    SALESFORCE_RESOLUTION,
    _mock_tailor_llm,
    _open_session,
    _seed_base,
    _seed_job,
    _tailor,
)

BASE_A = "data_scientist"
BASE_B = "ml_engineer"


def _other_resume():
    """Base B differs from base A, so switching writes a new version, not a no-op."""
    resume = deepcopy(SAMPLE_RESUME)
    resume["summary"] = "Machine learning engineer who ships models to production."
    return resume


def _two_bases(db_session, tmp_path, monkeypatch):
    _seed_base(db_session, tmp_path, monkeypatch, slug=BASE_A)
    _seed_base(db_session, tmp_path, monkeypatch, slug=BASE_B, resume_json=_other_resume())


def _job_apps(db_session, job):
    db_session.expire_all()
    return db_session.scalars(select(Application).where(Application.job_id == job.id)).all()


def _from_base(client, job, slug):
    response = client.post(
        "/api/applications/from-base",
        json={"job_id": str(job.id), "base_resume": slug, "ops": []},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tailored_on(client, job, slug):
    created = _open_session(client, job, slug, [SALESFORCE_RESOLUTION])
    response = _tailor(client, created["id"])
    assert response.status_code == 200, response.text
    return response.json()


def test_tailoring_with_another_base_replaces_the_jobs_draft(
    db_session, tmp_path, monkeypatch, client
):
    job = _seed_job(db_session)
    _two_bases(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    _tailored_on(client, job, BASE_A)
    [app_a] = _job_apps(db_session, job)

    _tailored_on(client, job, BASE_B)

    apps = _job_apps(db_session, job)
    assert len(apps) == 1 and apps[0].id == app_a.id and apps[0].base_resume == BASE_B
    versions = client.get(f"/api/resume-versions/application/{app_a.id}").json()
    newest = max(versions, key=lambda row: row["version_number"])
    assert newest["version_number"] == 2 and newest["summary"].startswith("Switched to ")


def test_from_base_with_another_base_updates_in_place(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    _two_bases(db_session, tmp_path, monkeypatch)
    app_a = _from_base(client, job, BASE_A)

    body = _from_base(client, job, BASE_B)

    assert body["id"] == app_a["id"] and body["base_resume"] == BASE_B
    assert len(_job_apps(db_session, job)) == 1


def test_the_old_draft_is_in_version_history(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    _two_bases(db_session, tmp_path, monkeypatch)
    app_a = _from_base(client, job, BASE_A)
    _from_base(client, job, BASE_B)

    versions = client.get(f"/api/resume-versions/application/{app_a['id']}").json()
    by_number = {row["version_number"]: row for row in versions}
    assert set(by_number) == {1, 2}
    assert by_number[2]["summary"].startswith("Switched to ")
    first = client.get(f"/api/resume-versions/application/{app_a['id']}/1").json()
    assert first["snapshot"]["summary"] == SAMPLE_RESUME["summary"]


def test_a_rebuild_on_the_same_base_still_says_rebuilt(db_session, tmp_path, monkeypatch, client):
    """Only a change of base reads "Switched to"; the same base keeps "Rebuilt from"."""
    job = _seed_job(db_session)
    _two_bases(db_session, tmp_path, monkeypatch)
    app_a = _from_base(client, job, BASE_A)
    client.post(
        "/api/applications/from-base",
        json={
            "job_id": str(job.id),
            "base_resume": BASE_A,
            "ops": [{"kind": "replace_summary", "value": "A rebuilt summary for the same base."}],
        },
    )

    versions = client.get(f"/api/resume-versions/application/{app_a['id']}").json()
    newest = max(versions, key=lambda row: row["version_number"])
    assert newest["version_number"] == 2
    assert newest["summary"].startswith("Rebuilt from ")


def test_status_notes_and_referral_survive_a_resume_switch(
    db_session, tmp_path, monkeypatch, client
):
    job = _seed_job(db_session)
    _two_bases(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)
    _tailored_on(client, job, BASE_A)
    [app_a] = _job_apps(db_session, job)
    referral = Referral(company="Acme", careers_url="https://acme.example/careers", contact_name="Pat Lee")
    db_session.add(referral)
    db_session.flush()
    applied_at = datetime(2026, 3, 1, tzinfo=UTC)
    app_a.status = "applied"
    app_a.applied_at = applied_at
    app_a.notes = "keep me"
    app_a.referral_id = referral.id
    db_session.commit()

    _tailored_on(client, job, BASE_B)

    [after] = _job_apps(db_session, job)
    assert after.id == app_a.id and after.base_resume == BASE_B
    assert after.status == "applied"
    assert after.applied_at == applied_at
    assert after.notes == "keep me"
    assert after.referral_id == referral.id


def test_a_legacy_job_with_two_applications_updates_the_newest(
    db_session, tmp_path, monkeypatch, client
):
    """Applications from before the rule stay (no migration); the newest one, by
    `created_at desc, id desc` like the job detail, takes the new base."""
    job = _seed_job(db_session)
    _two_bases(db_session, tmp_path, monkeypatch)
    _seed_base(db_session, tmp_path, monkeypatch, slug="data_engineer")
    tie = datetime(2026, 5, 1, tzinfo=UTC)
    rows = [
        Application(job_id=job.id, base_resume=slug, status="draft", created_at=tie)
        for slug in (BASE_A, BASE_B)
    ]
    db_session.add_all(rows)
    db_session.commit()
    newer = max(rows, key=lambda row: row.id.hex)
    older = next(row for row in rows if row is not newer)
    older_base = older.base_resume

    body = _from_base(client, job, "data_engineer")

    assert UUID(body["id"]) == newer.id and body["base_resume"] == "data_engineer"
    apps = {row.id: row for row in _job_apps(db_session, job)}
    assert len(apps) == 2
    assert apps[older.id].base_resume == older_base
