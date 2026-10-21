from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.services import explore_overview


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


def test_top_skills_filters_and_counts_distinct_jobs(db_session, client):
    job1 = _seed_job(db_session, raw_hash="job-1", role_category="data_scientist")
    job2 = _seed_job(db_session, raw_hash="job-2", role_category="data_scientist")
    job3 = _seed_job(db_session, raw_hash="job-3", role_category="data_engineer")
    _add_skill(db_session, job1, "Python")
    _add_skill(db_session, job2, "Python")
    _add_skill(db_session, job2, "SQL")
    _add_skill(db_session, job3, "Spark")
    db_session.commit()

    response = client.get("/api/explore/top-skills?role_category=data_scientist")

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


def test_top_skills_sections_split_top_thirty_percent(db_session, client):
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

    response = client.get("/api/explore/top-skills?role_category=data_scientist")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total_skills"] == 10
    assert body["meta"]["top_count"] == 3
    assert len(body["top"]) == 3
    assert len(body["rest"]) == 7
    assert [row["rank"] for row in body["top"]] == [1, 2, 3]
    assert [row["skill_name"] for row in body["top"]] == ["Skill0", "Skill1", "Skill2"]
    assert body["rest"][0]["rank"] == 4


def test_top_skills_rank_tier_buckets(db_session, client):
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

    response = client.get("/api/explore/top-skills?role_category=data_scientist")

    assert response.status_code == 200
    body = response.json()
    assert len(body["top"]) == 3
    assert {row["bucket"] for row in body["top"]} <= {"core", "preferred_top"}


def test_heatmap_returns_percent_jobs_by_role(db_session, client):
    scientist1 = _seed_job(db_session, raw_hash="sci-1", role_category="data_scientist")
    scientist2 = _seed_job(db_session, raw_hash="sci-2", role_category="data_scientist")
    engineer1 = _seed_job(db_session, raw_hash="eng-1", role_category="data_engineer")
    _add_skill(db_session, scientist1, "Python")
    _add_skill(db_session, scientist2, "SQL")
    _add_skill(db_session, engineer1, "Python")
    db_session.commit()

    response = client.get("/api/explore/heatmap?limit=2")

    assert response.status_code == 200
    rows = {
        (item["skill_name"], item["role_category"]): item["pct_jobs"]
        for item in response.json()
    }
    assert rows[("Python", "data_scientist")] == 50.0
    assert rows[("Python", "data_engineer")] == 100.0
    assert rows[("SQL", "data_scientist")] == 50.0
    # The counts behind each share (owner decision D7): the page shows "1 of 2" while a role has fewer
    # than rates.MIN_RATE_N jobs, and the share only from there.
    counts = {(item["skill_name"], item["role_category"]): (item["count"], item["of"]) for item in response.json()}
    assert counts == {("Python", "data_scientist"): (1, 2), ("Python", "data_engineer"): (1, 1),
                      ("SQL", "data_scientist"): (1, 2)}


def test_heatmap_numerator_honours_every_filter(db_session, client):
    """The share's top and bottom count the same jobs: a Level filter that halves
    the role's jobs must halve the skill's count too, never read 200%."""
    senior = _seed_job(db_session, raw_hash="lvl-senior", role_category="data_scientist", level="senior")
    mid = _seed_job(db_session, raw_hash="lvl-mid", role_category="data_scientist", level="mid")
    for job in (senior, mid):
        _add_skill(db_session, job, "Python")
    _add_skill(db_session, mid, "SQL")
    db_session.commit()

    rows = client.get("/api/explore/heatmap", params={"level": "senior"}).json()

    assert rows, "the filtered heatmap has rows"
    assert all(row["pct_jobs"] <= 100 for row in rows), rows
    assert {(r["skill_name"], r["role_category"]): r["pct_jobs"] for r in rows} == {
        ("Python", "data_scientist"): 100.0,
    }


def test_fit_distribution_buckets_scores(db_session, client):
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

    response = client.get("/api/explore/fit-distribution")

    assert response.status_code == 200
    rows = {item["base_resume"]: item["buckets"] for item in response.json()}
    assert rows["hybrid"]["0-20"] == 1
    assert rows["hybrid"]["60-80"] == 1
    assert rows["data_scientist"]["80-100"] == 1


def test_fit_distribution_flags_low_sample_and_reports_n(db_session, client):
    jobs = [
        _seed_job(db_session, raw_hash=f"fit-ls-{i}", role_category="data_scientist")
        for i in range(6)
    ]
    db_session.add_all(
        [_ats_base_row(jobs[i].id, "hybrid", 15.0 + i) for i in range(5)]
        + [_ats_base_row(jobs[5].id, "thin", 88.0)]
    )
    db_session.commit()

    response = client.get("/api/explore/fit-distribution")

    assert response.status_code == 200
    rows = {item["base_resume"]: item for item in response.json()}
    assert rows["hybrid"]["n"] == 5
    assert rows["hybrid"]["low_sample"] is False
    assert rows["thin"]["n"] == 1
    assert rows["thin"]["low_sample"] is True
    assert rows["hybrid"]["buckets"]["0-20"] == 5


def test_fit_distribution_names_each_base_resume(db_session, client):
    """The chart legend says the resume's own name. A slug with no row has none."""
    from app.models.base_resume import BaseResume

    job = _seed_job(db_session, raw_hash="fit-name", role_category="data_scientist")
    db_session.add(BaseResume(slug="ds_base", display_name="Data Science Base", data_json={}))
    db_session.add_all([_ats_base_row(job.id, "ds_base", 70.0), _ats_base_row(job.id, "disk_only", 40.0)])
    db_session.commit()

    response = client.get("/api/explore/fit-distribution")

    names = {row["base_resume"]: row["display_name"] for row in response.json()}
    assert names == {"ds_base": "Data Science Base", "disk_only": None}


def test_overview_aggregates(db_session, client):
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

    r = client.get("/api/explore/overview")
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
    assert wm["on_site"] == 2 and wm["remote"] == 1  # stored "onsite" reads as the key
    skills = {r["skill_name"]: r["n"] for r in body["top_required_skills"]}
    assert skills["Python"] == 2 and skills["SQL"] == 1
    opt = {r["key"]: r["count"] for r in body["work_auth"]["opt"]}
    assert opt["yes"] == 1 and opt["no"] == 1 and opt["unstated"] == 1
    locs = {r["key"]: r["count"] for r in body["locations"]}
    assert locs["Texas"] == 2 and locs["California"] == 1
    # Two yearly-paid data scientists are under the five a role needs to show; the hourly job is not yearly.
    pay = body["pay_by_role"]
    assert pay["roles"] == [] and pay["hidden_roles"] == [{"role_category": "data_scientist", "n": 2}]
    assert len(body["signals"]) <= 5


def test_overview_refuses_mixed_currency_mean(db_session, client):
    j1 = _seed_job(db_session, raw_hash="mc1", role_category="data_scientist")
    j2 = _seed_job(db_session, raw_hash="mc2", role_category="data_scientist")
    j1.salary_min, j1.salary_max, j1.salary_period, j1.salary_currency = 120000, 140000, "year", "USD"
    j2.salary_min, j2.salary_max, j2.salary_period, j2.salary_currency = 70000, 90000, "year", "GBP"
    db_session.flush()

    body = client.get("/api/explore/overview").json()
    usd = client.get("/api/explore/overview", params={"salary_currency": "USD"}).json()

    assert body["meta"]["salary_mixed_currencies"] is True
    assert body["meta"]["salary_year_avg_min"] is None
    assert body["meta"]["salary_year_avg_max"] is None
    by_cur = {r["key"]: r["count"] for r in body["salary_by_currency"]}
    assert by_cur["USD"] == 1 and by_cur["GBP"] == 1
    assert usd["meta"]["salary_mixed_currencies"] is False
    assert round(usd["meta"]["salary_year_avg_min"]) == 120000


def test_overview_null_salary_is_ordinary(db_session, client):
    _seed_job(db_session, raw_hash="ns1", role_category="data_scientist")
    paid = _seed_job(db_session, raw_hash="ns2", role_category="data_scientist")
    paid.salary_min, paid.salary_max, paid.salary_period, paid.salary_currency = (
        100000,
        120000,
        "year",
        "USD",
    )
    db_session.flush()
    body = client.get("/api/explore/overview").json()
    assert body["meta"]["jobs_with_salary"] == 1
    assert body["meta"]["jobs_without_salary"] == 1


def test_overview_filters_by_country(db_session, client):
    us = _seed_job(db_session, raw_hash="c1", role_category="data_scientist")
    de = _seed_job(db_session, raw_hash="c2", role_category="data_scientist")
    us.country, us.country_code = "US", "US"
    de.country, de.country_code = "Germany", "DE"
    db_session.flush()
    r = client.get("/api/explore/overview", params={"country": "DE"})
    assert r.json()["meta"]["total_jobs"] == 1
    # The filter takes any spelling of the country: it matches the stored code.
    named = client.get("/api/explore/overview", params={"country": "Germany"})
    assert named.json()["meta"]["total_jobs"] == 1


def test_overview_groups_one_spelling_per_value(db_session, client):
    """Rows written before values were normalised (or by hand) still group as one key each."""
    seeds = [
        ("sp1", "Hybrid", "Senior", "USA", None),
        ("sp2", "hybrid ", "senior", "United States", None),
        ("sp3", "On-site", "Sr.", None, "US"),
        ("sp4", "Onsite", "mid", "Narnia", None),
        ("sp5", None, None, None, None),
    ]
    for raw_hash, mode, level, country, code in seeds:
        job = _seed_job(db_session, raw_hash=raw_hash, role_category="data_scientist", level=level)
        job.work_mode, job.country, job.country_code = mode, country, code
    db_session.flush()

    body = client.get("/api/explore/overview").json()

    assert body["work_mode"] == [
        {"key": "hybrid", "count": 2}, {"key": "on_site", "count": 2}, {"key": "unstated", "count": 1},
    ]
    assert body["level_breakdown"] == [
        {"key": "senior", "count": 3}, {"key": "mid", "count": 1}, {"key": "unstated", "count": 1},
    ]
    # Every spelling of a country is its ISO code; a country the list cannot name is "unknown",
    # which the web app words as "Not stated".
    assert body["countries"] == [{"key": "US", "count": 3}, {"key": "unknown", "count": 2}]


def test_overview_filters_by_role(db_session, client):
    _seed_job(db_session, raw_hash="f1", role_category="data_scientist")
    _seed_job(db_session, raw_hash="f2", role_category="data_engineer")
    db_session.flush()
    r = client.get("/api/explore/overview", params={"role_category": "data_scientist"})
    assert r.json()["meta"]["total_jobs"] == 1


def test_overview_empty(db_session, client):
    r = client.get("/api/explore/overview")
    body = r.json()
    assert body["meta"]["total_jobs"] == 0
    assert body["meta"]["since"] is None
    assert body["meta"]["salary_year_avg_min"] is None
    assert body["role_mix"] == [] and body["signals"] == []


def test_overview_signals(db_session, client):
    j1 = _seed_job(db_session, raw_hash="s1", role_category="data_scientist")
    j2 = _seed_job(db_session, raw_hash="s2", role_category="data_scientist")
    j1.opt_accepted, j2.opt_accepted = "yes", "no"
    j1.state, j2.state = "Texas", "Texas"
    j1.work_mode, j2.work_mode = "onsite", "onsite"
    _add_skill(db_session, j1, "Python", requirement="required")
    _add_skill(db_session, j2, "Python", requirement="required")
    db_session.flush()
    body = client.get("/api/explore/overview").json()
    titles = " ".join(s["title"] for s in body["signals"])
    # The OPT share is the tab's own tile ("OPT (US student work permit)"): a signal said it twice.
    assert "OPT" not in titles
    assert "Texas" in titles
    assert "Python" in titles
    assert len(body["signals"]) <= 5


def test_overview_signal_copy_has_no_em_dash(db_session):
    """Insight title and detail are sentences. An em dash is a clause joiner, not copy.

    Reads the UNCAPPED list: the endpoint keeps five, and this fixture fires all
    five, so a sixth signal's copy would otherwise go unchecked."""
    j1 = _seed_job(db_session, raw_hash="s1", role_category="data_scientist")
    j2 = _seed_job(db_session, raw_hash="s2", role_category="data_scientist")
    paid = [_seed_job(db_session, raw_hash=f"s3-{i}", role_category="data_scientist") for i in range(5)]
    for job in (j1, j2, *paid):
        job.state, job.work_mode = "Texas", "onsite"
        _add_skill(db_session, job, "Python", requirement="required")
    for job in paid:
        job.salary_min, job.salary_max, job.salary_period, job.salary_currency = 150000, 180000, "year", "USD"
    db_session.flush()
    signals = explore_overview.candidate_signals(explore_overview.build_overview(db_session))
    assert len(signals) == 5, [s["title"] for s in signals]
    copy = " ".join(f"{s['title']} {s['detail']}" for s in signals)
    assert "Remote roles are scarce" in copy
    assert "—" not in copy
    # The payload carries pay as numbers; the browser words them (lib/money.ts), never the server.
    best = next(s for s in signals if s["title"].startswith("Best-paying role:"))
    assert best["detail"] == "Average top of the pay range, from 5 jobs that list pay."
    assert (best["amount"], best["currency"], best["converted"]) == (180000, "USD", False)


# AI/ML Engineer out-earns Data Scientist. A reserved bucket is appended to out-earn both.
_TRACKS = [("data_scientist", 100000, 150000), ("ai_ml_engineer", 160000, 200000)]


def _best_paying_titles(db_session, pay):
    """Overview signal titles with five yearly-USD jobs per (role, min, max), the fewest a role
    shows with; a role of None is stored NULL and reads back as `unknown`."""
    for i, (role, low, high) in enumerate(pay):
        for k in range(explore_overview.MIN_ROLE_JOBS):
            job = _seed_job(db_session, raw_hash=f"pay-{i}-{k}", role_category="data_scientist")
            job.role_category = role
            job.salary_min, job.salary_max = low, high
            job.salary_period, job.salary_currency = "year", "USD"
    db_session.flush()
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = client.get("/api/explore/overview").json()
    finally:
        app.dependency_overrides.clear()
    return [signal["title"] for signal in body["signals"]]


def test_best_paying_signal_uses_role_label(db_session):
    """The insight names the catalog label, never the slug."""
    titles = _best_paying_titles(db_session, _TRACKS)
    assert "Best-paying role: AI/ML Engineer" in titles
    assert not any("ai_ml_engineer" in title for title in titles)


def test_best_paying_signal_skips_the_unknown_bucket(db_session):
    """A higher-paying `unknown` bucket is not a track."""
    titles = _best_paying_titles(db_session, [*_TRACKS, (None, 300000, 400000)])
    best = [title for title in titles if title.startswith("Best-paying role:")]
    assert best == ["Best-paying role: AI/ML Engineer"]


def test_best_paying_signal_skips_the_other_bucket(db_session):
    """A higher-paying `other` bucket is not a track either."""
    titles = _best_paying_titles(db_session, [*_TRACKS, ("other", 300000, 400000)])
    best = [title for title in titles if title.startswith("Best-paying role:")]
    assert best == ["Best-paying role: AI/ML Engineer"]


def _seed_pay(db_session, tag, role, count, top, currency):
    for i in range(count):
        job = _seed_job(db_session, raw_hash=f"{tag}-{i}", role_category=role)
        job.salary_max, job.salary_period, job.salary_currency = top, "year", currency


def _best_paying(client, **params):
    signals = client.get("/api/explore/overview", params=params).json()["signals"]
    return [s for s in signals if s["title"].startswith("Best-paying role:")]


def test_best_paying_signal_compares_pay_in_your_currency(db_session, client, monkeypatch):
    """₹2,400,000 is not more than $170,000: converted, it is about €26,700 against €156,400.
    With no rate the rupee jobs are left out, never compared as posted."""
    _seed_pay(db_session, "inr", "data_scientist", 5, 2_400_000, "INR")
    _seed_pay(db_session, "usd", "ai_ml_engineer", 5, 170_000, "USD")
    db_session.flush()

    _in(monkeypatch, "EUR", {**_RATES, "rates": {**_RATES["rates"], "INR": Decimal("90.0")}})
    best = _best_paying(client)
    assert [s["title"] for s in best] == ["Best-paying role: AI/ML Engineer"]
    assert best[0]["currency"] == "EUR" and best[0]["converted"] is True
    assert round(best[0]["amount"]) == 156394

    _in(monkeypatch, "USD", None)
    best = _best_paying(client)
    assert [s["title"] for s in best] == ["Best-paying role: AI/ML Engineer"]
    assert best[0]["converted"] is False


def test_top_skill_signal_title_starts_with_words(db_session):
    """Skill names are stored casefolded, so the title leads with words and
    keeps the stored name verbatim instead of inventing a casing for it."""
    job = _seed_job(db_session, raw_hash="skill-title", role_category="data_scientist")
    _add_skill(db_session, job, "sql", requirement="required")
    db_session.flush()
    signals = explore_overview.candidate_signals(explore_overview.build_overview(db_session))
    assert "Most required skill: sql (100% of jobs)" in [s["title"] for s in signals]


def test_role_mix_over_time_groups_by_week(db_session, client):
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
    # Seeded LAST but belongs to the FIRST week, so insertion order is not
    # sorted order. Without it the ordering assertion below passes even when
    # the endpoint does not sort at all — do not drop it.
    _seed_job(
        db_session,
        raw_hash="week-4",
        role_category="data_engineer",
        created_at=datetime(2026, 4, 21, tzinfo=UTC),
    )
    db_session.commit()

    response = client.get("/api/explore/role-mix-over-time?window=week")

    assert response.status_code == 200
    rows = response.json()
    assert {"week_start": "2026-04-20", "role_category": "data_scientist", "count": 2} in rows
    assert {"week_start": "2026-04-27", "role_category": "data_engineer", "count": 1} in rows
    # The ordering the endpoint documents: week, then role_category.
    keys = [(r["week_start"], r["role_category"]) for r in rows]
    assert keys == sorted(keys)


def test_role_mix_over_time_follows_filters_and_zero_fills_weeks(db_session, client):
    """A Country filter changes the series, and the weeks run unbroken from the
    first to the last, with 0 for a role in a week that had none of it."""
    rows = [
        ("rm-us-1", "data_scientist", "US", datetime(2026, 4, 7, tzinfo=UTC)),
        ("rm-us-2", "data_engineer", "US", datetime(2026, 4, 22, tzinfo=UTC)),
        ("rm-de-1", "data_scientist", "DE", datetime(2026, 4, 14, tzinfo=UTC)),
    ]
    for raw_hash, role, country, created_at in rows:
        job = _seed_job(db_session, raw_hash=raw_hash, role_category=role, created_at=created_at)
        job.country = job.country_code = country
    db_session.commit()

    us = client.get("/api/explore/role-mix-over-time", params={"country": "US"}).json()
    every = client.get("/api/explore/role-mix-over-time").json()

    # US only: the DE job's week (2026-04-13) is still a week, with zeros.
    assert us == [
        {"week_start": "2026-04-06", "role_category": "data_engineer", "count": 0},
        {"week_start": "2026-04-06", "role_category": "data_scientist", "count": 1},
        {"week_start": "2026-04-13", "role_category": "data_engineer", "count": 0},
        {"week_start": "2026-04-13", "role_category": "data_scientist", "count": 0},
        {"week_start": "2026-04-20", "role_category": "data_engineer", "count": 1},
        {"week_start": "2026-04-20", "role_category": "data_scientist", "count": 0},
    ]
    assert {"week_start": "2026-04-13", "role_category": "data_scientist", "count": 1} in every


def test_top_skills_collapses_one_name_across_categories(db_session, client):
    job1 = _seed_job(db_session, raw_hash="agg-1", role_category="data_scientist")
    job2 = _seed_job(db_session, raw_hash="agg-2", role_category="data_scientist")
    job3 = _seed_job(db_session, raw_hash="agg-3", role_category="data_scientist")
    # Same canonical name "data modeling", disagreeing categories.
    _add_skill(db_session, job1, "data modeling", category="ml_modeling")
    _add_skill(db_session, job2, "data modeling", category="ml_modeling")
    _add_skill(db_session, job3, "data modeling", category="methodology")
    db_session.commit()

    response = client.get("/api/explore/top-skills")

    assert response.status_code == 200
    rows = response.json()["top"] + response.json()["rest"]
    modeling = [r for r in rows if r["skill_name"] == "data modeling"]
    # One row, not two — no split by category.
    assert len(modeling) == 1
    assert modeling[0]["n"] == 3
    # Tie-break: most-frequent category (ml_modeling, 2 vs 1) wins.
    assert modeling[0]["skill_category"] == "ml_modeling"


def test_fit_distribution_excludes_soft_deleted_base_resume(db_session, client):
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

    response = client.get("/api/explore/fit-distribution")

    assert response.status_code == 200
    slugs = {row["base_resume"] for row in response.json()}
    assert "data_scientist" in slugs   # on-disk-only slug preserved
    assert "old_track" not in slugs    # soft-deleted slug excluded


def test_a_count_of_one_job_is_one_job():
    """"(1 jobs)" and "from 1 jobs" are the plural bug appendix D §1 names."""
    one = {
        "meta": {"total_jobs": 1, "jobs_without_salary": 0},
        "work_auth": {"opt": []},
        "locations": [{"key": "Tacoma, WA", "count": 1}],
        "top_required_skills": [{"skill_name": "sql", "n": 1}],
        "pay_by_role": {"currency": "USD", "roles": [
            {"role_category": "data_scientist", "avg_max": 150000, "n": 1, "converted_count": 0}]},
        "work_mode": [{"key": "onsite", "count": 1}],
    }
    copy = {s["title"]: s["detail"] for s in explore_overview.candidate_signals(one)}
    assert "Most common location: Tacoma, WA (1 job)" in copy
    assert copy["Most required skill: sql (100% of jobs)"] == (
        "Required in 1 of 1 job, more than any other skill.")
    assert copy["Best-paying role: Data Scientist"] == (
        "Average top of the pay range, from 1 job that lists pay.")
    six = {**one, "meta": {**one["meta"], "total_jobs": 6},
           "work_mode": [{"key": "remote", "count": 1}, {"key": "onsite", "count": 5}]}
    remote = {s["title"]: s["detail"] for s in explore_overview.candidate_signals(six)}
    assert remote["Remote roles are scarce (17%)"] == "Only 1 of 6 jobs is remote."


@pytest.mark.parametrize("code", ["USD", "EUR", "CHF"])
def test_best_paying_pay_is_a_number_the_browser_words(code):
    """The server words no money ("$150K" came from a symbol table here): the signal carries the
    figure and its currency, and lib/money.ts writes it."""
    one = {
        "meta": {"total_jobs": 1, "jobs_without_salary": 0},
        "work_auth": {"opt": []}, "locations": [], "top_required_skills": [],
        "pay_by_role": {"currency": code, "roles": [
            {"role_category": "data_scientist", "avg_max": 150000, "n": 1, "converted_count": 1}]},
        "work_mode": [{"key": "onsite", "count": 1}],
    }
    best = next(s for s in explore_overview.candidate_signals(one) if s["title"].startswith("Best-paying"))
    assert (best["amount"], best["currency"], best["converted"]) == (150000, code, True)
    assert "150" not in best["detail"]
    assert not hasattr(explore_overview, "_thousands") and not hasattr(explore_overview, "_SYMBOLS")


# --- yearly pay by role in your currency (plan Task 3.9) ---------------------------------------

# ECB reference rates, units per euro: £87,700 and $108,700 are both €100,000.
_RATES = {"base": "EUR", "date": "2026-10-19", "fetched_at": "2026-10-19T16:30:00+00:00",
          "rates": {"USD": Decimal("1.0870"), "GBP": Decimal("0.8770")}}


def _in(monkeypatch, home, rates):
    from app.services import fx_rates, money_settings

    monkeypatch.setattr(money_settings, "home_currency", lambda session=None: home)
    monkeypatch.setattr(fx_rates, "current", lambda session: rates)


def _paid(db_session, tag, role, count, currency, top, low=None):
    for i in range(count):
        job = _seed_job(db_session, raw_hash=f"{tag}-{i}", role_category=role)
        job.salary_min, job.salary_max, job.salary_period, job.salary_currency = low, top, "year", currency


def test_yearly_pay_by_role_is_in_your_home_currency(db_session, client, monkeypatch):
    _paid(db_session, "ds-eur", "data_scientist", 3, "EUR", 90000, 70000)
    _paid(db_session, "ds-gbp", "data_scientist", 2, "GBP", 87700, 70160)
    _paid(db_session, "ml-usd", "ai_ml_engineer", 5, "USD", 108700)
    _paid(db_session, "de-eur", "data_engineer", 2, "EUR", 80000)       # under five: hidden
    _paid(db_session, "ds-ars", "data_scientist", 1, "ARS", 30_000_000)  # no ECB rate: left out
    _paid(db_session, "ds-none", "data_scientist", 1, None, 95000)       # no currency: left out
    db_session.flush()
    _in(monkeypatch, "EUR", _RATES)

    pay = client.get("/api/explore/overview").json()["pay_by_role"]

    assert (pay["currency"], pay["rate_date"], pay["min_jobs"]) == ("EUR", "2026-10-19", 5)
    roles = {r["role_category"]: r for r in pay["roles"]}
    assert [r["role_category"] for r in pay["roles"]] == ["ai_ml_engineer", "data_scientist"]
    ds = roles["data_scientist"]
    assert (ds["n"], ds["converted_count"], ds["posted_currencies"]) == (5, 2, ["EUR", "GBP"])
    assert round(ds["avg_max"]) == 94000 and round(ds["avg_min"]) == 74000
    ml = roles["ai_ml_engineer"]
    assert (ml["n"], ml["converted_count"], round(ml["avg_max"]), ml["avg_min"]) == (5, 5, 100000, None)
    assert pay["hidden_roles"] == [{"role_category": "data_engineer", "n": 2}]
    assert pay["unconverted"] == 2
    assert pay["converted_count"] == 7
    assert pay["posted_currencies"] == [{"key": "USD", "count": 5}, {"key": "GBP", "count": 2}]


def test_with_no_rates_only_pay_in_your_currency_counts(db_session, client, monkeypatch):
    _paid(db_session, "eur", "data_scientist", 5, "EUR", 90000)
    _paid(db_session, "gbp", "data_scientist", 2, "GBP", 87700)
    db_session.flush()
    _in(monkeypatch, "EUR", None)

    pay = client.get("/api/explore/overview").json()["pay_by_role"]

    assert pay["rate_date"] is None and pay["converted_count"] == 0 and pay["unconverted"] == 2
    assert [(r["role_category"], r["n"], r["converted_count"]) for r in pay["roles"]] == [("data_scientist", 5, 0)]
