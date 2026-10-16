from datetime import UTC, datetime, timedelta

from app.models.base_resume import BaseResume
from app.models.resume_version import ResumeVersion
from app.services import stage
from tests.ats.fixtures import SAMPLE_RESUME
from tests.stage_rows import make_application, make_base_score, make_job, make_session


def _rung_of_app(db_session, application):
    return stage.for_applications(db_session, [application])[application.id].rung


def test_rungs_are_ordered():
    assert stage.RUNGS == ("saved", "scored", "gaps", "tailored", "pdf_ready", "applied", "closed")


def test_nothing_in_nothing_out(db_session):
    assert stage.for_applications(db_session, []) == {}
    assert stage.for_job_rows(db_session, []) == {}
    assert stage.newest_applications(db_session, []) == {}


def test_a_saved_job_with_no_score_is_saved(db_session):
    job = make_job(db_session)
    out = stage.for_job_rows(db_session, [job])
    assert out[job.id] == stage.Stage("saved")


def test_a_scored_job_is_scored(db_session):
    job = make_job(db_session)
    make_base_score(db_session, job)
    assert stage.for_job_rows(db_session, [job])[job.id].rung == "scored"


def test_a_score_for_an_archived_base_does_not_make_a_job_scored(db_session):
    job = make_job(db_session)
    db_session.add(BaseResume(slug="old", data_json=SAMPLE_RESUME, archived_at=datetime.now(UTC)))
    db_session.commit()
    make_base_score(db_session, job, slug="old")
    assert stage.for_job_rows(db_session, [job])[job.id].rung == "saved"


def test_an_open_session_makes_gaps_with_counts(db_session):
    job = make_job(db_session)
    make_base_score(db_session, job)
    session = make_session(
        db_session,
        job,
        resolutions=[
            {"gap_id": "g0", "action": "answer"},
            {"gap_id": "g3", "action": "skip"},
            {"gap_id": "gone", "action": "answer"},  # no longer listed: counts for nothing
        ],
    )
    s = stage.for_job_rows(db_session, [job])[job.id]
    assert s.rung == "gaps" and s.open_session_id == session.id
    assert (s.gaps_done, s.gaps_total) == (2, 5)


def test_two_resolutions_for_one_gap_count_once(db_session):
    job = make_job(db_session)
    make_session(
        db_session,
        job,
        resolutions=[
            {"gap_id": "g0", "action": "answer"},
            {"gap_id": "g0", "action": "skip"},
        ],
    )
    s = stage.for_job_rows(db_session, [job])[job.id]
    assert (s.gaps_done, s.gaps_total) == (1, 5)


def test_a_gap_without_an_id_does_not_break_the_count(db_session):
    job = make_job(db_session)
    row = make_session(db_session, job)
    row.gaps_json = {"categories": [{"id": "c", "gaps": [{"gap_id": "g0"}, {"title": "no id"}]}]}
    row.resolutions_json = [{"action": "skip"}, {"gap_id": "g0", "action": "answer"}]
    db_session.commit()
    s = stage.for_job_rows(db_session, [job])[job.id]
    assert (s.gaps_done, s.gaps_total) == (1, 1)


def test_a_closed_session_is_not_gaps(db_session):
    job = make_job(db_session)
    make_session(db_session, job, status="superseded")
    make_session(db_session, job, status="abandoned")
    assert stage.for_job_rows(db_session, [job])[job.id].rung == "saved"


def test_the_newest_open_session_wins(db_session):
    job = make_job(db_session)
    now = datetime.now(UTC)
    make_session(db_session, job, created_at=now - timedelta(hours=1), n=3)
    newer = make_session(db_session, job, created_at=now, n=5)
    s = stage.for_job_rows(db_session, [job])[job.id]
    assert s.open_session_id == newer.id and s.gaps_total == 5


def test_each_job_gets_its_own_stage(db_session):
    a, b = make_job(db_session, 1), make_job(db_session, 2)
    make_session(db_session, a)
    out = stage.for_job_rows(db_session, [a, b])
    assert (out[a.id].rung, out[b.id].rung) == ("gaps", "saved")


def test_a_tailored_draft_is_tailored(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="draft", customized_json=SAMPLE_RESUME)
    assert _rung_of_app(db_session, app) == "tailored"


def test_a_draft_wins_over_an_older_open_session(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="draft", customized_json=SAMPLE_RESUME)
    make_session(db_session, job, created_at=app.updated_at - timedelta(hours=1))
    assert _rung_of_app(db_session, app) == "tailored"


def test_an_open_session_newer_than_the_draft_reads_gaps(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="draft", customized_json=SAMPLE_RESUME)
    session = make_session(
        db_session,
        job,
        created_at=app.updated_at + timedelta(hours=1),
        resolutions=[{"gap_id": "g0", "action": "answer"}],
    )
    s = stage.for_applications(db_session, [app])[app.id]
    assert (s.rung, s.open_session_id, s.gaps_done, s.gaps_total) == ("gaps", session.id, 1, 5)


def test_an_open_session_newer_than_the_pdf_reads_gaps(db_session):
    job = make_job(db_session)
    app = make_application(
        db_session, job, status="draft", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    session = make_session(db_session, job, created_at=app.updated_at + timedelta(hours=1))
    s = stage.for_applications(db_session, [app])[app.id]
    assert s.rung == "gaps" and s.open_session_id == session.id


def _draft_written(db_session, app, at):
    """The draft's version row, as every draft write records one, stamped `at`."""
    db_session.add(
        ResumeVersion(
            resume_kind="application",
            resume_key=str(app.id),
            version_number=1,
            snapshot=SAMPLE_RESUME,
            source="tailor",
            created_at=at,
        )
    )
    db_session.commit()


def test_a_notes_edit_after_a_restart_keeps_gaps(db_session):
    """`updated_at` moves on any column write: a Notes edit after Restart gap analysis must not read
    as a newer draft and flip the rung back to pdf_ready."""
    job = make_job(db_session)
    now = datetime.now(UTC)
    app = make_application(
        db_session, job, status="draft", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    _draft_written(db_session, app, now - timedelta(hours=3))
    session = make_session(db_session, job, created_at=now - timedelta(hours=2))
    app.notes = "Follow up on Monday"
    db_session.commit()
    db_session.refresh(app)
    assert app.updated_at > session.created_at  # the write that used to flip it
    assert _rung_of_app(db_session, app) == "gaps"
    s = stage.for_job_rows(db_session, [job])[job.id]
    assert s.rung == "gaps" and s.open_session_id == session.id


def test_a_draft_edit_after_the_restart_is_the_later_work(db_session):
    job = make_job(db_session)
    now = datetime.now(UTC)
    app = make_application(
        db_session, job, status="draft", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    make_session(db_session, job, created_at=now - timedelta(hours=2))
    _draft_written(db_session, app, now - timedelta(hours=1))
    assert _rung_of_app(db_session, app) == "pdf_ready"
    assert stage.for_job_rows(db_session, [job])[job.id].rung == "pdf_ready"


def test_applied_wins_over_a_newer_open_session(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="applied", customized_json=SAMPLE_RESUME)
    make_session(db_session, job, created_at=app.updated_at + timedelta(hours=1))
    assert _rung_of_app(db_session, app) == "applied"


def test_a_rejected_draft_with_a_pdf_is_closed(db_session):
    job = make_job(db_session)
    app = make_application(
        db_session, job, status="rejected", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    make_session(db_session, job, created_at=app.updated_at + timedelta(hours=1))
    assert _rung_of_app(db_session, app) == "closed"


def test_a_withdrawn_application_that_was_applied_is_closed(db_session):
    job = make_job(db_session)
    app = make_application(
        db_session,
        job,
        status="withdrawn",
        applied_at=datetime.now(UTC),
        customized_json=SAMPLE_RESUME,
    )
    assert _rung_of_app(db_session, app) == "closed"


def test_a_pdf_makes_pdf_ready(db_session):
    job = make_job(db_session)
    app = make_application(
        db_session, job, status="draft", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    assert _rung_of_app(db_session, app) == "pdf_ready"


def test_applied_wins_over_everything(db_session):
    job = make_job(db_session)
    app = make_application(
        db_session, job, status="applied", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    assert _rung_of_app(db_session, app) == "applied"


def test_a_later_submitted_status_is_applied(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="interviewing", customized_json=SAMPLE_RESUME)
    assert _rung_of_app(db_session, app) == "applied"


def test_an_applied_at_stamp_alone_is_applied(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="draft", applied_at=datetime.now(UTC))
    assert _rung_of_app(db_session, app) == "applied"


def test_a_draft_set_back_from_applied_is_not_applied(db_session):
    job = make_job(db_session)
    app = make_application(
        db_session, job, status="applied", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    app.status = "draft"
    app.applied_at = None
    db_session.commit()
    assert _rung_of_app(db_session, app) == "pdf_ready"


def test_an_application_without_a_draft_on_a_job_with_an_open_session_reads_gaps(db_session):
    job = make_job(db_session)
    session = make_session(db_session, job, resolutions=[{"gap_id": "g1", "action": "skip"}])
    app = make_application(db_session, job, status="draft")
    s = stage.for_applications(db_session, [app])[app.id]
    assert (s.rung, s.open_session_id, s.gaps_done, s.gaps_total) == ("gaps", session.id, 1, 5)


def test_an_application_without_a_draft_on_a_scored_job_reads_scored(db_session):
    job = make_job(db_session)
    make_base_score(db_session, job)
    app = make_application(db_session, job, status="draft")
    assert _rung_of_app(db_session, app) == "scored"


def test_an_application_without_a_draft_on_an_unscored_job_reads_saved(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="draft")
    assert _rung_of_app(db_session, app) == "saved"
