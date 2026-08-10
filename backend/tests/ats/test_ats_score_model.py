from app.models.ats_score import AtsScore
from app.models.job import Job


def test_ats_score_roundtrip(db_session):
    job = Job(raw_text="jd", raw_text_hash="h1", extracted_json={"title": "X"})
    db_session.add(job)
    db_session.flush()
    row = AtsScore(
        job_id=job.id, target_type="base_resume", target_id="data_scientist",
        phase="base", composite=61.5,
        subscores_json={"keyword": 0.6}, skill_table_json=[{"jd_skill": "Python"}],
        config_version="abc123", engine_version="ats-1.0.0",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.id is not None and float(row.composite) == 61.5
