from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.referral import Referral


def _override_db(db_session):
    def _inner():
        yield db_session
    return _inner


def test_create_and_list_referral(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        create = client.post(
            "/api/referrals",
            json={"company": "Acme", "careers_url": "https://acme.example/careers"},
        )
        assert create.status_code == 200
        created = create.json()
        assert created["company"] == "Acme"
        assert created["careers_url"].startswith("https://acme.example")
        assert created["applications_count"] == 0

        listed = client.get("/api/referrals")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_update_and_delete_referral(db_session):
    referral = Referral(company="Acme", careers_url="https://acme.example/careers")
    db_session.add(referral)
    db_session.commit()
    db_session.refresh(referral)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        updated = client.put(
            f"/api/referrals/{referral.id}",
            json={"contact_name": "Jane"},
        )
        assert updated.status_code == 200
        assert updated.json()["contact_name"] == "Jane"

        deleted = client.delete(f"/api/referrals/{referral.id}")
        assert deleted.status_code == 204

        listed = client.get("/api/referrals")
        assert listed.json() == []
    finally:
        app.dependency_overrides.clear()


def test_create_referral_rejects_bad_url(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/referrals",
            json={"company": "Acme", "careers_url": "not-a-url"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_delete_referral_nulls_linked_applications(db_session):
    from app.models.job import Job
    from app.models.application import Application
    from datetime import UTC, datetime

    job = Job(
        raw_text="Need Python",
        raw_text_hash="ref-fk-test",
        title="Engineer",
        company="Acme",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    referral = Referral(company="Acme", careers_url="https://acme.example/careers")
    db_session.add(referral)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(referral)

    application = Application(
        job_id=job.id, base_resume="hybrid", status="draft", referral_id=referral.id
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        deleted = client.delete(f"/api/referrals/{referral.id}")
        assert deleted.status_code == 204

        check = client.get(f"/api/applications/{application.id}")
        assert check.status_code == 200
        assert check.json()["referral_id"] is None
    finally:
        app.dependency_overrides.clear()
