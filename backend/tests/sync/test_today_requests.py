"""Today's Next up passes over a job whose change is on its way to the other copy: the Skip that was
"Sent at the next sync" moves the card on now, not after the other copy answers."""

import uuid

from sqlalchemy import select

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.models.sync import SyncRequest

QUEUED = {"queued": True, "detail": "Sent at the next sync."}


def _replicated(db, *rows):
    """Store rows the way a sync round does, so the guard lets a replica's rows in."""
    db.info["sync_apply"] = True
    try:
        for row in rows:
            db.add(row)
            db.flush()
        db.commit()
    finally:
        db.info.pop("sync_apply", None)


def _job(title, owner):
    return Job(id=uuid.uuid4(), raw_text=f"JD {uuid.uuid4().hex}", raw_text_hash=uuid.uuid4().hex,
               title=title, company="Example employer", owner_machine=owner)


def _ready(db, title, score, owner=None) -> Application:
    """A draft with its PDF ready and a tailored match score, on this copy's job or the other's."""
    job = _job(title, owner)
    application = Application(id=uuid.uuid4(), job_id=job.id, base_resume="alpha", status="draft",
                              customized_json={"basics": {"name": "Sample Person"}},
                              pdf_path=f"/tmp/{uuid.uuid4().hex}.pdf")
    _replicated(db, job, application, AtsScore(
        job_id=job.id, target_type="application", target_id=str(application.id),
        application_id=application.id, phase="tailored", composite=score, subscores_json={},
        skill_table_json=[], config_version="c1", engine_version="e1"))
    return application


def _question(db, owner=None) -> ApplicationProposal:
    job = _job("UX Researcher", owner)
    proposal = ApplicationProposal(job_id=job.id, status="needs_decision", proposed_by="claude-ai",
                                   fit_json={"chosen_base": "alpha", "scores": {"alpha": 72}},
                                   reason="Which start date should I give?")
    _replicated(db, job, proposal)
    return proposal


def _next_up(client):
    response = client.get("/api/today")
    assert response.status_code == 200
    return response.json()["next_up"]


def test_a_skip_sent_to_the_other_copy_moves_next_up_on(client, db_session, sync_on):
    bots = _ready(db_session, "Data Scientist", 72, owner="other-copy")
    mine = _ready(db_session, "Data Analyst", 60)
    assert _next_up(client)["application_id"] == str(bots.id)

    response = client.patch(f"/api/applications/{bots.id}", json={"status": "skipped"})
    assert (response.status_code, response.json()) == (202, QUEUED)

    assert _next_up(client)["application_id"] == str(mine.id)
    db_session.refresh(bots)
    assert bots.status == "draft"  # the replica changes only when the other copy answers


def test_a_sent_skip_still_waits_and_a_refused_one_comes_back(client, db_session, sync_on):
    bots = _ready(db_session, "Data Scientist", 72, owner="other-copy")
    assert client.patch(f"/api/applications/{bots.id}", json={"status": "skipped"}).status_code == 202
    request = db_session.scalars(select(SyncRequest)).one()

    request.status = "sent"
    db_session.commit()
    assert _next_up(client) is None

    request.status = "refused"
    db_session.commit()
    assert _next_up(client)["application_id"] == str(bots.id)


def test_a_notes_change_on_its_way_keeps_the_job_next_up(client, db_session, sync_on):
    bots = _ready(db_session, "Data Scientist", 72, owner="other-copy")
    response = client.patch(f"/api/applications/{bots.id}", json={"notes": "Ask about the team"})
    assert (response.status_code, response.json()) == (202, QUEUED)
    assert _next_up(client)["application_id"] == str(bots.id)


def test_a_decision_sent_to_the_other_copy_moves_its_question_on(client, db_session, sync_on):
    bots = _question(db_session, owner="other-copy")
    mine = _question(db_session)
    # Needs you lists newest first: this copy's question is newer, so answer it first.
    assert _next_up(client)["proposal_id"] == str(mine.id)
    db_session.delete(mine)
    db_session.commit()
    assert _next_up(client)["proposal_id"] == str(bots.id)

    response = client.patch(f"/api/proposals/{bots.id}", json={
        "status": "rejected", "reason": "Not the right team", "consent": {"channel": "frontend"}})
    assert (response.status_code, response.json()) == (202, QUEUED)
    assert _next_up(client) is None
