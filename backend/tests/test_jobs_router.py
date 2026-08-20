import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.routers import jobs


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _fake_extraction():
    return {
        "company": "Acme",
        "title": "Senior Data Analyst",
        "role_category": "data_analyst",
        "level": "senior",
        "employment_type": "full_time",
        "work_mode": "hybrid",
        "location": "Dallas, TX",
        "salary_min": "100000",
        "salary_max": "120000",
        "salary_period": "year",
        "skills": [
            {
                "skill_name": "SQL",
                "skill_category": "language",
                "requirement_level": "required",
            },
            {
                "skill_name": "Power BI",
                "skill_category": "tool",
                "requirement_level": "preferred",
            },
        ],
    }


def test_post_jobs_creates_job_and_skills(db_session, monkeypatch):
    app.dependency_overrides[get_db] = _override_db(db_session)
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: _fake_extraction(),
    )

    try:
        client = TestClient(app)
        response = client.post("/api/jobs", json={"raw_text": "Need SQL", "source_url": "https://x.test"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["company"] == "Acme"
    assert body["title"] == "Senior Data Analyst"
    assert len(db_session.query(JobSkill).all()) == 2


def test_post_jobs_stores_requisition_id(db_session, monkeypatch):
    # G11: the ATS requisition/job ID is a promoted column so cross-board
    # duplicates of the same posting can be identified.
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _fake_extraction()
    extraction["requisition_id"] = "R-12345"
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: extraction,
    )
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs",
            json={"raw_text": "Req R-12345 needs SQL", "source_url": "https://a.test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["requisition_id"] == "R-12345"


def test_saved_jobs_list_carries_newest_proposal_status(db_session, monkeypatch):
    # Tracker clarity (2026-08-01): agent-captured jobs without applications all
    # rendered a flat "Saved" — the derived proposal_status lets the UI show
    # Declined/Queued/Proposed instead of hiding what happened.
    from app.services import proposals as svc

    app.dependency_overrides[get_db] = _override_db(db_session)
    extractions = iter([_fake_extraction(), _fake_extraction()])
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: next(extractions),
    )
    try:
        client = TestClient(app)
        declined_job = client.post("/api/jobs", json={"raw_text": "posting A"}).json()
        plain_job = client.post("/api/jobs", json={"raw_text": "posting B"}).json()

        prop = svc.create_proposal(
            db_session, job_id=declined_job["id"],
            fit={"chosen_base": "hybrid"}, plan={},
        )
        svc.transition(db_session, prop, "rejected",
                       consent={"channel": "frontend"}, reason="duplicate")

        listed = client.get("/api/jobs?without_application=true")
    finally:
        app.dependency_overrides.clear()

    by_id = {j["id"]: j for j in listed.json()}
    assert by_id[declined_job["id"]]["proposal_status"] == "rejected"
    assert by_id[declined_job["id"]]["proposal_id"] == str(prop.id)
    assert by_id[plain_job["id"]]["proposal_status"] is None
    assert by_id[plain_job["id"]]["proposal_id"] is None

    # The detail route derives it too (job-page promote action visibility).
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        detail = TestClient(app).get(f"/api/jobs/{declined_job['id']}/detail")
    finally:
        app.dependency_overrides.clear()
    assert detail.json()["job"]["proposal_status"] == "rejected"
    assert detail.json()["job"]["proposal_id"] == str(prop.id)


def test_jobs_list_serializes_source(db_session, monkeypatch):
    # The tracker's Saved-lane rule filters on job.source — a projection that
    # drops the field makes the rule silently no-op (found in the 2026-08-01
    # browser walkthrough: agent hunt inventory flooded the Saved lane).
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _fake_extraction()
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: extraction,
    )
    try:
        client = TestClient(app)
        r = client.post("/api/jobs/ingest", json={
            "extracted_json": _fake_extraction(),
            "raw_text": "agent capture",
            "source_url": "https://agent.test/j1",
            "source": "agent",
        })
        assert r.status_code == 200
        listed = client.get("/api/jobs?without_application=true")
    finally:
        app.dependency_overrides.clear()

    row = next(j for j in listed.json() if j["id"] == r.json()["id"])
    assert row["source"] == "agent"


def test_capture_dedups_on_company_and_requisition_id(db_session, monkeypatch):
    # G11: the same requisition on two boards has different URLs AND different
    # page text — only (company, requisition_id) identifies it. Second capture
    # must return the existing row flagged already_existed, not mint a twin.
    app.dependency_overrides[get_db] = _override_db(db_session)
    first = _fake_extraction()
    first["requisition_id"] = "R-777"
    second = _fake_extraction()
    second["requisition_id"] = "R-777"
    extractions = iter([first, second])
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: next(extractions),
    )
    try:
        client = TestClient(app)
        r1 = client.post("/api/jobs", json={
            "raw_text": "Acme posting as rendered by LinkedIn",
            "source_url": "https://linkedin.test/jobs/1",
        })
        r2 = client.post("/api/jobs", json={
            "raw_text": "Acme posting as rendered by the careers site",
            "source_url": "https://acme.test/careers/R-777",
        })
    finally:
        app.dependency_overrides.clear()

    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["already_existed"] is True


def test_capture_without_requisition_never_requisition_dedups(db_session, monkeypatch):
    # No requisition id -> different raw text stays a different job (companies
    # legitimately run near-identical postings; G11 tier 2 is a soft warning,
    # never a capture-time merge).
    app.dependency_overrides[get_db] = _override_db(db_session)
    extractions = iter([_fake_extraction(), _fake_extraction()])
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: next(extractions),
    )
    try:
        client = TestClient(app)
        r1 = client.post("/api/jobs", json={"raw_text": "posting text A"})
        r2 = client.post("/api/jobs", json={"raw_text": "posting text B"})
    finally:
        app.dependency_overrides.clear()
    assert r2.json()["id"] != r1.json()["id"]


def test_patch_job_source_url(db_session, monkeypatch):
    app.dependency_overrides[get_db] = _override_db(db_session)
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: _fake_extraction(),
    )
    try:
        client = TestClient(app)
        created = client.post("/api/jobs", json={"raw_text": "Need SQL"}).json()
        response = client.patch(
            f"/api/jobs/{created['id']}",
            json={"source_url": "https://careers.example.com/app/123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["source_url"] == "https://careers.example.com/app/123"


def test_post_jobs_dedupes_by_raw_text_hash(db_session, monkeypatch):
    app.dependency_overrides[get_db] = _override_db(db_session)
    calls = {"n": 0}

    def fake_extract(raw_text, session=None):
        calls["n"] += 1
        return _fake_extraction()

    monkeypatch.setattr(jobs.jd_extraction, "extract_jd", fake_extract)

    try:
        client = TestClient(app)
        first = client.post("/api/jobs", json={"raw_text": "Need SQL"})
        second = client.post("/api/jobs", json={"raw_text": "Need SQL"})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert calls["n"] == 1


def test_delete_job_cascades_through_db(db_session, monkeypatch):
    app.dependency_overrides[get_db] = _override_db(db_session)
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: _fake_extraction(),
    )
    try:
        client = TestClient(app)
        created = client.post("/api/jobs", json={"raw_text": "Delete me"}).json()
        delete_response = client.delete(f"/api/jobs/{created['id']}")
        get_response = client.get(f"/api/jobs/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert delete_response.status_code == 204
    assert get_response.status_code == 404
    assert db_session.query(JobSkill).count() == 0


def test_list_jobs_without_application(db_session):
    job_only = Job(
        raw_text="Extract only",
        raw_text_hash="extract-only-hash",
        extracted_json={"title": "Analyst"},
        title="Analyst",
        extracted_at=datetime.now(UTC),
    )
    job_with_app = Job(
        raw_text="Has application",
        raw_text_hash="has-app-hash",
        extracted_json={"title": "Engineer"},
        title="Engineer",
        extracted_at=datetime.now(UTC),
    )
    db_session.add_all([job_only, job_with_app])
    db_session.flush()
    db_session.add(
        Application(job_id=job_with_app.id, base_resume="hybrid", status="draft")
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/jobs?without_application=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(job_only.id) in ids
    assert str(job_with_app.id) not in ids


def test_re_extract_job_updates_columns_and_skills(db_session, monkeypatch):
    app.dependency_overrides[get_db] = _override_db(db_session)
    initial = _fake_extraction()
    updated = {
        **initial,
        "company": "Beta",
        "title": "Lead Data Engineer",
        "skills": [
            {
                "skill_name": "Spark",
                "skill_category": "tool",
                "requirement_level": "required",
            }
        ],
    }
    state = {"call": 0}

    def fake_extract(raw_text, session=None):
        state["call"] += 1
        return initial if state["call"] == 1 else updated

    monkeypatch.setattr(jobs.jd_extraction, "extract_jd", fake_extract)

    try:
        client = TestClient(app)
        created = client.post("/api/jobs", json={"raw_text": "Need stuff"}).json()
        re_extract = client.post(f"/api/jobs/{created['id']}/re-extract")
    finally:
        app.dependency_overrides.clear()

    assert re_extract.status_code == 200
    body = re_extract.json()
    assert body["company"] == "Beta"
    assert body["title"] == "Lead Data Engineer"
    skills = db_session.query(JobSkill).filter(JobSkill.job_id == created["id"]).all()
    # Skill names are canonicalized (casefolded) at store time.
    assert [s.skill_name for s in skills] == ["spark"]


def test_get_and_list_jobs(db_session):
    job = Job(
        raw_text="Need Python",
        raw_text_hash="hash-1",
        extracted_json={"title": "Data Scientist"},
        title="Data Scientist",
        company="Acme",
        role_category="data_scientist",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        list_response = client.get("/api/jobs")
        get_response = client.get(f"/api/jobs/{job.id}")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == str(job.id)
    # JobSummary surfaces the OPT-gating flag for single-read list filtering.
    assert "disqualifying_for_opt" in list_response.json()[0]
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Data Scientist"


def test_get_job_detail_with_no_application(db_session):
    job = Job(
        raw_text="JD body",
        raw_text_hash="hash-detail-1",
        extracted_json={"title": "Data Scientist"},
        title="Data Scientist",
        company="Acme",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.get(f"/api/jobs/{job.id}/detail")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["job"]["id"] == str(job.id)
    assert body["application"] is None


def test_get_job_detail_with_application(db_session):
    job = Job(
        raw_text="JD body 2",
        raw_text_hash="hash-detail-2",
        extracted_json={"title": "Data Engineer"},
        title="Data Engineer",
        company="Beta",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    application = Application(
        job_id=job.id,
        base_resume="data_engineer",
        status="applied",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.get(f"/api/jobs/{job.id}/detail")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["job"]["id"] == str(job.id)
    assert body["application"]["id"] == str(application.id)
    assert body["application"]["status"] == "applied"


def test_get_job_detail_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.get(f"/api/jobs/{uuid.uuid4()}/detail")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def _valid_extraction() -> dict:
    return {
        "company": "Acme",
        "title": "Data Scientist",
        "role_category": "data_scientist",
        "skills": [
            {"skill_name": "SQL", "skill_category": "data", "requirement_level": "required"}
        ],
        "responsibilities": ["Build models"],
        "qualifications": ["MS in stats"],
    }


def test_ingest_stores_pre_extracted_job(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={
                "extracted_json": _valid_extraction(),
                "raw_text": "We need a data scientist",
                "source_url": "https://x.test",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["company"] == "Acme"
    assert body["role_category"] == "data_scientist"
    assert body["extracted_json"]["skills"][0]["skill_name"] == "SQL"


def test_ingest_rejects_invalid_extraction(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={"extracted_json": {"skills": [{"skill_category": "data"}]}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_ingest_without_raw_text_dedupes_on_extraction_hash(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        first = client.post("/api/jobs/ingest", json={"extracted_json": _valid_extraction()})
        second = client.post("/api/jobs/ingest", json={"extracted_json": _valid_extraction()})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_export_returns_jobs_with_skills_and_filters(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        client.post(
            "/api/jobs/ingest",
            json={"extracted_json": _valid_extraction(), "raw_text": "ds role"},
        )
        other = _valid_extraction()
        other["role_category"] = "data_engineer"
        other["skills"] = [
            {"skill_name": "Airflow", "skill_category": "data", "requirement_level": "required"}
        ]
        client.post(
            "/api/jobs/ingest",
            json={"extracted_json": other, "raw_text": "de role"},
        )

        all_rows = client.get("/api/jobs/export").json()
        assert len(all_rows) == 2
        assert any(r["skills"][0]["skill_name"] == "sql" for r in all_rows)

        filtered = client.get("/api/jobs/export", params={"role_category": "data_engineer"}).json()
        assert len(filtered) == 1
        assert filtered[0]["skills"][0]["skill_name"] == "airflow"

        by_skill = client.get("/api/jobs/export", params={"skill": "sql"}).json()
        assert len(by_skill) == 1
        assert by_skill[0]["role_category"] == "data_scientist"
    finally:
        app.dependency_overrides.clear()


def test_export_since_and_skill_negative_filters(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        client.post(
            "/api/jobs/ingest",
            json={"extracted_json": _valid_extraction(), "raw_text": "ds role"},
        )

        # Compute dates in UTC to match how created_at is stored; using local
        # date.today() flakes in the evening when UTC has already rolled over.
        today_utc = datetime.now(UTC).date()
        tomorrow = (today_utc + timedelta(days=1)).isoformat()
        today = today_utc.isoformat()

        # since=tomorrow excludes a job created today
        assert client.get("/api/jobs/export", params={"since": tomorrow}).json() == []

        # since=today includes the just-ingested job
        since_today = client.get("/api/jobs/export", params={"since": today}).json()
        assert len(since_today) >= 1

        # skill that matches nothing returns no rows
        no_match = client.get(
            "/api/jobs/export", params={"skill": "nonexistent_skill_xyz"}
        ).json()
        assert no_match == []
    finally:
        app.dependency_overrides.clear()


def test_list_jobs_returns_slim_summary(db_session):
    job = Job(
        raw_text="Need Python and lots of detail here",
        raw_text_hash="slim-summary-hash",
        extracted_json={"title": "Data Scientist", "responsibilities": ["a", "b"]},
        title="Data Scientist",
        company="Acme",
        role_category="data_scientist",
        level="senior",
        employment_type="full_time",
        work_mode="hybrid",
        location="Dallas, TX",
        work_authorization="no_sponsorship",
        opt_accepted="no",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/jobs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = response.json()[0]
    # Slim summary: present fields...
    assert row["company"] == "Acme"
    assert row["title"] == "Data Scientist"
    assert row["employment_type"] == "full_time"
    assert row["work_authorization"] == "no_sponsorship"
    # ...and heavy/duplicate fields dropped.
    assert "raw_text" not in row
    assert "raw_text_hash" not in row
    assert "extracted_json" not in row


def test_list_jobs_summary_carries_source_url(db_session):
    """The browser extension matches the active tab against each row's
    source_url. JobSummary is a Pydantic projection, so a missing field is
    dropped silently — no error, just a match that scores 0 forever. Assert the
    field survives the projection so that failure mode cannot come back."""
    job = Job(
        raw_text="JD with a link",
        raw_text_hash="summary-source-url-hash",
        source_url="https://jobs.lever.co/acme/abc",
        title="Data Scientist",
        company="Acme",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/jobs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = response.json()[0]
    assert row["source_url"] == "https://jobs.lever.co/acme/abc"


def test_list_jobs_offset_paginates(db_session):
    for i in range(3):
        db_session.add(
            Job(
                raw_text=f"job {i}",
                raw_text_hash=f"offset-page-{i}",
                title=f"Job {i}",
                extracted_at=datetime.now(UTC),
            )
        )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        page1 = client.get("/api/jobs?limit=2&offset=0").json()
        page2 = client.get("/api/jobs?limit=2&offset=2").json()
    finally:
        app.dependency_overrides.clear()

    assert len(page1) == 2
    assert len(page2) == 1
    ids = {r["id"] for r in page1} | {r["id"] for r in page2}
    assert len(ids) == 3  # no overlap across pages


def test_post_jobs_canonicalizes_and_dedupes_skills(db_session, monkeypatch):
    app.dependency_overrides[get_db] = _override_db(db_session)

    def fake_extract(raw_text, session=None):
        return {
            "company": "Acme",
            "title": "ML Engineer",
            "role_category": "ai_ml_engineer",
            "skills": [
                {"skill_name": "LLM", "skill_category": "nlp_genai", "requirement_level": "required"},
                {
                    "skill_name": "Large Language Models",
                    "skill_category": "nlp_genai",
                    "requirement_level": "required",
                },
                {"skill_name": "  Python  ", "skill_category": "Frontend", "requirement_level": "required"},
            ],
        }

    monkeypatch.setattr(jobs.jd_extraction, "extract_jd", fake_extract)
    try:
        client = TestClient(app)
        response = client.post("/api/jobs", json={"raw_text": "Need LLMs"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = db_session.query(JobSkill).all()
    names = sorted(r.skill_name for r in rows)
    # LLM + Large Language Models collapse to one canonical row; Python normalized.
    assert names == ["large language models", "python"]
    by_name = {r.skill_name: r for r in rows}
    assert by_name["large language models"].skill_category == "nlp_genai"
    # Unknown category bucketed to 'other'.
    assert by_name["python"].skill_category == "other"


def test_ingest_backstops_unstated_work_auth_from_raw_text(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _valid_extraction()
    extraction["work_authorization"] = "unstated"
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={
                "extracted_json": extraction,
                "raw_text": "Great role. Note: we do not offer visa sponsorship.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["work_authorization"] == "no_sponsorship"


def test_ingest_does_not_override_stated_work_auth(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _valid_extraction()
    extraction["work_authorization"] = "sponsorship_available"
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={
                "extracted_json": extraction,
                "raw_text": "We do not offer sponsorship.",
                "source_url": "https://x.test/stated",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["work_authorization"] == "sponsorship_available"


def test_ingest_sets_disqualifying_for_opt_from_no_sponsorship(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _valid_extraction()
    extraction["work_authorization"] = "no_sponsorship"
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={"extracted_json": extraction, "raw_text": "no sponsorship role"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["disqualifying_for_opt"] is True


def test_ingest_sets_disqualifying_for_opt_from_opt_no(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _valid_extraction()
    extraction["work_authorization"] = "unstated"
    extraction["opt_accepted"] = "no"
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={"extracted_json": extraction, "raw_text": "opt excluded role"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["disqualifying_for_opt"] is True


def test_ingest_disqualifying_for_opt_false_when_clear(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    extraction = _valid_extraction()
    extraction["work_authorization"] = "sponsorship_available"
    extraction["opt_accepted"] = "yes"
    try:
        client = TestClient(app)
        response = client.post(
            "/api/jobs/ingest",
            json={"extracted_json": extraction, "raw_text": "sponsorship available role"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["disqualifying_for_opt"] is False


def test_re_extract_applies_work_auth_backstop(db_session, monkeypatch):
    # A stored job whose raw_text plainly disqualifies but whose LLM re-extraction
    # returns "unstated" must not silently revert: the re-extract path must apply
    # the same backstop as _persist_job.
    job = Job(
        raw_text="Great role. Note: we do not offer visa sponsorship.",
        raw_text_hash="hash-reextract-backstop",
        extracted_json={"title": "Data Scientist"},
        title="Data Scientist",
        work_authorization="no_sponsorship",
        disqualifying_for_opt=True,
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    def fake_extract(raw_text, session=None):
        return {
            "title": "Data Scientist",
            "role_category": "data_scientist",
            "work_authorization": "unstated",
            "opt_accepted": "unstated",
        }

    monkeypatch.setattr(jobs.jd_extraction, "extract_jd", fake_extract)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.post(f"/api/jobs/{job.id}/re-extract")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["work_authorization"] == "no_sponsorship"
    assert body["disqualifying_for_opt"] is True


def test_list_jobs_source_url_exact_match(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    job1 = Job(raw_text="JD one", raw_text_hash="src-h1",
               source_url="https://x.test/jobs/1", company="Acme")
    job2 = Job(raw_text="JD two", raw_text_hash="src-h2",
               source_url="https://x.test/jobs/10", company="Beta")
    db_session.add_all([job1, job2])
    db_session.commit()

    try:
        client = TestClient(app)
        hit = client.get("/api/jobs", params={"source_url": "https://x.test/jobs/1"})
        # Exact match only: a prefix of a stored URL must NOT match.
        prefix = client.get("/api/jobs", params={"source_url": "https://x.test/jobs"})
        unfiltered = client.get("/api/jobs")
    finally:
        app.dependency_overrides.clear()

    assert hit.status_code == 200
    assert [j["id"] for j in hit.json()] == [str(job1.id)]
    assert prefix.json() == []
    assert len(unfiltered.json()) == 2


def test_list_jobs_source_url_strips_query_before_matching(db_session):
    # Every write path stores a stripped source_url; the list filter must strip
    # the query param too, or a trailing-whitespace URL (e.g. copied from a
    # capture agent) reports found:false for an already-captured job.
    app.dependency_overrides[get_db] = _override_db(db_session)
    job = Job(
        raw_text="JD strip", raw_text_hash="src-strip-h1",
        source_url="https://x.test/jobs/1", company="Acme",
    )
    db_session.add(job)
    db_session.commit()

    try:
        client = TestClient(app)
        hit = client.get("/api/jobs", params={"source_url": "https://x.test/jobs/1\n "})
        # An all-whitespace source_url strips to empty and must be treated as
        # "no filter", not an impossible exact match.
        blank = client.get("/api/jobs", params={"source_url": "   "})
    finally:
        app.dependency_overrides.clear()

    assert hit.status_code == 200
    assert [j["id"] for j in hit.json()] == [str(job.id)]
    assert len(blank.json()) == 1


def test_ingest_job_source_provenance(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        # Agent source
        r_agent = client.post("/api/jobs/ingest", json={
            "extracted_json": _fake_extraction(),
            "raw_text": "Agent JD text 1",
            "source": "agent",
        })
        assert r_agent.status_code == 200
        j_agent = db_session.get(Job, uuid.UUID(r_agent.json()["id"]))
        assert j_agent.source == "agent"

        # Default source (user)
        r_user = client.post("/api/jobs/ingest", json={
            "extracted_json": _fake_extraction(),
            "raw_text": "User JD text 2",
        })
        assert r_user.status_code == 200
        j_user = db_session.get(Job, uuid.UUID(r_user.json()["id"]))
        assert j_user.source == "user"

        # Invalid source -> 422
        r_bad = client.post("/api/jobs/ingest", json={
            "extracted_json": _fake_extraction(),
            "raw_text": "Bad JD text 3",
            "source": "bogus",
        })
        assert r_bad.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_list_jobs_filters_by_source(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    job_user = Job(raw_text="User JD", raw_text_hash="uh1", source="user")
    job_agent = Job(raw_text="Agent JD", raw_text_hash="ah1", source="agent")
    db_session.add_all([job_user, job_agent])
    db_session.commit()
    try:
        client = TestClient(app)
        res_agent = client.get("/api/jobs?source=agent")
        res_user = client.get("/api/jobs?source=user")
        res_invalid = client.get("/api/jobs?source=invalid")
    finally:
        app.dependency_overrides.clear()

    assert res_agent.status_code == 200
    assert len(res_agent.json()) == 1 and res_agent.json()[0]["id"] == str(job_agent.id)
    assert res_user.status_code == 200
    assert len(res_user.json()) == 1 and res_user.json()[0]["id"] == str(job_user.id)
    assert res_invalid.status_code == 422




def test_ingest_url_fallback_matches_the_posting_not_the_string(db_session):
    """SYSTEM.md §11 item 9: the no-raw-text capture path dedupes by POSTING,
    not by string equality. A re-capture arriving through a referral link
    (?gh_src=, ?utm_*) or from the posting's /apply sub-path is the job
    already captured; a different posting on the same board is not."""
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        first_extraction = _valid_extraction()
        first = client.post("/api/jobs/ingest", json={
            "extracted_json": first_extraction,
            "source_url": "https://job-boards.greenhouse.io/acme/jobs/123",
        })
        # A DIFFERENT extraction (different hash — hash dedup must not be the
        # thing passing this test) of the same posting, via a referral link
        # onto the apply sub-path.
        second_extraction = _valid_extraction()
        second_extraction["title"] = "Data Scientist II"
        second = client.post("/api/jobs/ingest", json={
            "extracted_json": second_extraction,
            "source_url": "https://job-boards.greenhouse.io/acme/jobs/123/apply?gh_src=2wwdc8go3us&utm_source=linkedin",
        })
        # A sibling posting shares every leading segment but one — a new row.
        third_extraction = _valid_extraction()
        third_extraction["title"] = "Data Engineer"
        third = client.post("/api/jobs/ingest", json={
            "extracted_json": third_extraction,
            "source_url": "https://job-boards.greenhouse.io/acme/jobs/456?gh_src=2wwdc8go3us",
        })
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == second.status_code == third.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert third.json()["id"] != first.json()["id"]
