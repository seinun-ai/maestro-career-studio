"""Late linking (design §1): a job's receipt rows posted before it had an application are
linked when one is created or rebuilt, marked applied, or submitted by an agent."""

from fastapi.testclient import TestClient

from app.main import app
from app.models.application import Application
from app.models.filled_answer import FilledAnswer
from app.models.job import Job
from app.services import application_writes
from app.services import proposals as svc
from tests.test_proposal_state_machine import (
    _final_review_evidence,
    _mk_proposal,
    _receipt_evidence,
)
from tests.test_proposals_models import _mk_job

client = TestClient(app)


def _unlinked(db_session, job, fields=None):
    row = FilledAnswer(job_id=job.id, channel="companion", fields=fields or [])
    db_session.add(row)
    db_session.commit()
    return row


def _app(db_session, job, **extra):
    app_row = Application(job_id=job.id, base_resume="hybrid", **extra)
    db_session.add(app_row)
    db_session.flush()
    return app_row


def _upload(slot, version=None, source="upload"):
    return {"question": f"{slot} file", "answer": "file.pdf", "source": source,
            "slot": slot, "version": version}


def test_creating_the_application_links_the_jobs_rows(db_session):
    job, other = _mk_job(db_session), _mk_job(db_session)
    mine, theirs = _unlinked(db_session, job), _unlinked(db_session, other)
    app_row = _app(db_session, job)
    application_writes.stage_resume_update(db_session, app_row, {"contact": {}}, source="import")
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(FilledAnswer, mine.id).application_id == app_row.id
    assert db_session.get(FilledAnswer, theirs.id).application_id is None


def test_a_row_already_linked_keeps_its_application(db_session):
    job = _mk_job(db_session)
    first = _app(db_session, job)
    row = FilledAnswer(job_id=job.id, application_id=first.id, channel="agent", fields=[])
    db_session.add(row)
    db_session.commit()
    second = _app(db_session, job)
    application_writes.stage_resume_update(db_session, second, {"contact": {}}, source="import")
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).application_id == first.id


def test_marking_applied_links_the_jobs_rows(db_session):
    job = _mk_job(db_session)
    app_row = _app(db_session, job, status="draft")
    db_session.commit()
    row = _unlinked(db_session, job)
    assert client.patch(f"/api/applications/{app_row.id}", json={"status": "applied"}).status_code == 200
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).application_id == app_row.id


def test_an_agent_submit_links_the_jobs_rows(db_session):
    prop = _mk_proposal(db_session)
    row = _unlinked(db_session, db_session.get(Job, prop.job_id))
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, prop, "submitted")
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).application_id == prop.application_id


def test_late_linking_stamps_the_resume_version_on_resume_uploads(db_session):
    job = _mk_job(db_session)
    row = _unlinked(db_session, job, [
        _upload("resume"), _upload("cover_letter"), _upload("resume", source="profile"),
        _upload("resume", version=7),
    ])
    app_row = _app(db_session, job)
    application_writes.stage_resume_update(db_session, app_row, {"contact": {}}, source="import")
    db_session.commit()
    db_session.expire_all()
    versions = [field["version"] for field in db_session.get(FilledAnswer, row.id).fields]
    assert versions == [1, None, None, 7]


def test_linking_without_a_resume_version_leaves_the_stamp_empty(db_session):
    job = _mk_job(db_session)
    row = _unlinked(db_session, job, [_upload("resume")])
    app_row = _app(db_session, job, status="draft")
    db_session.commit()
    assert client.patch(f"/api/applications/{app_row.id}", json={"status": "applied"}).status_code == 200
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).fields[0]["version"] is None
