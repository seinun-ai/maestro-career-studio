"""Readiness on the inbox list and the arrivals strip's counts."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.filled_answer import FilledAnswer
from app.models.types import utcnow
from app.services import proposals
from tests.test_proposals_models import _mk_job

client = TestClient(app)


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _prop(db_session, status, **cols):
    prop = ApplicationProposal(job_id=_mk_job(db_session).id, status=status, **cols)
    db_session.add(prop)
    db_session.commit()
    return prop


def _link_pdf(db_session, prop, path="/x.pdf"):
    app_row = Application(job_id=prop.job_id, base_resume="swe", pdf_path=path)
    db_session.add(app_row)
    db_session.flush()
    prop.application_id = app_row.id
    db_session.commit()


def test_the_list_carries_readiness_for_open_rows_only(db_session):
    open_id = _prop(db_session, "accepted").id
    done_id = _prop(db_session, "submitted").id
    items = {i["id"]: i for i in client.get("/api/proposals").json()["items"]}
    assert items[str(open_id)]["readiness"] == {"tailored": None, "knockout": None, "to_check": 0,
                                                 "base_country": None}
    assert items[str(done_id)]["readiness"] is None


def _summary(since):
    response = client.get("/api/proposals/summary", params={"since": since.isoformat()})
    assert response.status_code == 200, response.text
    body = response.json()
    return {k: body[k] for k in ("new", "ready", "needs_you", "applied_this_week")}


def test_the_summary_counts_new_needs_you_and_applied_this_week(db_session):
    since = utcnow() - timedelta(minutes=5)
    before = _summary(since)
    _prop(db_session, "pending_review")
    _prop(db_session, "needs_human")
    _prop(db_session, "accepted")  # queued, not tailored: not ready
    _prop(db_session, "submitted")
    _prop(db_session, "rejected", reason=proposals.APPLIED_MANUALLY)
    _prop(db_session, "rejected", reason="not a fit")
    _prop(db_session, "submitted", updated_at=utcnow() - timedelta(days=8))
    after = _summary(since)
    assert {k: after[k] - before[k] for k in after} == {
        "new": 7, "ready": 0, "needs_you": 1, "applied_this_week": 2}


def test_the_summary_defaults_to_the_last_day():
    before = utcnow()
    response = client.get("/api/proposals/summary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"since", "new", "ready", "needs_you", "applied_this_week"}
    since = datetime.fromisoformat(body["since"])
    assert before - timedelta(hours=24) <= since <= utcnow() - timedelta(hours=24)


def test_ready_counts_only_queued_rows_with_a_pdf_and_no_answer_flags(db_session):
    since = utcnow() - timedelta(minutes=5)
    before = _summary(since)
    for status, path in (("accepted", "/x.pdf"), ("accepted", ""), ("approved", "/x.pdf")):
        _link_pdf(db_session, _prop(db_session, status), path)
    _prop(db_session, "accepted")
    flagged = _prop(db_session, "accepted")
    _link_pdf(db_session, flagged)
    db_session.add(FilledAnswer(job_id=flagged.job_id, channel="agent", fields=[{
        "question": "Which languages?", "answer": ["a", "b", "c"],
        "options_count": 3, "source": "inferred",
    }]))
    db_session.commit()
    assert _summary(since)["ready"] - before["ready"] == 1


@pytest.mark.parametrize("status", ["needs_decision", "needs_human"])
def test_needs_you_counts_both_badge_statuses_regardless_of_since(db_session, status):
    since = utcnow() + timedelta(days=1)
    before = _summary(since)
    _prop(db_session, status)
    after = _summary(since)
    assert after["needs_you"] - before["needs_you"] == 1
    assert after["new"] == before["new"]


@pytest.mark.parametrize("offset", [None, 0, -5])
def test_new_uses_a_strict_boundary_and_accepts_naive_or_offset_times(db_session, offset):
    boundary = utcnow()
    for delta in (-1, 0, 1):
        _prop(db_session, "pending_review", created_at=boundary + timedelta(seconds=delta))
    since = (boundary.replace(tzinfo=None) if offset is None else
             boundary.astimezone(timezone(timedelta(hours=offset))))
    assert _summary(since)["new"] == 1
