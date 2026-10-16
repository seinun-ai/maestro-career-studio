from datetime import UTC, datetime, timedelta

from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.services import stage
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _job(db_session, n=1):
    job = Job(raw_text="jd", raw_text_hash=f"stage-{n}", extracted_json=SAMPLE_JD)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _base_score(db_session, job, slug="data_scientist"):
    row = AtsScore(
        job_id=job.id,
        target_type="base_resume",
        target_id=slug,
        phase="base",
        composite=62.0,
        subscores_json={},
        skill_table_json=[],
        config_version="test",
        engine_version="test",
    )
    db_session.add(row)
    db_session.commit()
    return row


def _gaps(n):
    return {
        "categories": [
            {"id": "c1", "gaps": [{"gap_id": f"g{i}"} for i in range(n - 2)]},
            {"id": "c2", "gaps": [{"gap_id": f"g{i}"} for i in range(n - 2, n)]},
        ]
    }


def _open_session(db_session, job, *, status="open", resolutions=None, created_at=None, n=5):
    row = TailoringSession(
        job_id=job.id,
        base_resume="data_scientist",
        status=status,
        gaps_json=_gaps(n),
        resolutions_json=resolutions or [],
    )
    if created_at is not None:
        row.created_at = created_at
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _application(db_session, job, **fields):
    row = Application(job_id=job.id, base_resume="data_scientist", **fields)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _rung_of_app(db_session, application):
    return stage.for_applications(db_session, [application])[application.id].rung


def test_rungs_are_ordered():
    assert stage.RUNGS == ("saved", "scored", "gaps", "tailored", "pdf_ready", "applied")


def test_nothing_in_nothing_out(db_session):
    assert stage.for_jobs(db_session, []) == {}
    assert stage.for_applications(db_session, []) == {}


def test_a_saved_job_with_no_score_is_saved(db_session):
    job = _job(db_session)
    out = stage.for_jobs(db_session, [job])
    assert out[job.id] == stage.Stage("saved")


def test_a_scored_job_is_scored(db_session):
    job = _job(db_session)
    _base_score(db_session, job)
    assert stage.for_jobs(db_session, [job])[job.id].rung == "scored"


def test_a_score_for_an_archived_base_does_not_make_a_job_scored(db_session):
    job = _job(db_session)
    db_session.add(
        BaseResume(slug="old", data_json=SAMPLE_RESUME, archived_at=datetime.now(UTC))
    )
    db_session.commit()
    _base_score(db_session, job, slug="old")
    assert stage.for_jobs(db_session, [job])[job.id].rung == "saved"


def test_an_open_session_makes_gaps_with_counts(db_session):
    job = _job(db_session)
    _base_score(db_session, job)
    session = _open_session(
        db_session,
        job,
        resolutions=[
            {"gap_id": "g0", "action": "answer"},
            {"gap_id": "g3", "action": "skip"},
            {"gap_id": "gone", "action": "answer"},  # no longer listed: counts for nothing
        ],
    )
    s = stage.for_jobs(db_session, [job])[job.id]
    assert s.rung == "gaps" and s.open_session_id == session.id
    assert (s.gaps_done, s.gaps_total) == (2, 5)


def test_a_closed_session_is_not_gaps(db_session):
    job = _job(db_session)
    _open_session(db_session, job, status="superseded")
    _open_session(db_session, job, status="abandoned")
    assert stage.for_jobs(db_session, [job])[job.id].rung == "saved"


def test_the_newest_open_session_wins(db_session):
    job = _job(db_session)
    now = datetime.now(UTC)
    _open_session(db_session, job, created_at=now - timedelta(hours=1), n=3)
    newer = _open_session(db_session, job, created_at=now, n=5)
    s = stage.for_jobs(db_session, [job])[job.id]
    assert s.open_session_id == newer.id and s.gaps_total == 5


def test_each_job_gets_its_own_stage(db_session):
    a, b = _job(db_session, 1), _job(db_session, 2)
    _open_session(db_session, a)
    out = stage.for_jobs(db_session, [a, b])
    assert (out[a.id].rung, out[b.id].rung) == ("gaps", "saved")


def test_a_tailored_draft_is_tailored(db_session):
    job = _job(db_session)
    app = _application(db_session, job, status="draft", customized_json=SAMPLE_RESUME)
    assert _rung_of_app(db_session, app) == "tailored"


def test_a_draft_wins_over_an_open_session(db_session):
    job = _job(db_session)
    _open_session(db_session, job)
    app = _application(db_session, job, status="draft", customized_json=SAMPLE_RESUME)
    assert _rung_of_app(db_session, app) == "tailored"


def test_a_pdf_makes_pdf_ready(db_session):
    job = _job(db_session)
    app = _application(
        db_session, job, status="draft", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    assert _rung_of_app(db_session, app) == "pdf_ready"


def test_applied_wins_over_everything(db_session):
    job = _job(db_session)
    app = _application(
        db_session, job, status="applied", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    assert _rung_of_app(db_session, app) == "applied"


def test_a_later_submitted_status_is_applied(db_session):
    job = _job(db_session)
    app = _application(db_session, job, status="interviewing", customized_json=SAMPLE_RESUME)
    assert _rung_of_app(db_session, app) == "applied"


def test_an_applied_at_stamp_alone_is_applied(db_session):
    job = _job(db_session)
    app = _application(db_session, job, status="draft", applied_at=datetime.now(UTC))
    assert _rung_of_app(db_session, app) == "applied"


def test_a_draft_set_back_from_applied_is_not_applied(db_session):
    job = _job(db_session)
    app = _application(
        db_session, job, status="applied", customized_json=SAMPLE_RESUME, pdf_path="/x/r.pdf"
    )
    app.status = "draft"
    app.applied_at = None
    db_session.commit()
    assert _rung_of_app(db_session, app) == "pdf_ready"


def test_an_application_without_a_draft_on_a_job_with_an_open_session_reads_gaps(db_session):
    job = _job(db_session)
    session = _open_session(db_session, job, resolutions=[{"gap_id": "g1", "action": "skip"}])
    app = _application(db_session, job, status="draft")
    s = stage.for_applications(db_session, [app])[app.id]
    assert (s.rung, s.open_session_id, s.gaps_done, s.gaps_total) == ("gaps", session.id, 1, 5)


def test_an_application_without_a_draft_on_a_scored_job_reads_scored(db_session):
    job = _job(db_session)
    _base_score(db_session, job)
    app = _application(db_session, job, status="draft")
    assert _rung_of_app(db_session, app) == "scored"


def test_an_application_without_a_draft_on_an_unscored_job_reads_saved(db_session):
    job = _job(db_session)
    app = _application(db_session, job, status="draft")
    assert _rung_of_app(db_session, app) == "saved"
