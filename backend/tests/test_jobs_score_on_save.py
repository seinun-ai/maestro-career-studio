"""Saving a job scores it against every selectable base resume in the same request.

Both save paths (web Add job, `POST /api/jobs`, and the pre-extracted ingest used by the
Companion and MCP) go through `_persist_job`, which scores a NEW job after its commit. A
scoring failure (no extracted skills, a corrupt base file) is logged and never fails the save;
a dedup hit returns the tracked row without scoring again. No LLM: extract_jd is patched."""

import copy
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from app.config import settings
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.routers import jobs
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _seed_bases(db_session, tmp_path, monkeypatch, slugs=("a", "b")):
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    for slug in slugs:
        (tmp_path / f"{slug}.json").write_text(json.dumps(SAMPLE_RESUME))
        db_session.add(BaseResume(slug=slug, data_json=SAMPLE_RESUME))
    db_session.commit()


def _extract_as(monkeypatch, extraction):
    monkeypatch.setattr(
        jobs.jd_extraction, "extract_jd", lambda raw_text, session=None: copy.deepcopy(extraction)
    )


def _base_rows(client, job_id):
    rows = client.get("/api/ats-scores", params={"job_id": job_id}).json()
    return [r for r in rows if r["phase"] == "base"]


def _saved_row(client, job_id):
    rows = client.get("/api/jobs?without_application=true").json()
    return next(r for r in rows if r["id"] == job_id)


def test_a_saved_job_is_scored_against_every_selectable_base(
    db_session, tmp_path, monkeypatch, client
):
    _seed_bases(db_session, tmp_path, monkeypatch)
    _extract_as(monkeypatch, SAMPLE_JD)

    job = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"}).json()

    assert {r["target_id"] for r in _base_rows(client, job["id"])} == {"a", "b"}


def test_an_archived_base_is_not_scored(db_session, tmp_path, monkeypatch, client):
    _seed_bases(db_session, tmp_path, monkeypatch)
    archived = db_session.get(BaseResume, "b")
    archived.archived_at = datetime.now(UTC)
    db_session.commit()
    _extract_as(monkeypatch, SAMPLE_JD)

    job = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"}).json()

    stored = db_session.query(AtsScore).filter(AtsScore.job_id == UUID(job["id"])).all()
    assert {row.target_id for row in stored} == {"a"}


def test_an_unscorable_job_still_saves(db_session, tmp_path, monkeypatch, client, caplog):
    _seed_bases(db_session, tmp_path, monkeypatch)
    _extract_as(monkeypatch, {**SAMPLE_JD, "skills": []})

    with caplog.at_level(logging.WARNING, logger="app.routers.jobs"):
        r = client.post("/api/jobs", json={"raw_text": "nothing here"})

    assert r.status_code == 200 and r.json()["id"]
    job_id = r.json()["id"]
    assert db_session.get(Job, UUID(job_id)) is not None
    assert _base_rows(client, job_id) == []
    assert _saved_row(client, job_id)["stage"] == "saved"
    assert any(job_id in rec.getMessage() for rec in caplog.records)


def test_a_corrupt_base_file_never_fails_the_save(db_session, tmp_path, monkeypatch, client):
    _seed_bases(db_session, tmp_path, monkeypatch)
    (tmp_path / "b.json").write_text("{not json")
    _extract_as(monkeypatch, SAMPLE_JD)

    r = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"})

    assert r.status_code == 200
    job_id = r.json()["id"]
    assert _saved_row(client, job_id)["company"] == "Acme Corp"
    # The scoring rolled back as a whole; the job did not.
    assert db_session.query(AtsScore).filter(AtsScore.job_id == UUID(job_id)).count() == 0


def test_a_job_saved_with_no_base_resume_saves_unscored(db_session, monkeypatch, client):
    _extract_as(monkeypatch, SAMPLE_JD)

    r = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"})

    assert r.status_code == 200
    assert _saved_row(client, r.json()["id"])["stage"] == "saved"


def test_ingest_scores_too(db_session, tmp_path, monkeypatch, client):
    _seed_bases(db_session, tmp_path, monkeypatch)

    r = client.post(
        "/api/jobs/ingest",
        json={"extracted_json": SAMPLE_JD, "raw_text": "agent capture", "source": "agent"},
    )

    assert r.status_code == 200
    assert {row["target_id"] for row in _base_rows(client, r.json()["id"])} == {"a", "b"}


def test_a_dedup_hit_does_not_rescore(db_session, tmp_path, monkeypatch, client):
    _seed_bases(db_session, tmp_path, monkeypatch)
    _extract_as(monkeypatch, SAMPLE_JD)
    calls = []
    real = jobs.ats_score.score_all_bases
    monkeypatch.setattr(
        jobs.ats_score,
        "score_all_bases",
        lambda job_id, **kw: calls.append(job_id) or real(job_id, **kw),
    )

    first = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"}).json()
    second = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"}).json()
    ingested = client.post(
        "/api/jobs/ingest",
        json={"extracted_json": SAMPLE_JD, "raw_text": "Senior Data Scientist at Acme"},
    ).json()

    assert first["id"] == second["id"] == ingested["id"]
    assert len(calls) == 1
    assert db_session.query(AtsScore).filter(AtsScore.job_id == UUID(first["id"])).count() == 2


def test_the_match_column_reads_the_best_score_right_after_save(
    db_session, tmp_path, monkeypatch, client
):
    _seed_bases(db_session, tmp_path, monkeypatch)
    _extract_as(monkeypatch, SAMPLE_JD)

    job = client.post("/api/jobs", json={"raw_text": "Senior Data Scientist at Acme"}).json()

    row = _saved_row(client, job["id"])
    assert row["best_ats_score"] is not None
    assert row["best_ats_score"] == max(r["composite"] for r in _base_rows(client, job["id"]))
    assert row["stage"] == "scored"
