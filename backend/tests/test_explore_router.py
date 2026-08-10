from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.models.job_skill import JobSkill


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed_job(
    db_session,
    *,
    raw_hash: str,
    role_category: str,
    level: str = "senior",
    employment_type: str = "full_time",
    created_at: datetime | None = None,
):
    job = Job(
        raw_text=f"JD {raw_hash}",
        raw_text_hash=raw_hash,
        extracted_json={"title": raw_hash},
        title=raw_hash,
        company="Acme",
        role_category=role_category,
        level=level,
        employment_type=employment_type,
        extracted_at=datetime.now(UTC),
        created_at=created_at or datetime(2026, 4, 22, tzinfo=UTC),
    )
    db_session.add(job)
    db_session.flush()
    return job


def _ats_base_row(job_id, slug, composite, phase="base"):
    return AtsScore(
        job_id=job_id, target_type="base_resume", target_id=slug, phase=phase,
        composite=composite, subscores_json={}, skill_table_json=[],
        config_version="c1", engine_version="ats-1.0.0",
    )


def _add_skill(db_session, job, name, category="language", requirement="required"):
    db_session.add(
        JobSkill(
            job_id=job.id,
            skill_name=name,
            skill_category=category,
            requirement_level=requirement,
        )
    )


def test_top_skills_filters_and_counts_distinct_jobs(db_session):
    job1 = _seed_job(db_session, raw_hash="job-1", role_category="data_scientist")
    job2 = _seed_job(db_session, raw_hash="job-2", role_category="data_scientist")
    job3 = _seed_job(db_session, raw_hash="job-3", role_category="data_engineer")
    _add_skill(db_session, job1, "Python")
    _add_skill(db_session, job2, "Python")
    _add_skill(db_session, job2, "SQL")
    _add_skill(db_session, job3, "Spark")
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/top-skills?role_category=data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total_jobs"] == 2
    assert body["top"][0]["skill_name"] == "Python"
    assert body["top"][0]["n"] == 2
    assert body["rest"][0]["skill_name"] == "SQL"
    assert body["rest"][0]["n"] == 1
    assert body["top"][0]["bucket"] in {"core", "preferred_top", "below_threshold"}
    assert "rank" in body["top"][0]
    assert "rank_percentile" in body["top"][0]


def test_top_skills_sections_split_top_thirty_percent(db_session):
    jobs = [
        _seed_job(db_session, raw_hash=f"split-job-{i}", role_category="data_scientist")
        for i in range(10)
    ]
    skill_names = [f"Skill{i}" for i in range(10)]
    for index, job in enumerate(jobs):
        for skill_index, name in enumerate(skill_names):
            if skill_index <= index:
                _add_skill(db_session, job, name)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/top-skills?role_category=data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total_skills"] == 10
    assert body["meta"]["top_count"] == 3
    assert len(body["top"]) == 3
    assert len(body["rest"]) == 7
    assert [row["rank"] for row in body["top"]] == [1, 2, 3]
    assert [row["skill_name"] for row in body["top"]] == ["Skill0", "Skill1", "Skill2"]
    assert body["rest"][0]["rank"] == 4


def test_top_skills_rank_tier_buckets(db_session):
    jobs = [
        _seed_job(db_session, raw_hash=f"job-{i}", role_category="data_scientist")
        for i in range(10)
    ]
    skill_names = [f"Skill{i}" for i in range(10)]
    for index, job in enumerate(jobs):
        for skill_index, name in enumerate(skill_names):
            if skill_index <= index:
                level = "required" if skill_index < 3 else "preferred"
                _add_skill(db_session, job, name, requirement=level)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/top-skills?role_category=data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["top"]) == 3
    assert {row["bucket"] for row in body["top"]} <= {"core", "preferred_top"}


def test_heatmap_returns_percent_jobs_by_role(db_session):
    scientist1 = _seed_job(db_session, raw_hash="sci-1", role_category="data_scientist")
    scientist2 = _seed_job(db_session, raw_hash="sci-2", role_category="data_scientist")
    engineer1 = _seed_job(db_session, raw_hash="eng-1", role_category="data_engineer")
    _add_skill(db_session, scientist1, "Python")
    _add_skill(db_session, scientist2, "SQL")
    _add_skill(db_session, engineer1, "Python")
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/heatmap?limit=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = {
        (item["skill_name"], item["role_category"]): item["pct_jobs"]
        for item in response.json()
    }
    assert rows[("Python", "data_scientist")] == 50.0
    assert rows[("Python", "data_engineer")] == 100.0
    assert rows[("SQL", "data_scientist")] == 50.0


def test_fit_distribution_buckets_scores(db_session):
    job1 = _seed_job(db_session, raw_hash="fit-job-1", role_category="data_scientist")
    job2 = _seed_job(db_session, raw_hash="fit-job-2", role_category="data_scientist")
    job3 = _seed_job(db_session, raw_hash="fit-job-3", role_category="data_scientist")
    db_session.add_all(
        [
            _ats_base_row(job1.id, "hybrid", 15.0),
            _ats_base_row(job2.id, "hybrid", 61.0),
            _ats_base_row(job3.id, "data_scientist", 88.0),
            # tailored rows must not count toward the base-composite distribution
            _ats_base_row(job3.id, "data_scientist", 99.0, phase="tailored"),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/fit-distribution")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = {item["base_resume"]: item["buckets"] for item in response.json()}
    assert rows["hybrid"]["0-20"] == 1
    assert rows["hybrid"]["60-80"] == 1
    assert rows["data_scientist"]["80-100"] == 1


def test_overview_aggregates(db_session):
    j1 = _seed_job(db_session, raw_hash="o1", role_category="data_scientist", level="entry")
    j2 = _seed_job(db_session, raw_hash="o2", role_category="data_scientist", level="mid")
    j3 = _seed_job(db_session, raw_hash="o3", role_category="data_engineer", level="entry")
    j1.work_mode, j2.work_mode, j3.work_mode = "onsite", "remote", "onsite"
    j1.opt_accepted, j2.opt_accepted, j3.opt_accepted = "yes", "unstated", "no"
    j1.work_authorization = "sponsorship_available"
    j1.state, j2.state, j3.state = "Texas", "Texas", "California"
    j1.salary_min, j1.salary_max, j1.salary_period = 120000, 160000, "year"
    j2.salary_min, j2.salary_max, j2.salary_period = 100000, 140000, "year"
    j3.salary_min, j3.salary_max, j3.salary_period = 50, 60, "hour"  # ignored
    j1.salary_currency = j2.salary_currency = "USD"
    j1.country = "US"
    j2.country = "US"
    j3.country = "CA"
    _add_skill(db_session, j1, "Python", requirement="required")
    _add_skill(db_session, j2, "Python", requirement="required")
    _add_skill(db_session, j3, "Python", requirement="preferred")
    _add_skill(db_session, j1, "SQL", requirement="required")
    db_session.flush()

    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = client.get("/api/explore/overview")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()

    assert body["meta"]["total_jobs"] == 3
    assert body["meta"]["role_category_count"] == 2
    assert body["meta"]["since"] is not None
    assert round(body["meta"]["salary_year_avg_min"]) == 110000
    assert round(body["meta"]["salary_year_avg_max"]) == 150000
    assert body["meta"]["salary_year_currency"] == "USD"
    assert not body["meta"]["salary_mixed_currencies"]

    role = {r["key"]: r["count"] for r in body["role_mix"]}
    assert role["data_scientist"] == 2 and role["data_engineer"] == 1
    wm = {r["key"]: r["count"] for r in body["work_mode"]}
    assert wm["onsite"] == 2 and wm["remote"] == 1
    skills = {r["skill_name"]: r["n"] for r in body["top_required_skills"]}
    assert skills["Python"] == 2 and skills["SQL"] == 1
    opt = {r["key"]: r["count"] for r in body["work_auth"]["opt"]}
    assert opt["yes"] == 1 and opt["no"] == 1 and opt["unstated"] == 1
    locs = {r["key"]: r["count"] for r in body["locations"]}
    assert locs["Texas"] == 2 and locs["California"] == 1
    sbr = {r["role_category"]: r for r in body["salary_by_role"]}
    assert "data_scientist" in sbr and "data_engineer" not in sbr
    assert len(body["signals"]) <= 5


def test_overview_refuses_mixed_currency_mean(db_session):
    j1 = _seed_job(db_session, raw_hash="mc1", role_category="data_scientist")
    j2 = _seed_job(db_session, raw_hash="mc2", role_category="data_scientist")
    j1.salary_min, j1.salary_max, j1.salary_period, j1.salary_currency = 120000, 140000, "year", "USD"
    j2.salary_min, j2.salary_max, j2.salary_period, j2.salary_currency = 70000, 90000, "year", "GBP"
    db_session.flush()

    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = client.get("/api/explore/overview").json()
        usd = client.get("/api/explore/overview", params={"salary_currency": "USD"}).json()
    finally:
        app.dependency_overrides.clear()

    assert body["meta"]["salary_mixed_currencies"] is True
    assert body["meta"]["salary_year_avg_min"] is None
    assert body["meta"]["salary_year_avg_max"] is None
    by_cur = {r["key"]: r["count"] for r in body["salary_by_currency"]}
    assert by_cur["USD"] == 1 and by_cur["GBP"] == 1
    assert usd["meta"]["salary_mixed_currencies"] is False
    assert round(usd["meta"]["salary_year_avg_min"]) == 120000


def test_overview_null_salary_is_ordinary(db_session):
    _seed_job(db_session, raw_hash="ns1", role_category="data_scientist")
    paid = _seed_job(db_session, raw_hash="ns2", role_category="data_scientist")
    paid.salary_min, paid.salary_max, paid.salary_period, paid.salary_currency = (
        100000,
        120000,
        "year",
        "USD",
    )
    db_session.flush()
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = client.get("/api/explore/overview").json()
    finally:
        app.dependency_overrides.clear()
    assert body["meta"]["jobs_with_salary"] == 1
    assert body["meta"]["jobs_without_salary"] == 1


def test_overview_filters_by_country(db_session):
    us = _seed_job(db_session, raw_hash="c1", role_category="data_scientist")
    de = _seed_job(db_session, raw_hash="c2", role_category="data_scientist")
    us.country = "US"
    de.country = "DE"
    db_session.flush()
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = client.get("/api/explore/overview", params={"country": "DE"})
    finally:
        app.dependency_overrides.clear()
    assert r.json()["meta"]["total_jobs"] == 1


def test_overview_filters_by_role(db_session):
    _seed_job(db_session, raw_hash="f1", role_category="data_scientist")
    _seed_job(db_session, raw_hash="f2", role_category="data_engineer")
    db_session.flush()
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = client.get("/api/explore/overview", params={"role_category": "data_scientist"})
    finally:
        app.dependency_overrides.clear()
    assert r.json()["meta"]["total_jobs"] == 1


def test_overview_empty(db_session):
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = client.get("/api/explore/overview")
    finally:
        app.dependency_overrides.clear()
    body = r.json()
    assert body["meta"]["total_jobs"] == 0
    assert body["meta"]["since"] is None
    assert body["meta"]["salary_year_avg_min"] is None
    assert body["role_mix"] == [] and body["signals"] == []


def test_overview_signals(db_session):
    j1 = _seed_job(db_session, raw_hash="s1", role_category="data_scientist")
    j2 = _seed_job(db_session, raw_hash="s2", role_category="data_scientist")
    j1.opt_accepted, j2.opt_accepted = "yes", "no"
    j1.state, j2.state = "Texas", "Texas"
    j1.work_mode, j2.work_mode = "onsite", "onsite"
    _add_skill(db_session, j1, "Python", requirement="required")
    _add_skill(db_session, j2, "Python", requirement="required")
    db_session.flush()
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = client.get("/api/explore/overview").json()
    finally:
        app.dependency_overrides.clear()
    titles = " ".join(s["title"] for s in body["signals"])
    assert "OPT" in titles
    assert "Texas" in titles
    assert "Python" in titles
    assert len(body["signals"]) <= 5


def test_role_mix_over_time_groups_by_week(db_session):
    _seed_job(
        db_session,
        raw_hash="week-1",
        role_category="data_scientist",
        created_at=datetime(2026, 4, 22, tzinfo=UTC),
    )
    _seed_job(
        db_session,
        raw_hash="week-2",
        role_category="data_scientist",
        created_at=datetime(2026, 4, 23, tzinfo=UTC),
    )
    _seed_job(
        db_session,
        raw_hash="week-3",
        role_category="data_engineer",
        created_at=datetime(2026, 4, 29, tzinfo=UTC),
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/role-mix-over-time?window=week")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = response.json()
    assert {"week_start": "2026-04-20", "role_category": "data_scientist", "count": 2} in rows
    assert {"week_start": "2026-04-27", "role_category": "data_engineer", "count": 1} in rows


def test_top_skills_collapses_one_name_across_categories(db_session):
    job1 = _seed_job(db_session, raw_hash="agg-1", role_category="data_scientist")
    job2 = _seed_job(db_session, raw_hash="agg-2", role_category="data_scientist")
    job3 = _seed_job(db_session, raw_hash="agg-3", role_category="data_scientist")
    # Same canonical name "data modeling", disagreeing categories.
    _add_skill(db_session, job1, "data modeling", category="ml_modeling")
    _add_skill(db_session, job2, "data modeling", category="ml_modeling")
    _add_skill(db_session, job3, "data modeling", category="methodology")
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/top-skills")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = response.json()["top"] + response.json()["rest"]
    modeling = [r for r in rows if r["skill_name"] == "data modeling"]
    # One row, not two — no split by category.
    assert len(modeling) == 1
    assert modeling[0]["n"] == 3
    # Tie-break: most-frequent category (ml_modeling, 2 vs 1) wins.
    assert modeling[0]["skill_category"] == "ml_modeling"


def test_fit_distribution_excludes_soft_deleted_base_resume(db_session):
    from datetime import UTC, datetime

    from app.models.base_resume import BaseResume
    from app.models.job import Job

    job = Job(
        raw_text="x",
        raw_text_hash="explore-soft-delete",
        extracted_json={"title": "DS", "company": "Acme"},
        title="DS",
        company="Acme",
        role_category="data_scientist",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    # An on-disk-only slug (not in base_resumes) must still appear.
    db_session.add(_ats_base_row(job.id, "data_scientist", 85.0))
    # A soft-deleted DB slug must be excluded.
    deleted = BaseResume(slug="old_track", data_json={}, deleted_at=datetime.now(UTC))
    db_session.add(deleted)
    db_session.add(_ats_base_row(job.id, "old_track", 70.0))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/fit-distribution")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    slugs = {row["base_resume"] for row in response.json()}
    assert "data_scientist" in slugs   # on-disk-only slug preserved
    assert "old_track" not in slugs    # soft-deleted slug excluded
