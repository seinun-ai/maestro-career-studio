"""Late linking (design §1): a job's receipt rows posted before it had an application are
linked, for their base, when one is created, marked applied, or submitted by an agent."""

import copy
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.application import Application
from app.models.filled_answer import FilledAnswer
from app.models.job import Job
from app.routers import applications
from app.services import application_writes, filled_answers
from app.services import proposals as svc
from tests.ats.fixtures import SAMPLE_RESUME
from tests.test_proposal_state_machine import (
    _final_review_evidence,
    _mk_proposal,
    _receipt_evidence,
)
from tests.test_proposals_models import _mk_job

client = TestClient(app)


def _unlinked(db_session, job, fields=None, base_resume=None, captured_at=None):
    extra = {"captured_at": captured_at} if captured_at else {}
    row = FilledAnswer(job_id=job.id, channel="companion", fields=fields or [],
                       base_resume=base_resume, **extra)
    db_session.add(row)
    db_session.commit()
    return row


def _app(db_session, job, base="hybrid", **extra):
    app_row = Application(job_id=job.id, base_resume=base, **extra)
    db_session.add(app_row)
    db_session.flush()
    return app_row


def _version(db_session, app_row, at, summary="Ada"):
    """A resume version of the application (its content is `summary`), stamped `at`."""
    _, version = application_writes.stage_resume_update(
        db_session, app_row, {"summary": summary}, source="import")
    version.created_at = at
    db_session.commit()
    return version


def _upload(slot, version=None, source="upload"):
    return {"question": f"{slot} file", "answer": "file.pdf", "source": source,
            "slot": slot, "version": version}


def _link(db_session, app_row):
    count = filled_answers.link_unlinked(db_session, app_row)
    db_session.commit()
    return count


def _owner(db_session, row):
    db_session.expire_all()
    return db_session.get(FilledAnswer, row.id).application_id


def test_creating_an_application_through_from_base_links_the_jobs_rows(db_session, monkeypatch):
    monkeypatch.setattr(applications.base_resume_data, "load_base_resume",
                        lambda slug, session=None: copy.deepcopy(SAMPLE_RESUME))
    job, other = _mk_job(db_session), _mk_job(db_session)
    mine, theirs = _unlinked(db_session, job), _unlinked(db_session, other)
    res = client.post("/api/applications/from-base",
                      json={"job_id": str(job.id), "base_resume": "hybrid", "ops": []})
    assert res.status_code == 200
    assert str(_owner(db_session, mine)) == res.json()["id"]
    assert _owner(db_session, theirs) is None


def test_rebuilding_an_application_does_not_claim_rows(db_session, monkeypatch):
    monkeypatch.setattr(applications.base_resume_data, "load_base_resume",
                        lambda slug, session=None: copy.deepcopy(SAMPLE_RESUME))
    job = _mk_job(db_session)
    _app(db_session, job)
    db_session.commit()
    row = _unlinked(db_session, job)
    res = client.post("/api/applications/from-base",
                      json={"job_id": str(job.id), "base_resume": "hybrid", "ops": []})
    assert res.status_code == 200
    assert _owner(db_session, row) is None


def test_a_row_already_linked_keeps_its_application(db_session):
    job = _mk_job(db_session)
    first = _app(db_session, job)
    row = FilledAnswer(job_id=job.id, application_id=first.id, channel="agent", fields=[])
    db_session.add(row)
    db_session.commit()
    second = _app(db_session, job)
    _link(db_session, second)
    assert _owner(db_session, row) == first.id


def test_rows_link_to_the_application_of_their_base(db_session):
    job = _mk_job(db_session)
    ds, swe = _app(db_session, job, "data_scientist"), _app(db_session, job, "swe")
    ds_row = _unlinked(db_session, job, base_resume="data_scientist")
    swe_row = _unlinked(db_session, job, base_resume="swe")
    _link(db_session, swe)
    _link(db_session, ds)
    assert (_owner(db_session, ds_row), _owner(db_session, swe_row)) == (ds.id, swe.id)


def test_a_row_without_a_base_links_only_to_the_jobs_sole_application(db_session):
    job = _mk_job(db_session)
    first = _app(db_session, job, "data_scientist")
    row = _unlinked(db_session, job)
    assert _link(db_session, first) == 1
    assert _owner(db_session, row) == first.id


def test_a_row_without_a_base_stays_unlinked_when_the_job_has_two_applications(db_session):
    job = _mk_job(db_session)
    first, second = _app(db_session, job, "data_scientist"), _app(db_session, job, "swe")
    row = _unlinked(db_session, job)
    assert _link(db_session, first) == 0
    assert _link(db_session, second) == 0
    assert _owner(db_session, row) is None


def test_marking_applied_links_the_jobs_rows(db_session):
    job = _mk_job(db_session)
    app_row = _app(db_session, job, status="draft")
    db_session.commit()
    row = _unlinked(db_session, job)
    assert client.patch(f"/api/applications/{app_row.id}", json={"status": "applied"}).status_code == 200
    assert _owner(db_session, row) == app_row.id


def test_an_agent_submit_links_the_jobs_rows(db_session):
    prop = _mk_proposal(db_session)
    row = _unlinked(db_session, db_session.get(Job, prop.job_id))
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, prop, "submitted")
    assert _owner(db_session, row) == prop.application_id


def test_late_linking_stamps_the_version_the_application_had_when_the_row_was_posted(db_session):
    job = _mk_job(db_session)
    app_row = _app(db_session, job)
    now = datetime.now(UTC)
    _version(db_session, app_row, now - timedelta(hours=2))
    row = _unlinked(db_session, job, [
        _upload("resume"), _upload("cover_letter"), _upload("resume", source="profile"),
        _upload("resume", version=7),
    ], captured_at=now - timedelta(hours=1))
    _link(db_session, app_row)
    db_session.expire_all()
    versions = [field["version"] for field in db_session.get(FilledAnswer, row.id).fields]
    assert versions == [1, None, None, 7]


def test_a_later_edit_does_not_restamp_an_earlier_upload(db_session):
    """v1 exists, the row is posted, an edit makes v2, then the row is linked: the upload
    went up with v1, so v1 it stays."""
    job = _mk_job(db_session)
    app_row = _app(db_session, job)
    now = datetime.now(UTC)
    _version(db_session, app_row, now - timedelta(hours=3))
    row = _unlinked(db_session, job, [_upload("resume")], captured_at=now - timedelta(hours=2))
    _version(db_session, app_row, now - timedelta(hours=1), "Ada, edited")
    _link(db_session, app_row)
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).fields[0]["version"] == 1


def test_a_row_that_predates_every_version_is_left_unstamped(db_session):
    job = _mk_job(db_session)
    now = datetime.now(UTC)
    row = _unlinked(db_session, job, [_upload("resume")], captured_at=now - timedelta(hours=2))
    app_row = _app(db_session, job)
    _version(db_session, app_row, now - timedelta(hours=1), "Ada, edited")
    _link(db_session, app_row)
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).fields[0]["version"] is None


def test_linking_without_a_resume_version_leaves_the_stamp_empty(db_session):
    job = _mk_job(db_session)
    row = _unlinked(db_session, job, [_upload("resume")])
    app_row = _app(db_session, job, status="draft")
    db_session.commit()
    assert client.patch(f"/api/applications/{app_row.id}", json={"status": "applied"}).status_code == 200
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).fields[0]["version"] is None
