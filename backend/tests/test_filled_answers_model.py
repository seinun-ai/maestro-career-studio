"""The answer receipt's table: one row per page run (design §1)."""

from sqlalchemy import func, select

from app.models.application import Application
from app.models.filled_answer import FilledAnswer
from tests.test_proposals_models import _mk_job


def _row(job, **extra) -> FilledAnswer:
    return FilledAnswer(job_id=job.id, channel="companion", host="jobs.ashbyhq.com",
                        step="/acme/apply", fields=[{"question": "First name", "answer": "Ada",
                                                     "source": "profile"}], **extra)


def test_a_row_round_trips_with_an_aware_timestamp(db_session):
    job = _mk_job(db_session, company="Acme")
    row = _row(job)
    db_session.add(row)
    db_session.commit()
    stored = db_session.get(FilledAnswer, row.id)
    assert stored.fields[0]["answer"] == "Ada"
    assert stored.captured_at.tzinfo is not None
    assert stored.application_id is None


def test_the_rows_go_with_their_job(db_session):
    job = _mk_job(db_session, company="Acme")
    db_session.add(_row(job))
    db_session.commit()
    db_session.delete(job)
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(FilledAnswer)) == 0


def test_deleting_the_application_keeps_the_record_unlinked(db_session):
    job = _mk_job(db_session, company="Acme")
    app_row = Application(job_id=job.id, base_resume="hybrid")
    db_session.add(app_row)
    db_session.commit()
    row = _row(job, application_id=app_row.id)
    db_session.add(row)
    db_session.commit()
    db_session.delete(app_row)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(FilledAnswer, row.id).application_id is None
