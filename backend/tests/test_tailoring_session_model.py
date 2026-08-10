from app.models.job import Job
from app.models.tailoring_session import TailoringSession


def test_tailoring_session_roundtrip(db_session):
    job = Job(raw_text="jd", raw_text_hash="h1", extracted_json={"title": "X"})
    db_session.add(job)
    db_session.flush()
    row = TailoringSession(
        job_id=job.id,
        base_resume="data_scientist",
        gaps_json={"categories": [], "base_composite": 61.5},
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.id is not None
    assert row.status == "open"
    assert row.resolutions_json == []
    assert row.application_id is None and row.base_ats_score_id is None
    assert row.created_at is not None and row.updated_at is not None
    assert row.gaps_json["base_composite"] == 61.5
