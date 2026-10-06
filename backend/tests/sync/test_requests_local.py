"""A write to the other copy's job becomes a request, through the routes the user already uses."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.db import get_db
from app.main import app
from app.services.sync import requests, status

QUEUED = {"queued": True, "detail": "Sent at the next sync."}
CONSENT = {"channel": "frontend", "note": "triage"}
OFFERED = "This job is on its way to your bot. Use Keep it here to keep working on it."


@pytest.fixture
def client(db_session):
    def override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def seeding_is_a_sync_apply(db_session):
    """Seed rows the guard would refuse, the way an applied bundle writes them."""
    db_session.info["sync_apply"] = True
    yield
    db_session.info.pop("sync_apply", None)


def _live(db):
    """From here on the session writes as a user, not as an applied bundle."""
    db.info.pop("sync_apply", None)


def _job(db, owner="other-machine", handover=None):
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex,
                     title="Engineer", company="Example employer",
                     owner_machine=owner, handover=handover)
    db.add(job)
    db.flush()
    return job


def _case(db, owner="other-machine", handover=None, live=True):
    job = _job(db, owner, handover)
    application = models.Application(job_id=job.id, base_resume="base", status="draft")
    db.add(application)
    db.flush()
    proposal = models.ApplicationProposal(job_id=job.id, application_id=application.id,
                                          status="accepted")
    db.add(proposal)
    db.commit()
    if live:
        _live(db)
    return job, application, proposal


def _requests(db):
    db.expire_all()
    return list(db.scalars(select(models.SyncRequest)))


def _patch_proposal(client, proposal, **body):
    return client.patch(f"/api/proposals/{proposal.id}", json=body)


def test_a_transition_on_a_non_owned_job_is_queued_not_applied(client, db_session, sync_on):
    job, _, proposal = _case(db_session)
    response = _patch_proposal(client, proposal, status="rejected", consent=CONSENT,
                               reason="Not for me")
    assert (response.status_code, response.json()) == (202, QUEUED)
    db_session.refresh(proposal)
    assert proposal.status == "accepted"
    (row,) = _requests(db_session)
    assert (row.kind, row.origin, row.status, row.job_id) == (
        "proposal_transition", "local", "pending", job.id)
    assert row.payload_json == {"proposal_id": str(proposal.id), "to": "rejected",
                                "reason": "Not for me", "consent": {"channel": "frontend",
                                                                     "note": "triage"}}


def test_a_status_and_notes_patch_is_queued_not_applied(client, db_session, sync_on):
    job, application, _ = _case(db_session)
    response = client.patch(f"/api/applications/{application.id}",
                            json={"status": "applied", "notes": "Sent it myself"})
    assert (response.status_code, response.json()) == (202, QUEUED)
    db_session.refresh(application)
    assert (application.status, application.notes) == ("draft", None)
    (row,) = _requests(db_session)
    assert (row.kind, row.origin, row.status, row.job_id) == (
        "application_patch", "local", "pending", job.id)
    assert row.payload_json == {"application_id": str(application.id),
                                "fields": {"status": "applied", "notes": "Sent it myself"}}


def test_take_over_is_queued_with_an_empty_payload(db_session, sync_on):
    job = _job(db_session)
    _live(db_session)
    requests.enqueue_take_over(db_session, job.id)
    (row,) = _requests(db_session)
    assert (row.kind, row.origin, row.status, row.job_id, row.payload_json) == (
        "take_over", "local", "pending", job.id, {})


@pytest.mark.parametrize("extra", [{"template_id": "classic"}, {"applied_at": "2026-10-01T00:00:00Z"},
                                   {"customized_json": None}, {"referral_id": None}])
def test_an_application_patch_with_another_field_is_refused_and_queues_nothing(
        client, db_session, sync_on, extra):
    _, application, _ = _case(db_session)
    response = client.patch(f"/api/applications/{application.id}",
                            json={"status": "applied", **extra})
    assert response.status_code == 409
    assert response.json()["owner"] == "bot"
    assert _requests(db_session) == []
    db_session.refresh(application)
    assert application.status == "draft"


def test_a_proposal_patch_with_another_field_is_refused_and_queues_nothing(
        client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    response = _patch_proposal(client, proposal, status="rejected", consent=CONSENT,
                               fit={"chosen_base": "hybrid"})
    assert response.status_code == 409
    assert _requests(db_session) == []
    db_session.refresh(proposal)
    assert proposal.status == "accepted"


def test_an_offered_job_stays_a_409_and_is_never_queued(client, db_session, sync_on):
    _, application, proposal = _case(db_session, owner=None, handover="offered")
    first = _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    second = client.patch(f"/api/applications/{application.id}", json={"notes": "x"})
    assert (first.status_code, second.status_code) == (409, 409)
    assert first.json()["detail"] == second.json()["detail"] == OFFERED
    assert _requests(db_session) == []


def test_an_offered_job_with_an_explicit_owner_is_never_queued_either(client, db_session, sync_on):
    machine = status.machine_id(db_session)
    _, _, proposal = _case(db_session, owner=machine, handover="offered")
    response = _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    assert (response.status_code, response.json()["detail"]) == (409, OFFERED)
    assert _requests(db_session) == []


@pytest.mark.parametrize("own", ["unset", "machine"])
def test_an_owned_job_is_changed_normally(client, db_session, sync_on, own):
    owner = None if own == "unset" else status.machine_id(db_session)
    _, application, proposal = _case(db_session, owner=owner)
    rejected = _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    patched = client.patch(f"/api/applications/{application.id}", json={"notes": "Mine"})
    assert (rejected.status_code, patched.status_code) == (200, 200)
    assert rejected.json()["status"] == "rejected"
    assert patched.json()["notes"] == "Mine"
    assert _requests(db_session) == []


def test_the_always_on_copy_queues_requests_on_its_laptops_jobs(client, db_session, sync_remote):
    job, _, proposal = _case(db_session)
    response = _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    assert (response.status_code, response.json()) == (202, QUEUED)
    (row,) = _requests(db_session)
    assert (row.kind, row.origin, row.job_id) == ("proposal_transition", "local", job.id)


def test_sync_off_changes_nothing(client, db_session):
    _, application, proposal = _case(db_session)
    rejected = _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    patched = client.patch(f"/api/applications/{application.id}",
                           json={"status": "applied", "template_id": None})
    assert (rejected.status_code, patched.status_code) == (200, 200)
    assert _requests(db_session) == []


def test_bulk_transition_applies_owned_queues_other_and_refuses_offered(
        client, db_session, sync_on):
    _, _, mine = _case(db_session, owner=None, live=False)
    other_job, _, theirs = _case(db_session, live=False)
    _, _, offered = _case(db_session, owner=None, handover="offered", live=False)
    _live(db_session)
    ids = [str(mine.id), str(theirs.id), str(offered.id)]
    response = client.post("/api/proposals/bulk-transition", json={
        "ids": ids, "status": "rejected", "consent": CONSENT, "reason": "Not for me"})
    assert response.status_code == 200
    results = {row["id"]: row for row in response.json()["results"]}
    assert results[ids[0]]["ok"] and results[ids[0]]["status"] == "rejected"
    assert results[ids[1]] == {"id": ids[1], "ok": True, "status": None,
                               "detail": "Sent at the next sync."}
    assert not results[ids[2]]["ok"] and results[ids[2]]["detail"] == OFFERED
    for row in (mine, theirs, offered):
        db_session.refresh(row)
    assert (mine.status, theirs.status, offered.status) == ("rejected", "accepted", "accepted")
    (row,) = _requests(db_session)
    assert (row.kind, row.job_id, row.payload_json) == (
        "proposal_transition", other_job.id,
        {"proposal_id": str(theirs.id), "to": "rejected", "reason": "Not for me",
         "consent": {"channel": "frontend", "note": "triage"}})


def test_bulk_transition_with_sync_off_is_unchanged(client, db_session):
    _, _, prop = _case(db_session)
    response = client.post("/api/proposals/bulk-transition", json={
        "ids": [str(prop.id)], "status": "rejected", "consent": CONSENT})
    assert response.json()["results"][0]["ok"]
    assert _requests(db_session) == []


def test_a_queued_decision_carries_the_consent_exactly_as_received(client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    _patch_proposal(client, proposal, status="rejected", consent={"channel": "mcp"})
    (row,) = _requests(db_session)
    assert row.payload_json["consent"] == {"channel": "mcp"}


def test_a_transition_that_needs_no_consent_stores_none(client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    response = _patch_proposal(client, proposal, status="needs_human", reason="Login wall")
    assert response.status_code == 202
    (row,) = _requests(db_session)
    assert row.payload_json == {"proposal_id": str(proposal.id), "to": "needs_human",
                                "reason": "Login wall"}


@pytest.mark.parametrize("extra", [{"fit": {"chosen_base": "x"}}, {"attested": False},
                                   {"intervention": {"kind": "login"}},
                                   {"application_id": str(uuid.uuid4())}])
def test_nothing_outside_the_allowlist_reaches_a_request(client, db_session, sync_on, extra):
    """Fit, intervention (can hold page details), attestation and links are never forwarded:
    a PATCH carrying one is a 409, so no payload can hold them."""
    _, _, proposal = _case(db_session)
    response = _patch_proposal(client, proposal, status="rejected", consent=CONSENT, **extra)
    assert response.status_code == 409
    assert _requests(db_session) == []


# Repeated clicks while the 202 leaves the replica unchanged must not stack requests.

def _patch_application(client, application, **fields):
    return client.patch(f"/api/applications/{application.id}", json=fields)


def test_skip_then_accept_leaves_one_pending_request_saying_accepted(client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    _patch_proposal(client, proposal, status="rejected", consent=CONSENT, reason="Not for me")
    _patch_proposal(client, proposal, status="accepted", consent={"channel": "mcp"})
    (row,) = _requests(db_session)
    assert row.status == "pending"
    assert row.payload_json == {"proposal_id": str(proposal.id), "to": "accepted",
                                "reason": None, "consent": {"channel": "mcp"}}


def test_accepting_twice_leaves_one_request(client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    for _ in range(2):
        assert _patch_proposal(client, proposal, status="accepted", consent=CONSENT).status_code == 202
    assert len(_requests(db_session)) == 1


def test_a_later_decision_without_consent_drops_the_earlier_consent(client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    _patch_proposal(client, proposal, status="needs_human", reason="Login wall")
    (row,) = _requests(db_session)
    assert row.payload_json == {"proposal_id": str(proposal.id), "to": "needs_human",
                                "reason": "Login wall"}


def test_decisions_on_two_proposals_stay_two_requests(client, db_session, sync_on):
    _, _, first = _case(db_session, live=False)
    _, _, second = _case(db_session, live=False)
    _live(db_session)
    _patch_proposal(client, first, status="rejected", consent=CONSENT)
    _patch_proposal(client, second, status="rejected", consent=CONSENT)
    assert len(_requests(db_session)) == 2


def test_three_identical_notes_blurs_make_one_request(client, db_session, sync_on):
    _, application, _ = _case(db_session)
    for _ in range(3):
        assert _patch_application(client, application, notes="Call on Friday").status_code == 202
    (row,) = _requests(db_session)
    assert row.payload_json == {"application_id": str(application.id),
                                "fields": {"notes": "Call on Friday"}}


def test_notes_then_status_merge_into_one_request_and_later_values_win(
        client, db_session, sync_on):
    _, application, _ = _case(db_session)
    _patch_application(client, application, notes="first")
    _patch_application(client, application, status="applied")
    _patch_application(client, application, notes="second")
    (row,) = _requests(db_session)
    assert row.payload_json == {"application_id": str(application.id),
                                "fields": {"notes": "second", "status": "applied"}}


def test_a_bulk_call_with_the_same_id_twice_stores_one_request(client, db_session, sync_on):
    _, _, proposal = _case(db_session)
    response = client.post("/api/proposals/bulk-transition", json={
        "ids": [str(proposal.id), str(proposal.id)], "status": "rejected", "consent": CONSENT})
    assert response.status_code == 200
    assert len(_requests(db_session)) == 1


def test_a_second_take_over_for_the_same_job_is_not_added(db_session, sync_on):
    job = _job(db_session)
    _live(db_session)
    requests.enqueue_take_over(db_session, job.id)
    requests.enqueue_take_over(db_session, job.id)
    assert len(_requests(db_session)) == 1


def test_a_sent_request_is_never_changed_and_a_new_click_adds_a_second(
        client, db_session, sync_on):
    _, application, proposal = _case(db_session)
    job_id = proposal.job_id
    _patch_proposal(client, proposal, status="rejected", consent=CONSENT)
    _patch_application(client, application, notes="one")
    requests.enqueue_take_over(db_session, job_id)
    for row in _requests(db_session):
        row.status = "sent"
    db_session.commit()
    _patch_proposal(client, proposal, status="accepted", consent=CONSENT)
    _patch_application(client, application, notes="two")
    requests.enqueue_take_over(db_session, job_id)
    rows = _requests(db_session)
    assert sorted(r.status for r in rows) == ["pending"] * 3 + ["sent"] * 3
    sent = [r for r in rows if r.status == "sent"]
    assert {r.payload_json.get("to") for r in sent if r.kind == "proposal_transition"} == {"rejected"}
    assert [r.payload_json["fields"] for r in sent if r.kind == "application_patch"] == [
        {"notes": "one"}]
