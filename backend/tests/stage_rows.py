"""Row builders for the stage tests (test_stage.py, test_stage_api.py): one job, score, gap
session or application, committed and refreshed."""

from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from tests.ats.fixtures import SAMPLE_JD


def make_job(db_session, n=1):
    job = Job(raw_text="jd", raw_text_hash=f"stage-{n}", extracted_json=SAMPLE_JD)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def make_base_score(db_session, job, slug="data_scientist"):
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


def gaps_doc(n):
    return {
        "categories": [
            {"id": "c1", "gaps": [{"gap_id": f"g{i}"} for i in range(n - 2)]},
            {"id": "c2", "gaps": [{"gap_id": f"g{i}"} for i in range(n - 2, n)]},
        ]
    }


def make_session(db_session, job, *, status="open", resolutions=None, created_at=None, n=5):
    row = TailoringSession(
        job_id=job.id,
        base_resume="data_scientist",
        status=status,
        gaps_json=gaps_doc(n),
        resolutions_json=resolutions or [],
    )
    if created_at is not None:
        row.created_at = created_at
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def make_application(db_session, job, **fields):
    row = Application(job_id=job.id, base_resume="data_scientist", **fields)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row
