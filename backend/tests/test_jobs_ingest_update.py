"""Correcting a saved job through the capture route (`POST /api/jobs/ingest`, `update`).

Without `update` a repeat capture returns the saved job unchanged, as it always has. With
`update=true` the new extraction replaces the saved job's fields and skills through the same
mapping a new capture uses, keeps its id, status, applications, proposals and provenance,
deletes its saved match scores (they are computed from the extraction alone, so the next
scoring recomputes them) and names, without touching, a tailored resume or an open gap
analysis. No LLM: the ingest route takes the caller's extraction."""

import copy
import json
import uuid

from app.config import settings
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.tailoring_session import TailoringSession
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME

TEXT = "Logistics Coordinator, Harbourline Freight. Plan inbound shipments and customs paperwork."
LINK = "https://careers.harbourline.example/jobs/48213"


def _first():
    return {
        "title": "Logistics Coordinator",
        "company": "Harbourline Freight",
        "role_category": "operations",
        "work_mode": "on_site",
        "city": "Rotterdam",
        "country": "Netherlands",
        "location_raw": "Rotterdam, Netherlands",
        "skills": [
            {"skill_name": "SAP", "skill_category": "tool", "requirement_level": "required"},
            {"skill_name": "Excel", "skill_category": "tool", "requirement_level": "preferred"},
        ],
        "responsibilities": ["Plan inbound shipments"],
        "qualifications": ["Two years in freight"],
    }


def _corrected():
    fixed = _first()
    fixed.update(
        title="Senior Logistics Coordinator",
        city="Hamburg",
        country="Germany",
        location_raw="Hamburg, Germany",
        salary_min=52000,
        salary_max=60000,
        salary_period="year",
        salary_currency="EUR",
    )
    fixed["skills"] = [
        {"skill_name": "SAP", "skill_category": "tool", "requirement_level": "required"},
        {"skill_name": "Customs Clearance", "skill_category": "domain", "requirement_level": "required"},
    ]
    fixed["responsibilities"] = ["Plan inbound shipments", "Clear customs for EU imports"]
    return fixed


def _ingest(client, extraction, **extra):
    body = {"extracted_json": extraction, "raw_text": TEXT, **extra}
    response = client.post("/api/jobs/ingest", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _skills(db_session, job_id):
    db_session.expire_all()
    rows = db_session.query(JobSkill).filter(JobSkill.job_id == uuid.UUID(job_id)).all()
    return sorted((row.skill_name, row.requirement_level) for row in rows)


def _scores(db_session, job_id):
    db_session.expire_all()
    return db_session.query(AtsScore).filter(AtsScore.job_id == uuid.UUID(job_id)).all()


def _seed_bases(db_session, tmp_path, monkeypatch, slugs=("a", "b")):
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    for slug in slugs:
        (tmp_path / f"{slug}.json").write_text(json.dumps(SAMPLE_RESUME))
        db_session.add(BaseResume(slug=slug, data_json=SAMPLE_RESUME))
    db_session.commit()


def test_a_repeat_capture_without_update_returns_the_saved_job_unchanged(db_session, client):
    first = _ingest(client, _first())

    again = _ingest(client, _corrected())

    assert again["id"] == first["id"]
    assert again["already_existed"] is True
    assert again["correction"] is None
    assert (again["title"], again["city"], again["country_code"]) == (
        "Logistics Coordinator", "Rotterdam", "NL")
    assert _skills(db_session, first["id"]) == [("excel", "preferred"), ("sap", "required")]
    assert db_session.query(Job).count() == 1


def test_update_replaces_the_fields_and_skills_through_the_capture_mapping(db_session, client):
    first = _ingest(client, _first())

    fixed = _ingest(client, _corrected(), update=True)

    assert fixed["id"] == first["id"]
    assert fixed["already_existed"] is True
    assert (fixed["title"], fixed["city"], fixed["country"], fixed["country_code"]) == (
        "Senior Logistics Coordinator", "Hamburg", "Germany", "DE")
    assert (fixed["salary_currency"], fixed["salary_currency_assumed"]) == ("EUR", False)
    assert fixed["extracted_json"]["responsibilities"][-1] == "Clear customs for EU imports"
    # Canonicalized like a new capture's skill rows.
    assert _skills(db_session, first["id"]) == [("customs clearance", "required"), ("sap", "required")]
    changed = set(fixed["correction"]["changed"])
    assert {"title", "city", "country", "country_code", "location", "salary_min", "salary_currency",
            "responsibilities", "skills"} <= changed
    assert not {"company", "work_mode", "role_category", "qualifications", "extracted_at"} & changed


def test_update_keeps_id_status_applications_proposals_and_provenance(db_session, client):
    first = _ingest(client, _first(), source="agent")
    job_id = uuid.UUID(first["id"])
    db_session.add(Application(job_id=job_id, base_resume="ops_base", status="applied"))
    db_session.add(ApplicationProposal(job_id=job_id, status="accepted", proposed_by="you"))
    db_session.commit()

    fixed = _ingest(client, _corrected(), source="user", update=True)

    assert fixed["source"] == "agent"
    assert fixed["raw_text"] == TEXT
    assert fixed["proposal_status"] == "accepted"
    db_session.expire_all()
    applications = db_session.query(Application).filter(Application.job_id == job_id).all()
    assert [a.status for a in applications] == ["applied"]
    assert db_session.query(ApplicationProposal).filter(ApplicationProposal.job_id == job_id).count() == 1


def test_update_deletes_the_jobs_saved_scores_and_scoring_recomputes_them(
    db_session, tmp_path, monkeypatch, client
):
    _seed_bases(db_session, tmp_path, monkeypatch)
    saved = client.post("/api/jobs/ingest", json={"extracted_json": SAMPLE_JD, "raw_text": "ds role"}).json()
    other = client.post("/api/jobs/ingest", json={"extracted_json": SAMPLE_JD, "raw_text": "ds role two"}).json()
    assert len(_scores(db_session, saved["id"])) == 2
    corrected = copy.deepcopy(SAMPLE_JD)
    corrected["skills"] = [
        {"skill_name": "Python", "skill_category": "Programming Language", "requirement_level": "required"},
        {"skill_name": "Kubernetes", "skill_category": "DevOps", "requirement_level": "required"},
    ]

    fixed = client.post(
        "/api/jobs/ingest", json={"extracted_json": corrected, "raw_text": "ds role", "update": True}
    ).json()

    assert fixed["correction"]["scores_cleared"] == 2
    assert _scores(db_session, saved["id"]) == []
    assert len(_scores(db_session, other["id"])) == 2  # another job's scores stay
    rescored = client.post("/api/ats-scores", json={"job_id": saved["id"]})
    assert rescored.status_code == 200
    skills_scored = {row["jd_skill"].lower() for row in rescored.json()[0]["skill_table_json"]}
    assert "kubernetes" in skills_scored and "snowflake" not in skills_scored


def test_an_update_that_changes_nothing_keeps_the_scores(db_session, tmp_path, monkeypatch, client):
    _seed_bases(db_session, tmp_path, monkeypatch)
    saved = client.post("/api/jobs/ingest", json={"extracted_json": SAMPLE_JD, "raw_text": "ds role"}).json()

    same = client.post(
        "/api/jobs/ingest", json={"extracted_json": SAMPLE_JD, "raw_text": "ds role", "update": True}
    ).json()

    assert same["correction"]["changed"] == []
    assert same["correction"]["scores_cleared"] == 0
    assert len(_scores(db_session, saved["id"])) == 2


def test_update_names_a_tailored_resume_and_an_open_gap_analysis_and_leaves_them(db_session, client):
    first = _ingest(client, _first())
    job_id = uuid.UUID(first["id"])
    draft = {"contact": {"name": "Sample Person", "email": "sample@example.org"}, "summary": "Draft."}
    tailored = Application(job_id=job_id, base_resume="ops_base", status="draft", customized_json=draft)
    session = TailoringSession(job_id=job_id, base_resume="ops_base", status="open",
                               gaps_json={"categories": []}, resolutions_json=[])
    closed = TailoringSession(job_id=job_id, base_resume="ops_base", status="abandoned",
                              gaps_json={"categories": []}, resolutions_json=[])
    db_session.add_all([tailored, session, closed])
    db_session.commit()

    fixed = _ingest(client, _corrected(), update=True)

    assert fixed["correction"]["tailored_applications"] == [str(tailored.id)]
    assert fixed["correction"]["open_sessions"] == [str(session.id)]
    db_session.expire_all()
    assert db_session.get(Application, tailored.id).customized_json == draft
    assert db_session.get(TailoringSession, session.id).status == "open"


def test_update_without_raw_text_finds_the_posting_by_its_link(db_session, client):
    first = client.post("/api/jobs/ingest", json={"extracted_json": _first(), "source_url": LINK}).json()

    fixed = client.post("/api/jobs/ingest", json={
        "extracted_json": _corrected(), "source_url": LINK + "?utm_source=board", "update": True,
    }).json()

    assert fixed["id"] == first["id"]
    assert fixed["city"] == "Hamburg"
    assert db_session.query(Job).count() == 1


def test_update_on_a_posting_not_yet_saved_is_a_plain_capture(db_session, client):
    created = _ingest(client, _first(), update=True)

    assert created["already_existed"] is False
    assert created["correction"] is None
    assert created["title"] == "Logistics Coordinator"


def test_the_apply_link_is_stored_on_capture_and_found_by_url(db_session, client):
    apply = "https://apply.harbourline.example/requisitions/48213"
    first = _ingest(client, _first(), apply_url=apply)

    match = client.get("/api/jobs/match", params={"url": apply}).json()

    assert first["apply_url"] == apply
    assert match["match"] == "exact" and match["job"]["id"] == first["id"]


def test_update_replaces_the_apply_link_and_reports_it(db_session, client):
    old = "https://apply.harbourline.example/requisitions/48213"
    new = "https://apply.harbourline.example/requisitions/48213-de"
    first = _ingest(client, _first(), apply_url=old)

    unchanged = _ingest(client, _first(), apply_url=new)
    fixed = _ingest(client, _first(), apply_url=new, update=True)
    kept = _ingest(client, _first(), update=True)

    assert unchanged["apply_url"] == old  # without update a stored link is never replaced
    assert fixed["apply_url"] == new
    assert fixed["correction"]["changed"] == ["apply_url"]
    assert kept["apply_url"] == new  # an update that names no link keeps the stored one
    assert client.get("/api/jobs/match", params={"url": new}).json()["job"]["id"] == first["id"]
