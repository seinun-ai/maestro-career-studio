import json
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.resume_lint_report import ResumeLintReport
from app.models.tailoring_session import TailoringSession
from app.services import prompt_assembly, prompts, quick_tailor, tailoring_session
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed_job(db_session):
    job = Job(raw_text="jd", raw_text_hash="qt-hash", extracted_json=SAMPLE_JD)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _seed_base(db_session, tmp_path, monkeypatch, slug="data_scientist", resume_json=None):
    resume_json = resume_json if resume_json is not None else SAMPLE_RESUME
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(resume_json))
    db_session.add(BaseResume(slug=slug, data_json=resume_json))
    db_session.commit()
    return slug


TAILOR_OPS = {
    "ops": [
        {"kind": "add_skill_item", "category": "Additional Skills", "item": "Salesforce"},
        {"kind": "add_skill_item", "category": "Additional Skills", "item": "Snowflake"},
    ]
}


def _mock_llm(monkeypatch, enrichments=None, tailor_ops=None):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key, session=None: (prompts.PROMPT_DIR / f"{key}.txt").read_text(
            encoding="utf-8"
        ),
    )
    calls = []

    def fake_call_openai(**kwargs):
        calls.append(kwargs)
        if kwargs.get("trace_name") == "gap-enrichment":
            return {"enrichments": enrichments or []}
        return tailor_ops or TAILOR_OPS

    monkeypatch.setattr(tailoring_session.llm, "call_openai", fake_call_openai)
    return calls


def _mock_render(monkeypatch, error=None):
    def fake_render(db, application_id, *, template_id=None):
        if error is not None:
            raise error
        return ("/tmp/x.tex", "/tmp/x.pdf")

    monkeypatch.setattr(
        "app.services.quick_tailor.application_render.render_resume", fake_render
    )


def _quick_tailor(client, job, slug):
    return client.post(f"/api/jobs/{job.id}/quick-tailor", json={"base_resume": slug})


# --- policy unit tests (pure, no DB) -----------------------------------------


def _gap(
    gap_id,
    category_kind="skill",
    jd_skill="X",
    actions=("add_keyword", "skip"),
    enrichment=None,
    diagnostic=None,
):
    return {
        "gap_id": gap_id,
        "kind": category_kind,
        "jd_skill": jd_skill,
        "actions": list(actions),
        "enrichment": enrichment,
        "diagnostic": diagnostic or {},
    }


def _gaps_json(**categories):
    return {"categories": [{"key": key, "gaps": gaps} for key, gaps in categories.items()]}


def test_policy_missing_skill_lands_in_skills_default_category():
    gaps = _gaps_json(missing_skills=[_gap("skill:x", jd_skill="Snowflake")])
    resolutions, applied = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    [r] = resolutions
    assert r["action"] == "add_keyword"
    assert r["payload"]["placement_target"] == {
        "section": "skills",
        "index_or_category": "Additional Skills",
    }
    assert r["payload"]["wording"] == "Snowflake"
    assert applied and "Snowflake" in applied[0]


def test_policy_missing_skill_reuses_auto_verified_library_entry():
    gap = _gap("skill:kafka", jd_skill="Kafka")
    gap["library_candidates"] = [
        {
            "kind": "disabled",
            "section": "projects",
            "index": 0,
            "name": "Ingestion Pipeline",
            "auto": True,
        }
    ]
    gaps = _gaps_json(missing_skills=[gap])

    resolutions, applied = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)

    assert resolutions[0]["action"] == "enable_entry"
    assert applied and "Ingestion Pipeline" in applied[0]


def test_policy_missing_skill_uses_enriched_skills_category():
    enrichment = {
        "suggested_placement": {"section": "skills", "index_or_category": "Cloud"}
    }
    gaps = _gaps_json(missing_skills=[_gap("skill:x", enrichment=enrichment)])
    resolutions, _ = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    assert resolutions[0]["payload"]["placement_target"]["index_or_category"] == "Cloud"


def test_policy_honesty_invariant_absent_skill_never_leaves_skills():
    # Even a (hypothetically) bad enrichment pointing at experience must be
    # overridden: the planned target is ALWAYS section=skills for missing skills.
    enrichment = {
        "suggested_placement": {"section": "experience", "index_or_category": 0}
    }
    gaps = _gaps_json(missing_skills=[_gap("skill:x", enrichment=enrichment)])
    resolutions, _ = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    assert resolutions[0]["payload"]["placement_target"]["section"] == "skills"
    assert (
        resolutions[0]["payload"]["placement_target"]["index_or_category"]
        == "Additional Skills"
    )


def test_policy_keywords_into_skills_off_skips_missing():
    gaps = _gaps_json(missing_skills=[_gap("skill:x")])
    profile = {**quick_tailor.DEFAULTS, "keywords_into_skills": False}
    resolutions, applied = quick_tailor.plan_resolutions(gaps, profile)
    assert resolutions == [{"gap_id": "skill:x", "action": "skip"}]
    assert applied == []


def test_policy_mirror_wording_lands_exact_token_in_skills():
    # A mirror gap plans its deterministic exact-token add into SKILLS via the
    # wording_auto path — even when enrichment suggests a prose placement. A
    # dual_place gap (token already in skills) keeps the enriched prose placement.
    mirror = _gap(
        "skill:a",
        jd_skill="AWS",
        enrichment={
            "suggested_placement": {"section": "experience", "index_or_category": 0}
        },
        diagnostic={"fix_hint": "mirror_wording"},
    )
    dual = _gap(
        "skill:c",
        jd_skill="Python",
        enrichment={
            "suggested_placement": {"section": "experience", "index_or_category": 0}
        },
        diagnostic={"fix_hint": "dual_place"},
    )
    unplaced = _gap(
        "skill:b",
        jd_skill="Tableau",
        enrichment=None,
        diagnostic={"fix_hint": "dual_place"},
    )
    gaps = _gaps_json(mirror_wording=[mirror], dual_place=[dual, unplaced])
    resolutions, applied = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    by_id = {r["gap_id"]: r for r in resolutions}
    assert by_id["skill:a"]["action"] == "add_keyword"
    assert by_id["skill:a"]["payload"]["placement_target"]["section"] == "skills"
    assert by_id["skill:a"]["payload"]["provenance"] == {"source": "wording_auto"}
    assert by_id["skill:c"]["action"] == "add_keyword"
    assert by_id["skill:c"]["payload"]["placement_target"]["section"] == "experience"
    assert by_id["skill:b"]["action"] == "skip"  # null placement -> skip
    assert any("AWS" in line for line in applied)
    # The mirror_wording switch governs BOTH the wording_auto and the dual path.
    profile = {**quick_tailor.DEFAULTS, "mirror_wording": False}
    resolutions, _ = quick_tailor.plan_resolutions(gaps, profile)
    assert all(r["action"] == "skip" for r in resolutions)


def test_policy_projects_placement_gated_by_project_keyword_injection():
    gap = _gap(
        "skill:a",
        enrichment={
            "suggested_placement": {"section": "projects", "index_or_category": 0}
        },
        diagnostic={"fix_hint": "dual_place"},
    )
    gaps = _gaps_json(dual_place=[gap])
    resolutions, _ = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    assert resolutions[0]["action"] == "skip"  # default: gate off
    profile = {**quick_tailor.DEFAULTS, "project_keyword_injection": True}
    resolutions, _ = quick_tailor.plan_resolutions(gaps, profile)
    assert resolutions[0]["action"] == "add_keyword"
    assert resolutions[0]["payload"]["placement_target"]["section"] == "projects"


def test_policy_summary_rename_gates_summary_and_title_gaps():
    summary_gap = {
        "gap_id": "summary:value_prop",
        "kind": "summary",
        "actions": ["user_input", "skip"],
        "enrichment": {"suggested_wording": "Senior DS driving ML revenue."},
    }
    title_gap = {
        "gap_id": "title:alignment",
        "kind": "title",
        "actions": ["user_input", "skip"],
        "enrichment": None,
    }
    gaps = _gaps_json(title_structure=[summary_gap, title_gap])
    resolutions, _ = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    assert all(r["action"] == "skip" for r in resolutions)  # default: off
    profile = {**quick_tailor.DEFAULTS, "summary_rename": True}
    resolutions, _ = quick_tailor.plan_resolutions(gaps, profile)
    by_id = {r["gap_id"]: r for r in resolutions}
    assert by_id["summary:value_prop"]["action"] == "user_input"
    assert by_id["summary:value_prop"]["payload"]["text"] == "Senior DS driving ML revenue."
    assert by_id["title:alignment"]["action"] == "skip"  # no wording -> skip


# --- endpoint integration ----------------------------------------------------


def test_quick_tailor_happy_path(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["nothing_to_tailor"] is False
    assert body["pdf_ready"] is True
    assert body["applied"]  # human-readable lines
    assert body["compare"]["after"] >= body["compare"]["before"]
    application = db_session.get(Application, UUID(body["application_id"]))
    assert application is not None
    row = db_session.get(TailoringSession, UUID(body["session_id"]))
    assert row.status == "tailored"
    # missing-skill resolutions all target skills (honesty invariant end to end)
    for item in row.resolutions_json:
        if item["action"] == "add_keyword":
            assert item["payload"]["placement_target"]["section"] == "skills"


def test_quick_tailor_zero_actionable_never_calls_tailor(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    # Fully-enabled base: the default fixture's disabled entries now legitimately
    # produce auto-resolutions via self-nomination, which is actionable work —
    # this test pins the genuinely-zero-actionable path.
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    for section in ("experience", "projects"):
        for entry in resume.get(section) or []:
            entry["enabled"] = True
    slug = _seed_base(db_session, tmp_path, monkeypatch, resume_json=resume)
    calls = _mock_llm(monkeypatch)
    _mock_render(monkeypatch)
    monkeypatch.setattr(
        "app.routers.jobs.quick_tailor.get_profile",
        lambda session=None: {
            **quick_tailor.DEFAULTS,
            "keywords_into_skills": False,
            "mirror_wording": False,
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["nothing_to_tailor"] is True
    assert body["applied"] == []
    assert body["application_id"] is None
    assert body["pdf_ready"] is False
    assert [c for c in calls if c.get("trace_name") == "tailoring"] == []
    assert db_session.scalars(select(Application)).first() is None
    assert db_session.get(TailoringSession, UUID(body["session_id"])).status == "open"


IN_PROGRESS_409_DETAIL = (
    "An in-progress tailoring session with saved resolutions exists for this job "
    "and base resume. Finish or close it in the web app, or run quick tailor "
    "after discarding it."
)


def _seed_open_session(db_session, job, slug, resolutions, status="open"):
    row = TailoringSession(
        job_id=job.id,
        base_resume=slug,
        status=status,
        gaps_json={"categories": []},
        resolutions_json=resolutions,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_quick_tailor_409_when_open_session_has_resolutions(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)
    existing = _seed_open_session(
        db_session,
        job,
        slug,
        [
            {"gap_id": "skill:x", "action": "skip"},
            {
                "gap_id": "skill:y",
                "action": "add_keyword",
                "payload": {"placement_target": {"section": "skills"}, "wording": "AWS"},
            },
        ],
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == IN_PROGRESS_409_DETAIL
    # The hand-built session is left untouched (not superseded).
    db_session.expire_all()
    assert db_session.get(TailoringSession, existing.id).status == "open"


def test_quick_tailor_proceeds_when_open_session_only_skips(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)
    _seed_open_session(db_session, job, slug, [{"gap_id": "skill:x", "action": "skip"}])

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["nothing_to_tailor"] is False


def test_quick_tailor_proceeds_when_open_session_empty_resolutions(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)
    _seed_open_session(db_session, job, slug, [])

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_quick_tailor_proceeds_when_prior_session_not_open(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)
    # A non-open (already tailored) session with resolutions must NOT block.
    _seed_open_session(
        db_session,
        job,
        slug,
        [{"gap_id": "skill:y", "action": "add_keyword", "payload": {"wording": "AWS"}}],
        status="tailored",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_quick_tailor_surfaces_health_warning(db_session, tmp_path, monkeypatch):
    # The created session's transient health_warning must reach the response
    # (fix B5), including on the nothing_to_tailor path.
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)

    seeded = _seed_open_session(db_session, job, slug, [])
    seeded.health_warning = (
        "Base resume health is 42 (F); tailoring a weak base produces weak output."
    )
    monkeypatch.setattr(
        "app.routers.jobs.tailoring_session.create_session",
        lambda job_id, base_resume, session=None: seeded,
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["nothing_to_tailor"] is True
    assert body["health_warning"] == seeded.health_warning


def test_quick_tailor_health_gate_409_passthrough(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    db_session.add(
        ResumeLintReport(
            resume_kind="base",
            resume_key=slug,
            report_json={
                "score": 70,
                "grade": "C",
                "gates": [
                    {
                        "id": "S1",
                        "tier": "fatal",
                        "status": "fail",
                        "label": "Parse fidelity",
                        "detail": "drops text",
                    }
                ],
            },
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "S1" in response.json()["detail"]


def test_quick_tailor_render_failure_degrades_not_fails(db_session, tmp_path, monkeypatch):

    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch, error=RuntimeError("pdflatex exploded"))

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["pdf_ready"] is False
    assert body["application_id"] is not None  # tailor still committed
    # Failure detail is NOT in the response (frozen contract has no render_error
    # field); application_render.render_resume persists application.render_error
    # for the UI. (Not asserted here: the render call is mocked.)


def test_quick_tailor_compare_failure_degrades_to_none(db_session, tmp_path, monkeypatch):
    # A compare failure post-commit must not 500 the whole endpoint (fix B6):
    # compare degrades to None and the render still runs, mirroring render
    # degradation.
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("scorer exploded")

    monkeypatch.setattr("app.services.quick_tailor.ats_score.compare", boom)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["compare"] is None
    assert body["pdf_ready"] is True
    assert body["application_id"] is not None


def test_quick_tailor_unknown_job_404_unknown_base_422(db_session, tmp_path, monkeypatch):
    from uuid import uuid4

    job = _seed_job(db_session)
    _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        bad_job = client.post(
            f"/api/jobs/{uuid4()}/quick-tailor", json={"base_resume": "data_scientist"}
        )
        bad_base = client.post(
            f"/api/jobs/{job.id}/quick-tailor", json={"base_resume": "no_such_slug"}
        )
    finally:
        app.dependency_overrides.clear()

    # Unknown job_id is a 404 (fix B8); an unknown base on a real job is a 422.
    assert bad_job.status_code == 404
    assert bad_job.json()["detail"] == "Job not found"
    assert bad_base.status_code == 422


def test_quick_tailor_proceeds_when_open_session_has_only_system_autos(
    db_session, tmp_path, monkeypatch
):
    """Auto-resolutions seeded at session creation (payload.provenance) are not
    user work: an untouched-but-enriched session must not block quick tailor."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)
    _seed_open_session(
        db_session,
        job,
        slug,
        [
            {"gap_id": "skill:x", "action": "skip"},
            {
                "gap_id": "skill:kafka",
                "action": "enable_entry",
                "payload": {
                    "section": "projects",
                    "index": 0,
                    "provenance": {"source": "library_auto"},
                },
            },
        ],
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_policy_keywords_into_skills_off_gates_profile_auto():
    """A kb_profile auto is still an add_keyword into skills, so the user's
    keywords_into_skills switch governs it; evidence-backed enable/port autos
    are not gated by that switch."""
    gap = _gap("skill:airflow", jd_skill="Airflow")
    gap["library_candidates"] = [{"kind": "profile", "match_form": "exact", "auto": True}]
    gaps = _gaps_json(missing_skills=[gap])

    profile = {**quick_tailor.DEFAULTS, "keywords_into_skills": False}
    resolutions, applied = quick_tailor.plan_resolutions(gaps, profile)
    assert resolutions[0]["action"] == "skip"
    assert applied == []

    resolutions, _ = quick_tailor.plan_resolutions(gaps, quick_tailor.DEFAULTS)
    assert resolutions[0]["action"] == "add_keyword"
    assert resolutions[0]["payload"]["provenance"] == {"source": "kb_profile"}


def test_quick_tailor_preserves_prestored_cannot_confirm(db_session, tmp_path, monkeypatch):
    """A standing "I can't confirm this" must survive the profile plan's
    replace=True save — the plan must not resurrect the disconfirmed keyword.
    Pins the suppression-preservation guard in run_for_job."""
    from app.models.career_kb import KBEntity, KBPoint

    ent = KBEntity(kind="extra", title="Unconfirmed claims", status="archived",
                   origin="gap_elicitation")
    db_session.add(ent)
    db_session.flush()
    db_session.add(KBPoint(
        entity_id=ent.id, text="Docker", state="retired",
        origin="gap_elicitation", provenance="user_cannot_confirm",
    ))
    db_session.commit()

    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_llm(monkeypatch)
    _mock_render(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _quick_tailor(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = db_session.get(TailoringSession, UUID(response.json()["session_id"]))
    docker_actions = [
        item["action"]
        for item in row.resolutions_json
        if "docker" in json.dumps(item).lower()
    ]
    assert "cannot_confirm" in docker_actions, docker_actions
    assert "add_keyword" not in docker_actions, docker_actions
