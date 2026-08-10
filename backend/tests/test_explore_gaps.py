from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.job import Job


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


def _skill_gap(
    jd_skill,
    *,
    requirement_level="required",
    potential_points=1.0,
    score_effect=None,
    fix_hint="absent",
):
    gap = {
        "gap_id": f"skill:{jd_skill.lower()}",
        "kind": "skill",
        "jd_skill": jd_skill,
        "requirement_level": requirement_level,
        "potential_points": potential_points,
        "diagnostic": {"fix_hint": fix_hint},
        "actions": ["add_keyword", "skip"],
        "enrichment": None,
    }
    if score_effect is not None:
        # gap_analysis._skill_gap stamps score_effect on mirror_wording gaps only.
        gap["score_effect"] = score_effect
    return gap


def _requirement_gap(jd_line):
    """A weak_coverage gap: jd_skill is a whole JD sentence, not a skill name."""
    return {
        "gap_id": "coverage:0",
        "kind": "requirement",
        "jd_skill": jd_line,
        "requirement_level": "preferred",
        "potential_points": 0.0,
        "diagnostic": {},
        "actions": ["user_input", "skip"],
        "enrichment": None,
    }


def _gaps_json(
    *,
    missing_skill_gaps=(),
    weak_coverage_gaps=(),
    wording_gaps=(),
    base_composite=42.0,
):
    """Minimal gaps_json shape mirroring gap_analysis.build_gaps output."""
    categories = [
        {
            "key": "missing_skills",
            "title": "Missing skills",
            "description": "JD skills with no evidence on the resume",
            "gaps": list(missing_skill_gaps),
        }
    ]
    if wording_gaps:
        categories.append(
            {
                "key": "mirror_wording",
                "title": "Mirror JD wording",
                "description": "Skills evidenced under a different label",
                "gaps": list(wording_gaps),
            }
        )
    if weak_coverage_gaps:
        categories.append(
            {
                "key": "weak_coverage",
                "title": "Weak coverage",
                "description": "JD requirements the resume answers thinly",
                "gaps": list(weak_coverage_gaps),
            }
        )
    return {
        "base_composite": base_composite,
        "subscores": {},
        "engine_version": "ats-1.0.0",
        "config_version": "c1",
        "categories": categories,
    }


def _base_row(job_id, slug, composite, *, gaps_json=None, created_at=None):
    return AtsScore(
        job_id=job_id,
        target_type="base_resume",
        target_id=slug,
        phase="base",
        composite=composite,
        subscores_json={},
        skill_table_json=[],
        gaps_json=gaps_json,
        config_version="c1",
        engine_version="ats-1.0.0",
        created_at=created_at or datetime(2026, 4, 22, tzinfo=UTC),
    )


def _tailored_row(job_id, target_id, composite, *, application_id=None, created_at=None):
    return AtsScore(
        job_id=job_id,
        target_type="application",
        target_id=target_id,
        phase="tailored",
        composite=composite,
        subscores_json={},
        skill_table_json=[],
        gaps_json=None,
        config_version="c1",
        engine_version="ats-1.0.0",
        application_id=application_id,
        created_at=created_at or datetime(2026, 4, 22, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# gap-frequency
# ---------------------------------------------------------------------------


def test_gap_frequency_ranks_by_distinct_jobs(db_session):
    job1 = _seed_job(db_session, raw_hash="gf-1", role_category="data_engineer")
    job2 = _seed_job(db_session, raw_hash="gf-2", role_category="data_engineer")
    db_session.add_all(
        [
            _base_row(
                job1.id,
                "de_track",
                40.0,
                gaps_json=_gaps_json(
                    missing_skill_gaps=[
                        _skill_gap("kubernetes", potential_points=4.0),
                        _skill_gap("spark", potential_points=2.0),
                    ]
                ),
            ),
            _base_row(
                job2.id,
                "de_track",
                45.0,
                gaps_json=_gaps_json(
                    missing_skill_gaps=[_skill_gap("kubernetes", potential_points=6.0)]
                ),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = response.json()
    by_skill = {r["skill"]: r for r in rows}
    assert by_skill["kubernetes"]["n_jobs"] == 2
    assert by_skill["spark"]["n_jobs"] == 1
    # kubernetes (2 jobs) ranks above spark (1 job)
    skills_in_order = [r["skill"] for r in rows]
    assert skills_in_order.index("kubernetes") < skills_in_order.index("spark")
    # avg_potential_points is the mean across occurrences: (4.0 + 6.0) / 2 == 5.0
    assert by_skill["kubernetes"]["avg_potential_points"] == 5.0
    assert by_skill["kubernetes"]["category"] == "missing_skills"
    assert by_skill["kubernetes"]["requirement_level"] == "required"


def test_gap_frequency_counts_only_best_base_per_job(db_session):
    # score_all_bases writes one base row per (job, base slug), so a weak
    # secondary base can gap on skills the resume you would actually send
    # covers. Only the best-scoring base per job may feed the ranking.
    job = _seed_job(db_session, raw_hash="gf-best-base", role_category="data_engineer")
    db_session.add_all(
        [
            _base_row(
                job.id,
                "strong",
                80.0,
                gaps_json=_gaps_json(
                    missing_skill_gaps=[
                        _skill_gap("kubernetes", potential_points=3.0)
                    ]
                ),
            ),
            _base_row(
                job.id,
                "weak",
                40.0,
                gaps_json=_gaps_json(
                    missing_skill_gaps=[
                        _skill_gap("kubernetes", potential_points=9.0),
                        _skill_gap("spark"),
                    ]
                ),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    by_skill = {r["skill"]: r for r in response.json()}
    assert "kubernetes" in by_skill
    # spark gapped only on the losing base, so it is not a real gap at all
    assert "spark" not in by_skill
    # the losing base's occurrence must not leak into the aggregates either:
    # 3.0 is the winner's value alone, not the (3.0 + 9.0) / 2 mean of both
    assert by_skill["kubernetes"]["avg_potential_points"] == 3.0


def test_gap_frequency_best_base_tie_breaks_deterministically(db_session):
    # Equal composites must not make the winner depend on row order, or the
    # panel would flip between reruns; lowest target_id wins. Two jobs with
    # OPPOSITE insertion orders — a one-job test would still pass under both
    # "first row wins" and "last row wins", which are the two order-dependent
    # bugs the tie-break exists to rule out.
    job1 = _seed_job(db_session, raw_hash="gf-tie-1", role_category="data_engineer")
    job2 = _seed_job(db_session, raw_hash="gf-tie-2", role_category="data_engineer")
    db_session.add_all(
        [
            # job1: the losing slug is inserted first
            _base_row(
                job1.id,
                "beta",
                50.0,
                gaps_json=_gaps_json(missing_skill_gaps=[_skill_gap("airflow")]),
            ),
            _base_row(
                job1.id,
                "alpha",
                50.0,
                gaps_json=_gaps_json(missing_skill_gaps=[_skill_gap("spark")]),
            ),
            # job2: the winning slug is inserted first
            _base_row(
                job2.id,
                "alpha",
                50.0,
                gaps_json=_gaps_json(missing_skill_gaps=[_skill_gap("dbt")]),
            ),
            _base_row(
                job2.id,
                "beta",
                50.0,
                gaps_json=_gaps_json(missing_skill_gaps=[_skill_gap("kafka")]),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # "alpha" wins both jobs regardless of which row the scan saw first
    assert {r["skill"] for r in response.json()} == {"spark", "dbt"}


def test_gap_frequency_excludes_requirement_kind(db_session):
    # weak_coverage gaps carry a whole JD sentence as jd_skill; ranking them
    # alongside skill names pollutes the list and eats top-N slots.
    jd_line = "Own the end-to-end ML lifecycle in production"
    job = _seed_job(db_session, raw_hash="gf-kind", role_category="data_engineer")
    db_session.add(
        _base_row(
            job.id,
            "de_track",
            40.0,
            gaps_json=_gaps_json(
                missing_skill_gaps=[_skill_gap("kubernetes")],
                weak_coverage_gaps=[_requirement_gap(jd_line)],
            ),
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    skills = {r["skill"] for r in response.json()}
    assert "kubernetes" in skills
    assert jd_line not in skills


def test_gap_frequency_excludes_hygiene_wording(db_session):
    # A hygiene mirror_wording gap means the resume ALREADY matches the skill at
    # full keyword credit, so there is no headroom to report — listing it under
    # "what you keep lacking" contradicts the Gaps panel's wording footnote,
    # which tells the user adding the token will not change their score.
    job = _seed_job(db_session, raw_hash="gf-hygiene", role_category="data_engineer")
    db_session.add(
        _base_row(
            job.id,
            "de_track",
            40.0,
            gaps_json=_gaps_json(
                missing_skill_gaps=[_skill_gap("spark")],
                wording_gaps=[
                    _skill_gap(
                        "kubernetes",
                        score_effect="hygiene",
                        fix_hint="mirror_wording",
                        potential_points=7.0,
                    )
                ],
            ),
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    skills = {r["skill"] for r in response.json()}
    assert "spark" in skills
    # every kubernetes occurrence is hygiene, so it gets no row at all
    assert "kubernetes" not in skills


def test_gap_frequency_keeps_adds_credit_wording(db_session):
    # The hygiene sibling: below full keyword credit, the literal JD token earns
    # real credit, so an adds_credit mirror_wording gap IS effective demand.
    job = _seed_job(db_session, raw_hash="gf-adds", role_category="data_engineer")
    db_session.add(
        _base_row(
            job.id,
            "de_track",
            40.0,
            gaps_json=_gaps_json(
                wording_gaps=[
                    _skill_gap(
                        "kubernetes",
                        score_effect="adds_credit",
                        fix_hint="mirror_wording",
                        potential_points=5.0,
                    )
                ]
            ),
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    by_skill = {r["skill"]: r for r in response.json()}
    assert by_skill["kubernetes"]["n_jobs"] == 1
    assert by_skill["kubernetes"]["avg_potential_points"] == 5.0
    assert by_skill["kubernetes"]["category"] == "mirror_wording"


def test_gap_frequency_hygiene_occurrences_do_not_inflate_aggregates(db_session):
    # Same skill, two hygiene jobs and one effective job. The hygiene pair
    # OUTVOTES the effective occurrence on every most-common axis and carries a
    # much larger potential_points, so each assertion below fails if the skip is
    # dropped — n_jobs 3, avg 7.0, category mirror_wording, level preferred.
    hygiene_jobs = [
        _seed_job(db_session, raw_hash="gf-hyg-a", role_category="data_engineer"),
        _seed_job(db_session, raw_hash="gf-hyg-b", role_category="data_engineer"),
    ]
    for job in hygiene_jobs:
        db_session.add(
            _base_row(
                job.id,
                "de_track",
                40.0,
                gaps_json=_gaps_json(
                    wording_gaps=[
                        _skill_gap(
                            "kubernetes",
                            score_effect="hygiene",
                            fix_hint="mirror_wording",
                            requirement_level="preferred",
                            potential_points=9.0,
                        )
                    ]
                ),
            )
        )
    effective_job = _seed_job(
        db_session, raw_hash="gf-hyg-c", role_category="data_engineer"
    )
    db_session.add(
        _base_row(
            effective_job.id,
            "de_track",
            40.0,
            gaps_json=_gaps_json(
                missing_skill_gaps=[
                    _skill_gap(
                        "kubernetes",
                        requirement_level="required",
                        potential_points=3.0,
                    )
                ]
            ),
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/gap-frequency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = {r["skill"]: r for r in response.json()}["kubernetes"]
    assert row["n_jobs"] == 1
    assert row["avg_potential_points"] == 3.0
    assert row["category"] == "missing_skills"
    assert row["requirement_level"] == "required"


def test_gap_frequency_role_filter_narrows(db_session):
    job1 = _seed_job(db_session, raw_hash="gf-role-de", role_category="data_engineer")
    job2 = _seed_job(db_session, raw_hash="gf-role-ds", role_category="data_scientist")
    db_session.add_all(
        [
            _base_row(
                job1.id,
                "de_track",
                40.0,
                gaps_json=_gaps_json(missing_skill_gaps=[_skill_gap("kubernetes")]),
            ),
            _base_row(
                job2.id,
                "ds_track",
                40.0,
                gaps_json=_gaps_json(missing_skill_gaps=[_skill_gap("pytorch")]),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(
            "/api/explore/gap-frequency?role_category=data_engineer"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    skills = {r["skill"] for r in response.json()}
    assert "kubernetes" in skills
    assert "pytorch" not in skills


# ---------------------------------------------------------------------------
# ats-over-time
# ---------------------------------------------------------------------------


def test_ats_over_time_buckets_weekly_by_phase_and_role(db_session):
    ds1 = _seed_job(db_session, raw_hash="aot-ds1", role_category="data_scientist")
    ds2 = _seed_job(db_session, raw_hash="aot-ds2", role_category="data_scientist")
    de1 = _seed_job(db_session, raw_hash="aot-de1", role_category="data_engineer")
    db_session.add_all(
        [
            # week of 2026-04-20, base, data_scientist -> avg 50, n 2
            _base_row(ds1.id, "a", 40.0, created_at=datetime(2026, 4, 21, tzinfo=UTC)),
            _base_row(ds2.id, "b", 60.0, created_at=datetime(2026, 4, 22, tzinfo=UTC)),
            # week of 2026-04-27, tailored, data_scientist -> avg 80, n 1
            _tailored_row(
                ds1.id, "app-1", 80.0, created_at=datetime(2026, 4, 29, tzinfo=UTC)
            ),
            # week of 2026-04-20, base, data_engineer -> avg 30, n 1
            _base_row(de1.id, "c", 30.0, created_at=datetime(2026, 4, 21, tzinfo=UTC)),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/ats-over-time")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = response.json()
    assert {
        "week_start": "2026-04-20",
        "phase": "base",
        "role_category": "data_scientist",
        "avg_composite": 50.0,
        "n": 2,
    } in rows
    assert {
        "week_start": "2026-04-27",
        "phase": "tailored",
        "role_category": "data_scientist",
        "avg_composite": 80.0,
        "n": 1,
    } in rows
    assert {
        "week_start": "2026-04-20",
        "phase": "base",
        "role_category": "data_engineer",
        "avg_composite": 30.0,
        "n": 1,
    } in rows


# ---------------------------------------------------------------------------
# tailoring-lift
# ---------------------------------------------------------------------------


def test_tailoring_lift_joins_base_and_tailored(db_session):
    job = _seed_job(db_session, raw_hash="tl-de", role_category="data_engineer")
    app_row = Application(job_id=job.id, base_resume="de_track")
    db_session.add(app_row)
    db_session.flush()
    db_session.add_all(
        [
            _base_row(job.id, "de_track", 40.0),
            _tailored_row(job.id, str(app_row.id), 60.0, application_id=app_row.id),
        ]
    )

    # A second application missing its tailored row must be skipped entirely.
    job2 = _seed_job(db_session, raw_hash="tl-ds", role_category="data_scientist")
    app_row2 = Application(job_id=job2.id, base_resume="ds_track")
    db_session.add(app_row2)
    db_session.flush()
    db_session.add(_base_row(job2.id, "ds_track", 50.0))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/tailoring-lift")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = {r["role_category"]: r for r in response.json()}
    assert rows["data_engineer"]["n"] == 1
    assert rows["data_engineer"]["avg_base"] == 40.0
    assert rows["data_engineer"]["avg_tailored"] == 60.0
    assert rows["data_engineer"]["avg_lift"] == 20.0
    # overall "all" row aggregates every completed application
    assert rows["all"]["n"] == 1
    assert rows["all"]["avg_lift"] == 20.0
    # the data_scientist application missing its tailored phase is skipped
    assert "data_scientist" not in rows


def test_tailoring_lift_uses_latest_tailored_row_per_application(db_session):
    # Re-tailoring appends a new tailored row under the SAME application_id.
    # Only the latest (created_at desc, id desc) may count — never both.
    job = _seed_job(db_session, raw_hash="tl-latest", role_category="data_engineer")
    app_row = Application(job_id=job.id, base_resume="de_track")
    db_session.add(app_row)
    db_session.flush()
    db_session.add_all(
        [
            _base_row(job.id, "de_track", 40.0),
            _tailored_row(
                job.id,
                str(app_row.id),
                50.0,
                application_id=app_row.id,
                created_at=datetime(2026, 4, 21, tzinfo=UTC),
            ),
            _tailored_row(
                job.id,
                str(app_row.id),
                60.0,
                application_id=app_row.id,
                created_at=datetime(2026, 4, 23, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/explore/tailoring-lift")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = {r["role_category"]: r for r in response.json()}
    # n counts the application once (not both tailored rows)
    assert rows["data_engineer"]["n"] == 1
    # lift uses the newer tailored composite (60), not the older (50): 60 - 40 = 20
    assert rows["data_engineer"]["avg_tailored"] == 60.0
    assert rows["data_engineer"]["avg_lift"] == 20.0
    assert rows["all"]["n"] == 1
    assert rows["all"]["avg_lift"] == 20.0
