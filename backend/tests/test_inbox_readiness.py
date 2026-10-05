"""Readiness on the Agent inbox's rows (agent-dashboard-design.md, Part 1)."""

from datetime import timedelta

import pytest

from app.config import settings
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.filled_answer import FilledAnswer
from app.models.types import utcnow
from app.services import autofill_profile, eeo_consent, filled_answers, inbox_readiness, knockout
from tests.test_proposals_models import _mk_job

TICKED_ALL = {"question": "Which languages?", "answer": ["a", "b", "c"], "options_count": 3,
              "source": "inferred"}


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _proposal(db_session, status="accepted", pdf=None, **job):
    job_row = _mk_job(db_session, **job)
    app_id = None
    if pdf is not None:
        app_row = Application(job_id=job_row.id, base_resume="swe", pdf_path=pdf)
        db_session.add(app_row)
        db_session.flush()
        app_id = app_row.id
    prop = ApplicationProposal(job_id=job_row.id, status=status, application_id=app_id)
    db_session.add(prop)
    db_session.commit()
    return prop, job_row


def test_tailored_follows_the_linked_application_pdf(db_session):
    rows = [_proposal(db_session, pdf="/x.pdf"), _proposal(db_session, pdf=""),
            _proposal(db_session)]
    got = inbox_readiness.for_proposals(db_session, rows)
    assert [got[p.id]["tailored"] for p, _ in rows] == [True, False, None]


def test_history_rows_get_no_readiness(db_session):
    rows = [_proposal(db_session, status=s)
            for s in ("submitted", "rejected", "expired", "submission_uncertain")]
    assert inbox_readiness.for_proposals(db_session, rows) == {}


def test_to_check_counts_the_flagged_answers(db_session):
    prop, job = _proposal(db_session, status="approved")
    db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[TICKED_ALL]))
    db_session.commit()
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]


def test_a_conflicting_knockout_names_its_kind(db_session, monkeypatch):
    monkeypatch.setattr(knockout, "scan_job", lambda job, **_: {
        "status": "conflict", "checks": [{"kind": "salary", "result": "pass"},
                                         {"kind": "on_site", "result": "conflict"}]})
    prop, job = _proposal(db_session)
    assert inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]["knockout"] == "on_site"


def test_the_profile_is_read_once_per_batch(db_session, monkeypatch):
    calls = []
    real = knockout.scan_args
    monkeypatch.setattr(knockout, "scan_args", lambda s: calls.append(1) or real(s))
    rows = [_proposal(db_session) for _ in range(3)]
    inbox_readiness.for_proposals(db_session, rows)
    assert calls == [1]


def test_a_row_that_fails_gets_null_and_the_rest_still_read(db_session, monkeypatch, caplog):
    rows = [_proposal(db_session), _proposal(db_session)]
    bad_job = rows[0][1]
    real = knockout.scan_job

    def scan(job, **kw):
        if job.id == bad_job.id:
            raise RuntimeError("boom")
        return real(job, **kw)

    monkeypatch.setattr(knockout, "scan_job", scan)
    got = inbox_readiness.for_proposals(db_session, rows)
    assert got[rows[0][0].id] is None and got[rows[1][0].id] is not None
    assert f"readiness skipped for proposal {rows[0][0].id}" in caplog.text


@pytest.mark.parametrize("readiness, ready", [
    ({"tailored": True, "knockout": None, "to_check": 0}, True),
    ({"tailored": False, "knockout": None, "to_check": 0}, False),
    ({"tailored": None, "knockout": None, "to_check": 0}, False),
    ({"tailored": 1, "knockout": None, "to_check": 0}, False),
    ({"tailored": True, "knockout": "opt", "to_check": 0}, False),
    ({"tailored": True, "knockout": None, "to_check": 2}, False),
    (None, False),
])
def test_ready_means_tailored_no_knockout_nothing_to_check(readiness, ready):
    assert inbox_readiness.is_ready(readiness) is ready


@pytest.mark.parametrize("stale_link", [False, True])
def test_a_deleted_linked_application_is_not_tailored(db_session, stale_link):
    prop, job = _proposal(db_session, status="approved", pdf="/x.pdf")
    app_id = prop.application_id
    db_session.delete(db_session.get(Application, app_id))
    db_session.commit()
    db_session.refresh(prop)
    if stale_link:
        prop = ApplicationProposal(id=prop.id, job_id=job.id, status="approved",
                                   application_id=app_id)
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got == {"tailored": None, "knockout": None, "to_check": 0}
    assert inbox_readiness.is_ready(got) is False


def test_latest_answers_across_two_pages_match_the_receipt(db_session):
    prop, job = _proposal(db_session, status="approved", pdf="/x.pdf")
    now = utcnow()
    for index, (step, answer) in enumerate([
        ("/apply/1", ["a", "b", "c"]), ("/apply/2", ["a", "b", "c"]),
        ("/apply/1", ["a"]),
    ]):
        db_session.add(FilledAnswer(job_id=job.id, channel="agent", step=step,
                                    captured_at=now + timedelta(seconds=index),
                                    fields=[{**TICKED_ALL, "answer": answer}]))
    db_session.commit()
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]
    assert filled_answers.flag_count(db_session, job) == 1
    assert inbox_readiness.is_ready(got) is False


@pytest.mark.parametrize("profile", [{}, {"work_auth": None}, {"work_auth": {}}])
def test_missing_work_auth_keeps_the_incomplete_verdict(db_session, profile):
    autofill_profile.set_profile(profile, db_session)
    prop, job = _proposal(db_session, pdf="/x.pdf", work_authorization="citizen_or_gc_required")
    assert knockout.scan_for(db_session, job)["status"] == "incomplete_profile"
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got == {"tailored": True, "knockout": None, "to_check": 0}
    assert inbox_readiness.is_ready(got) is True


def test_an_explicit_empty_flag_profile_does_not_read_saved_values(db_session):
    autofill_profile.set_profile({"personal": {"first_name": "Ada"}}, db_session)
    job = _mk_job(db_session)
    facts, saved = filled_answers.flag_context(db_session, job, {})
    assert "personal.first_name" not in facts
    assert saved == set()
    assert "personal.first_name" in filled_answers.flag_context(db_session, job)[0]


def test_answered_jobs_share_one_disclosable_profile(db_session, monkeypatch):
    rows = [_proposal(db_session) for _ in range(3)]
    for _, job in rows:
        db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[TICKED_ALL]))
    db_session.commit()
    calls = []
    real = eeo_consent.disclosable_profile
    monkeypatch.setattr(eeo_consent, "disclosable_profile", lambda s: calls.append(1) or real(s))
    got = inbox_readiness.for_proposals(db_session, rows)
    assert [got[p.id]["to_check"] for p, _ in rows] == [1, 1, 1]
    assert calls == [1]


def test_one_answer_with_two_flags_counts_once(db_session):
    prop, job = _proposal(db_session, status="approved")
    field = {**TICKED_ALL, "question": "Are you authorized to work?"}
    db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[field]))
    db_session.commit()
    assert len(filled_answers.agent_flags(db_session, job)[0]["flags"]) == 2
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]
