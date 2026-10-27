
import pytest

from app.models.referral import Referral


def _override_db(db_session):
    def _inner():
        yield db_session
    return _inner


def test_create_and_list_referral(db_session, client):
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


def test_update_and_delete_referral(db_session, client):
    referral = Referral(company="Acme", careers_url="https://acme.example/careers")
    db_session.add(referral)
    db_session.commit()
    db_session.refresh(referral)

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


def test_create_referral_rejects_bad_url(db_session, client):
    response = client.post(
        "/api/referrals",
        json={"company": "Acme", "careers_url": "not-a-url"},
    )
    assert response.status_code == 422


def test_delete_referral_nulls_linked_applications(db_session, client):
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

    deleted = client.delete(f"/api/referrals/{referral.id}")
    assert deleted.status_code == 204

    check = client.get(f"/api/applications/{application.id}")
    assert check.status_code == 200
    assert check.json()["referral_id"] is None


def test_update_keeps_the_fields_a_caller_left_out(db_session, client):
    """PUT is a partial update: only the fields sent change (MCP save_referral relies on it)."""
    referral = Referral(
        company="Acme", careers_url="https://acme.example/careers", contact_name="Jane",
        notes="Met at a meetup",
    )
    db_session.add(referral)
    db_session.commit()
    db_session.refresh(referral)

    updated = client.put(f"/api/referrals/{referral.id}", json={"notes": "Intro sent"})

    assert updated.status_code == 200
    body = updated.json()
    assert (body["company"], body["careers_url"], body["contact_name"], body["notes"]) == (
        "Acme", "https://acme.example/careers", "Jane", "Intro sent",
    )


def test_update_of_an_unknown_referral_is_404(db_session, client):
    response = client.put(
        "/api/referrals/00000000-0000-4000-8000-000000000000", json={"notes": "x"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Referral not found"


def test_an_agent_adds_and_edits_a_referral_through_mcp(db_session, client, mcp_tools):
    """MCP save_referral against the real routes: a new referral, then an edit that keeps every
    field it was not given, then an unknown id refused."""
    from mcp.server.fastmcp.exceptions import ToolError

    created = mcp_tools.save_referral(
        "Northwind Labs", careers_url="https://northwind.example/jobs", contact_name="Amara Okafor",
    )
    assert created["applications_count"] == 0

    edited = mcp_tools.save_referral(
        "Northwind Labs", notes="Asked for an intro on Monday", referral_id=created["id"]
    )

    assert edited["id"] == created["id"]
    assert (edited["careers_url"], edited["contact_name"], edited["notes"]) == (
        "https://northwind.example/jobs", "Amara Okafor", "Asked for an intro on Monday",
    )
    assert [r["id"] for r in client.get("/api/referrals").json()] == [created["id"]]
    with pytest.raises(ToolError, match="404"):
        mcp_tools.save_referral("Northwind Labs", referral_id="00000000-0000-4000-8000-000000000000")
