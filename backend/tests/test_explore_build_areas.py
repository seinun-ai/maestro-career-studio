"""Tests for /api/explore/build-areas (gap frequency classified by KB evidence)."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.ats_score import AtsScore
from app.models.career_kb import KBEntity, KBPoint, KBPortLog, KBProfile
from app.models.job import Job


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _get(db_session, path="/api/explore/build-areas"):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).get(path)
    finally:
        app.dependency_overrides.clear()


def _seed_job(db_session, raw_hash: str, role_category="data_scientist") -> Job:
    job = Job(
        raw_text=f"JD {raw_hash}",
        raw_text_hash=raw_hash,
        extracted_json={"title": raw_hash},
        title=raw_hash,
        company="Acme",
        role_category=role_category,
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    return job


def _skill_gap(
    jd_skill,
    *,
    requirement_level="required",
    potential_points=2.0,
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
        gap["score_effect"] = score_effect
    return gap


def _seed_gap_row(
    db_session,
    job,
    gaps,
    *,
    slug="data_scientist",
    category_key="missing_skills",
    composite=50.0,
):
    db_session.add(
        AtsScore(
            job_id=job.id,
            target_type="base_resume",
            target_id=slug,
            phase="base",
            composite=composite,
            subscores_json={},
            skill_table_json=[],
            config_version="c1",
            engine_version="ats-1.0.0",
            gaps_json={
                "base_composite": composite,
                "subscores": {},
                "engine_version": "ats-1.0.0",
                "config_version": "c1",
                "categories": [
                    {"key": category_key, "title": category_key, "gaps": list(gaps)}
                ],
            },
        )
    )


def _seed_entity_with_point(db_session, *, title, text, kind="project"):
    entity = KBEntity(kind=kind, title=title, status="completed")
    db_session.add(entity)
    db_session.flush()
    point = KBPoint(entity_id=entity.id, text=text, state="approved", origin="manual")
    db_session.add(point)
    db_session.flush()
    return entity, point


def test_build_areas_classifies_missing_in_kb_and_ported(db_session):
    job1 = _seed_job(db_session, "j1")
    job2 = _seed_job(db_session, "j2")
    _seed_gap_row(
        db_session,
        job1,
        [_skill_gap("Kubernetes"), _skill_gap("Tableau"), _skill_gap("Airflow")],
    )
    _seed_gap_row(db_session, job2, [_skill_gap("Kubernetes")])

    # Tableau: approved point evidence, never ported -> in_kb.
    _seed_entity_with_point(
        db_session, title="BI Revamp", text="Built Tableau dashboards for execs"
    )
    # Airflow: approved point evidence WITH a port log -> ported.
    airflow_entity, airflow_point = _seed_entity_with_point(
        db_session, title="Pipeline Modernization", text="Migrated cron jobs to Airflow"
    )
    db_session.add(
        KBPortLog(
            entity_id=airflow_entity.id,
            point_id=airflow_point.id,
            resume_kind="base",
            resume_key="data_engineer",
            section="experience",
            ported_text="Migrated cron jobs to Airflow",
        )
    )
    db_session.commit()

    resp = _get(db_session)
    assert resp.status_code == 200
    rows = {row["skill"]: row for row in resp.json()}
    assert rows["Kubernetes"]["status"] == "missing"
    assert rows["Kubernetes"]["n_jobs"] == 2
    assert rows["Kubernetes"]["kb_points"] == 0
    assert rows["Tableau"]["status"] == "in_kb"
    assert rows["Tableau"]["kb_points"] == 1
    assert rows["Tableau"]["kb_entities"] == ["BI Revamp"]
    assert rows["Airflow"]["status"] == "ported"
    assert rows["Airflow"]["kb_entities"] == ["Pipeline Modernization"]
    # Sorted by demand first.
    assert resp.json()[0]["skill"] == "Kubernetes"


def test_build_areas_profile_skills_count_as_evidence(db_session):
    job = _seed_job(db_session, "j1")
    _seed_gap_row(db_session, job, [_skill_gap("dbt")])
    db_session.add(
        KBProfile(id=1, skills_json=[{"category": "Data", "items": ["dbt", "SQL"]}])
    )
    db_session.commit()

    rows = _get(db_session).json()
    assert rows[0]["skill"] == "dbt"
    assert rows[0]["status"] == "in_kb"
    assert rows[0]["kb_points"] == 0


def test_build_areas_folds_alias_and_case_variants(db_session):
    job1 = _seed_job(db_session, "j1")
    job2 = _seed_job(db_session, "j2")
    # "AWS" and "Amazon Web Services" are one alias group in aliases.yaml.
    _seed_gap_row(db_session, job1, [_skill_gap("AWS")])
    _seed_gap_row(db_session, job2, [_skill_gap("Amazon Web Services")])
    db_session.commit()

    rows = _get(db_session).json()
    assert len(rows) == 1
    assert rows[0]["n_jobs"] == 2
    assert rows[0]["skill"] in ("AWS", "Amazon Web Services")


def test_build_areas_word_boundary_no_false_positive(db_session):
    job = _seed_job(db_session, "j1")
    _seed_gap_row(db_session, job, [_skill_gap("ML")])
    # "xml" must NOT count as evidence for "ml".
    _seed_entity_with_point(db_session, title="Parser", text="Wrote an xml parser")
    db_session.commit()

    rows = _get(db_session).json()
    assert rows[0]["skill"] == "ML"
    assert rows[0]["status"] == "missing"


def test_build_areas_short_alias_forms_do_not_prose_match(db_session):
    """'tf' (TensorFlow alias) must not match a TF-IDF bullet — the engine's
    short-form prose guard applies to analytics too."""
    job = _seed_job(db_session, "j1")
    _seed_gap_row(db_session, job, [_skill_gap("TensorFlow")])
    _seed_entity_with_point(
        db_session,
        title="Search Ranking",
        text="Built a TF-IDF vectorizer for search ranking",
    )
    db_session.commit()

    rows = _get(db_session).json()
    assert rows[0]["skill"] == "TensorFlow"
    assert rows[0]["status"] == "missing"
    assert rows[0]["kb_points"] == 0


def test_build_areas_ported_certification(db_session):
    """Cert ports log point_id=None; their provenance must still reach 'ported'."""
    job = _seed_job(db_session, "j1")
    _seed_gap_row(db_session, job, [_skill_gap("AWS")])
    entity = KBEntity(
        kind="certification",
        title="AWS Solutions Architect",
        org="Amazon",
        status="completed",
    )
    db_session.add(entity)
    db_session.flush()
    db_session.add(
        KBPortLog(
            entity_id=entity.id,
            point_id=None,
            resume_kind="base",
            resume_key="data_engineer",
            section="certifications",
            ported_text="AWS Solutions Architect (Amazon)",
        )
    )
    db_session.commit()

    rows = _get(db_session).json()
    assert rows[0]["status"] == "ported"
    assert rows[0]["kb_entities"] == ["AWS Solutions Architect"]


def test_build_areas_certification_titles_match(db_session):
    job = _seed_job(db_session, "j1")
    _seed_gap_row(db_session, job, [_skill_gap("AWS")])
    entity = KBEntity(
        kind="certification", title="AWS Solutions Architect", org="Amazon", status="completed"
    )
    db_session.add(entity)
    db_session.commit()

    rows = _get(db_session).json()
    assert rows[0]["status"] == "in_kb"
    assert rows[0]["kb_entities"] == ["AWS Solutions Architect"]


def test_build_areas_ignores_requirement_kind_and_filters(db_session):
    job = _seed_job(db_session, "j1", role_category="data_engineer")
    _seed_gap_row(
        db_session,
        job,
        [
            _skill_gap("Spark"),
            {
                "gap_id": "coverage:0",
                "kind": "requirement",
                "jd_skill": "Own the roadmap end to end",
                "requirement_level": "preferred",
                "potential_points": 1.0,
                "diagnostic": {"coverage_score": 0.1},
            },
        ],
    )
    db_session.commit()

    rows = _get(db_session).json()
    assert [row["skill"] for row in rows] == ["Spark"]
    filtered = _get(
        db_session, "/api/explore/build-areas?role_category=data_scientist"
    ).json()
    assert filtered == []


def test_build_areas_hygiene_wording_tiers_separately(db_session):
    """Hygiene mirror_wording gaps are a footnote: the resume already matches at
    full keyword credit so the literal token moves no score, hence they never
    count as demand and always rank below effective gaps. (The discriminator is
    score movement, NOT auto-resolution — tailoring auto-mirrors adds_credit
    gaps too; kb_resolver._wording_auto_resolution never reads score_effect.)"""
    _seed_gap_row(
        db_session,
        _seed_job(db_session, "j1"),
        [_skill_gap(
            "Kubernetes", score_effect="hygiene", fix_hint="mirror_wording"
        )],
        category_key="mirror_wording",
    )
    _seed_gap_row(
        db_session,
        _seed_job(db_session, "j2"),
        [_skill_gap(
            "Kubernetes", score_effect="hygiene", fix_hint="mirror_wording"
        )],
        category_key="mirror_wording",
    )
    _seed_gap_row(db_session, _seed_job(db_session, "j3"), [_skill_gap("Airflow")])
    db_session.commit()

    rows = _get(db_session).json()
    # Airflow gaps in ONE job, Kubernetes hygienes in two — effective still wins.
    assert [row["skill"] for row in rows] == ["Airflow", "Kubernetes"]
    assert rows[1]["tier"] == "wording"
    assert rows[1]["n_jobs"] == 0
    assert rows[1]["wording_jobs"] == 2
    assert rows[1]["avg_potential_points"] == 0.0
    assert rows[1]["category"] is None
    assert rows[0]["wording_jobs"] == 0


def test_build_areas_adds_credit_wording_is_effective(db_session):
    """A semantic match below full credit really does gain score from the literal
    token, so it stays real headroom — but it is not a skill to learn."""
    _seed_gap_row(
        db_session,
        _seed_job(db_session, "j1"),
        [_skill_gap(
            "Kubernetes", score_effect="adds_credit", fix_hint="mirror_wording"
        )],
        category_key="mirror_wording",
    )
    db_session.commit()

    row = _get(db_session).json()[0]
    assert row["n_jobs"] == 1
    assert row["wording_jobs"] == 0
    assert row["status"] == "missing"
    assert row["tier"] == "surface"
    assert row["category"] == "mirror_wording"


def test_build_areas_build_tier_requires_kb_missing_and_missing_skills(db_session):
    _seed_gap_row(db_session, _seed_job(db_session, "j1"), [_skill_gap("Kubernetes")])
    _seed_gap_row(db_session, _seed_job(db_session, "j2"), [_skill_gap("Tableau")])
    _seed_gap_row(
        db_session,
        _seed_job(db_session, "j3"),
        [_skill_gap("Spark")],
        category_key="dual_place",
    )
    _seed_entity_with_point(
        db_session, title="BI Revamp", text="Built Tableau dashboards for execs"
    )
    db_session.commit()

    rows = {row["skill"]: row for row in _get(db_session).json()}
    # Nothing on the resume, nothing in the KB -> genuinely learn it.
    assert rows["Kubernetes"]["status"] == "missing"
    assert rows["Kubernetes"]["tier"] == "build"
    # KB evidence exists -> port it, don't "build" it.
    assert rows["Tableau"]["status"] == "in_kb"
    assert rows["Tableau"]["tier"] == "surface"
    # dual_place means the token is already in the skills list: corroborate it.
    assert rows["Spark"]["status"] == "missing"
    assert rows["Spark"]["tier"] == "surface"
    assert rows["Spark"]["category"] == "dual_place"


def test_build_areas_mixed_skill_counts_both_axes(db_session):
    """One skill, both kinds of occurrence: one row, tiered by the effective one."""
    _seed_gap_row(
        db_session,
        _seed_job(db_session, "ja"),
        [_skill_gap(
            "Kubernetes", score_effect="hygiene", fix_hint="mirror_wording"
        )],
        category_key="mirror_wording",
    )
    _seed_gap_row(db_session, _seed_job(db_session, "jb"), [_skill_gap("Kubernetes")])
    db_session.commit()

    rows = _get(db_session).json()
    assert len(rows) == 1
    assert rows[0]["n_jobs"] == 1
    assert rows[0]["wording_jobs"] == 1
    assert rows[0]["tier"] == "build"
    assert rows[0]["category"] == "missing_skills"


def test_build_areas_reads_only_the_best_base_per_job(db_session):
    """A weak secondary base must not manufacture demand the real resume covers."""
    job = _seed_job(db_session, "j1")
    _seed_gap_row(
        db_session, job, [_skill_gap("Kubernetes")], slug="data_scientist", composite=72.0
    )
    _seed_gap_row(
        db_session,
        job,
        [_skill_gap("Kubernetes"), _skill_gap("COBOL")],
        slug="data_engineer",
        composite=41.0,
    )
    db_session.commit()

    assert [row["skill"] for row in _get(db_session).json()] == ["Kubernetes"]


def test_build_areas_limit_bounds_the_whole_panel_effective_first(db_session):
    """limit is a budget for the WHOLE response, and the wording footnote may only
    spend what effective gaps left over — never displace a truncated real gap."""
    for i, skill in enumerate(("Kubernetes", "Airflow", "Spark")):
        _seed_gap_row(db_session, _seed_job(db_session, f"e{i}"), [_skill_gap(skill)])
    for i, skill in enumerate(("Tableau", "dbt")):
        _seed_gap_row(
            db_session,
            _seed_job(db_session, f"w{i}"),
            [_skill_gap(skill, score_effect="hygiene", fix_hint="mirror_wording")],
            category_key="mirror_wording",
        )
    db_session.commit()

    # Budget smaller than the effective pool: wording gets nothing.
    capped = _get(db_session, "/api/explore/build-areas?limit=2").json()
    assert [row["tier"] for row in capped] == ["build", "build"]

    # Budget with one slot to spare: exactly one wording row rides along.
    spilled = _get(db_session, "/api/explore/build-areas?limit=4").json()
    assert [row["tier"] for row in spilled] == ["build", "build", "build", "wording"]

    # Budget above both pools: everything, still effective-first.
    everything = _get(db_session, "/api/explore/build-areas?limit=20").json()
    assert [row["tier"] for row in everything] == [
        "build",
        "build",
        "build",
        "wording",
        "wording",
    ]
