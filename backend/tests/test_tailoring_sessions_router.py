import json
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from app.models.health_gate_waiver import HealthGateWaiver
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.models.resume_lint_report import ResumeLintReport
from app.models.tailoring_session import TailoringSession
from app.schemas.resume_edit import ResumeEditRequest
from app.services import (
    gap_enrichment,
    kb_resolver,
    llm,
    prompt_assembly,
    prompts,
    quick_tailor,
    resume_versions,
    tailoring_session,
)
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed_job(db_session, extracted_json=SAMPLE_JD):
    job = Job(raw_text="jd", raw_text_hash="router-ts-hash", extracted_json=extracted_json)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _seed_base(
    db_session, tmp_path, monkeypatch, slug="data_scientist", resume_json=None
):
    resume_json = resume_json or SAMPLE_RESUME
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(resume_json))
    db_session.add(BaseResume(slug=slug, data_json=resume_json))
    db_session.commit()
    return slug


def _mock_prompt_files(monkeypatch):
    # get_prompt without a session opens its own SessionLocal against the app DB;
    # serve the on-disk defaults directly instead.
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key, session=None: (prompts.PROMPT_DIR / f"{key}.txt").read_text(encoding="utf-8"),
    )


def _mock_enrichment(monkeypatch, response=None, error=None):
    _mock_prompt_files(monkeypatch)
    calls = []

    def fake_call_openai(**kwargs):
        calls.append(kwargs)
        if error is not None:
            raise error
        return response if response is not None else {"enrichments": []}

    monkeypatch.setattr(gap_enrichment.llm, "call_openai", fake_call_openai)
    return calls


def _create(client, job, slug, enrich=None):
    payload = {"job_id": str(job.id), "base_resume": slug}
    if enrich is not None:
        payload["enrich"] = enrich
    return client.post("/api/tailoring-sessions", json=payload)


def _create_clean(client, job, slug):
    """Create a session and clear the system-planned auto-resolutions it
    pre-stores (the SAMPLE fixtures produce a wording_auto for AWS), so tests
    that pin PATCH/tailor semantics start from an empty resolution list."""
    created = _create(client, job, slug, enrich=False).json()
    cleared = client.patch(
        f"/api/tailoring-sessions/{created['id']}",
        json={"resolutions": [], "replace": True},
    )
    assert cleared.status_code == 200
    created["resolutions_json"] = []
    return created


def _all_gaps(gaps_json):
    return [gap for category in gaps_json["categories"] for gap in category["gaps"]]


def test_create_session_with_enrichment(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_enrichment(
        monkeypatch,
        response={
            "enrichments": [
                {
                    "gap_id": "skill:salesforce",
                    "suggested_wording": None,
                    "project_candidates": [],
                    "elicitation_question": "Have you used Salesforce?",
                }
            ]
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["job_id"] == str(job.id)
    assert body["base_resume"] == slug
    # Self-nomination may pre-store auto-resolutions from library evidence
    # (SAMPLE_RESUME's disabled entries); anything stored at creation must be
    # system-planned, i.e. carry provenance — never hand-shaped user work.
    assert all(
        (item.get("payload") or {}).get("provenance")
        for item in body["resolutions_json"]
    )
    assert body["gaps_json"]["categories"]

    assert len(calls) == 1
    assert calls[0]["response_format"] == "json"

    by_id = {gap["gap_id"]: gap for gap in _all_gaps(body["gaps_json"])}
    assert by_id["skill:salesforce"]["enrichment"]["elicitation_question"] == (
        "Have you used Salesforce?"
    )

    # the base score row was persisted and linked
    base_row = db_session.get(AtsScore, body["base_ats_score_id"])
    assert base_row is not None
    assert base_row.phase == "base"
    assert base_row.target_id == slug
    assert float(base_row.composite) == body["gaps_json"]["base_composite"]


def test_create_session_stamps_candidates_and_prestores_autos(
    db_session, tmp_path, monkeypatch
):
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    resume["projects"].insert(
        0,
        {
            "name": "Ingestion Pipeline",
            "enabled": False,
            "bullets": ["Streamed events with Apache Kafka into S3"],
            "tech": ["Kafka", "Spark"],
        },
    )
    jd = json.loads(json.dumps(SAMPLE_JD))
    jd["skills"].append(
        {
            "skill_name": "Kafka",
            "skill_category": "Streaming",
            "requirement_level": "required",
        }
    )
    job = _seed_job(db_session, extracted_json=jd)
    slug = _seed_base(
        db_session,
        tmp_path,
        monkeypatch,
        slug="kb_auto_create",
        resume_json=resume,
    )
    _mock_enrichment(
        monkeypatch,
        response={
            "enrichments": [
                {
                    "gap_id": "skill:kafka",
                    "library_candidates": [
                        {"kind": "disabled", "section": "projects", "index": 0}
                    ],
                }
            ]
        },
    )

    created = tailoring_session.create_session(
        job.id, slug, enrich=True, session=db_session
    )

    missing = next(
        category
        for category in created.gaps_json["categories"]
        if category["key"] == "missing_skills"
    )
    kafka_gap = next(gap for gap in missing["gaps"] if gap["jd_skill"].lower() == "kafka")
    assert kafka_gap["library_candidates"][0]["auto"] is True
    autos = [item for item in created.resolutions_json if item["action"] != "skip"]
    assert autos
    assert autos[0]["payload"]["provenance"]["source"] == "library_auto"
    # The private llm_library_proposals stash (enrich_gaps -> stamp_library_
    # candidates handoff) must never survive into the persisted, publicly-
    # served gaps_json — sweep every gap in every category, not just kafka's.
    for category in created.gaps_json["categories"]:
        for gap in category["gaps"]:
            assert "llm_library_proposals" not in gap, gap


def test_create_session_enrich_false_skips_llm(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_enrichment(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls == []
    assert all(gap["enrichment"] is None for gap in _all_gaps(response.json()["gaps_json"]))
    # Auto planning is deterministic, and candidate gating now runs
    # UNCONDITIONALLY (stamp_library_candidates, hoisted out from under the LLM
    # call): enrich=False still pre-stores the mirror_wording exact-token add
    # (SAMPLE fixtures: AWS) AND the library auto that self-nomination finds
    # with no LLM involved at all (SAMPLE_RESUME's disabled HiddenCo entry
    # literally says "Salesforce admin work.").
    stored = response.json()["resolutions_json"]
    assert stored
    sources = {item["payload"]["provenance"]["source"] for item in stored}
    assert sources == {"wording_auto", "library_auto"}


def test_create_session_enrichment_failure_still_creates(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_enrichment(monkeypatch, error=RuntimeError("llm down"))

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert all(gap["enrichment"] is None for gap in _all_gaps(body["gaps_json"]))
    # Enrichment failure degrades to unenriched gaps, but the deterministic
    # auto planning is unaffected: stamp_library_candidates runs outside the
    # enrichment try-block, so both the wording auto (AWS) AND the library
    # auto that self-nomination finds without any LLM (SAMPLE_RESUME's
    # disabled HiddenCo entry says "Salesforce admin work.") still land.
    sources = {
        item["payload"]["provenance"]["source"] for item in body["resolutions_json"]
    }
    assert sources == {"wording_auto", "library_auto"}
    assert body["resolutions_json"]


def test_create_session_kb_snapshot_failure_degrades_to_manual_flow(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_enrichment(monkeypatch)

    snapshot_calls = []

    def fail_snapshot(session):
        snapshot_calls.append(session)
        raise RuntimeError("KB unavailable")

    monkeypatch.setattr(kb_resolver, "load_kb_snapshot", fail_snapshot)

    created = tailoring_session.create_session(
        job.id, slug, enrich=True, session=db_session
    )

    assert snapshot_calls == [db_session]
    assert created.status == "open"
    # No KB snapshot → no library/KB autos; the deterministic wording autos
    # don't need the KB and still plan.
    assert all(
        item["payload"]["provenance"]["source"] == "wording_auto"
        for item in created.resolutions_json
    )
    assert all("library_candidates" not in gap for gap in _all_gaps(created.gaps_json))


def test_create_session_scores_once_and_persists_that_run(db_session, tmp_path, monkeypatch):
    """The engine runs exactly once per session create: the persisted "before"
    row and the frozen gaps come from the SAME result (audit C18 — this used to
    be two identical runs plus a divergence warning)."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    real_score_resume = tailoring_session.score_resume
    calls = []

    def counting(resume_json, jd_json, as_of=None):
        calls.append(1)
        return real_score_resume(resume_json, jd_json, as_of=as_of)

    monkeypatch.setattr(tailoring_session, "score_resume", counting)
    # Count the persistence path's engine entry point too: score_target must
    # reuse the passed-in result, not run the engine a second time.
    from app.services import ats_score as ats_score_service

    monkeypatch.setattr(ats_score_service, "score_resume", counting)

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)

    assert created.status == "open"
    assert len(calls) == 1
    base_row = db_session.get(AtsScore, created.base_ats_score_id)
    assert created.gaps_json["base_composite"] == float(base_row.composite)


def test_create_session_422_for_job_without_skills(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session, extracted_json={"title": "X", "skills": []})
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "skills" in response.json()["detail"]


def test_create_session_422_for_unknown_job(db_session, tmp_path, monkeypatch):
    _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/tailoring-sessions",
            json={"job_id": str(uuid4()), "base_resume": "data_scientist", "enrich": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Job not found" in response.json()["detail"]


def test_create_session_422_for_unknown_slug(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/tailoring-sessions",
            json={"job_id": str(job.id), "base_resume": "no_such_slug", "enrich": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# --- base-resume health gate (Task 10) ---------------------------------------
#
# A failing FATAL, unwaived health gate on the base resume BLOCKS tailoring (409);
# a health score < 55 WARNS but proceeds; waived gates never block; no report at
# all proceeds silently.


def _seed_health_report(
    db_session, slug, report_json, *, resume_version_number=None
):
    db_session.add(
        ResumeLintReport(
            resume_kind="base",
            resume_key=slug,
            resume_version_number=resume_version_number,
            report_json=report_json,
        )
    )
    db_session.commit()


def test_create_session_blocked_by_failing_fatal_gate(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    version = resume_versions.record_version(
        db_session, "base", slug, SAMPLE_RESUME, source="create"
    )
    db_session.commit()
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 70,
            "grade": "C",
            "gates": [
                {
                    "id": "S1",
                    "tier": "fatal",
                    "status": "fail",
                    "label": "Parse fidelity",
                    "detail": "The template's PDF drops text under a strict extractor.",
                }
            ],
        },
        resume_version_number=version.version_number,
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "S1" in response.json()["detail"]
    # nothing was created — the block fires before the session row is inserted
    assert db_session.scalars(select(TailoringSession)).first() is None


def test_create_session_ignores_stale_failing_fatal_report_with_warning(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    first = resume_versions.record_version(
        db_session, "base", slug, SAMPLE_RESUME, source="create"
    )
    db_session.commit()
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 40,
            "grade": "D",
            "gates": [
                {
                    "id": "S1",
                    "tier": "fatal",
                    "status": "fail",
                    "label": "Parse fidelity",
                }
            ],
        },
        resume_version_number=first.version_number,
    )
    changed = deepcopy(SAMPLE_RESUME)
    changed["summary"] = "Edited after the health report."
    base = db_session.get(BaseResume, slug)
    base.data_json = changed
    (tmp_path / f"{slug}.json").write_text(json.dumps(changed))
    second = resume_versions.record_version(
        db_session, "base", slug, changed, source="form_edit"
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["health_warning"] == (
        f"Health report is stale (ran against v{first.version_number}; "
        f"resume is now v{second.version_number}) — re-analyze."
    )


def test_create_session_waived_fatal_gate_not_blocked(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    # same fatal gate, but WAIVED — a waived gate never blocks.
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 70,
            "grade": "C",
            "gates": [
                {
                    "id": "S1",
                    "tier": "fatal",
                    "status": "waived",
                    "label": "Parse fidelity",
                    "detail": "Waived by the user.",
                }
            ],
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    # score 70 is above the warn floor, so no warning either
    assert body["health_warning"] is None


def test_create_session_unblocked_by_a_waiver_row_the_stored_report_predates(
    db_session, tmp_path, monkeypatch
):
    """The waiver TABLE is the authority, not the snapshot beside it.

    `POST /gates/{id}/waive` writes a `HealthGateWaiver` row and nothing else —
    the stored report keeps saying "fail" until a health check RUNS again, which
    is where waivers are folded into gate statuses. The gate read here used the
    stored statuses alone, so the documented escape hatch did not open: MCP's
    `waive_health_gate` says it clears this 409, and an agent that waived and
    retried got the same 409 forever. The web path only worked because its
    waive button re-runs the check afterwards.
    """
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 70,
            "grade": "C",
            "gates": [
                {
                    "id": "S1",
                    "tier": "fatal",
                    "status": "fail",
                    "label": "Parse fidelity",
                    "detail": "The template's PDF drops text under a strict extractor.",
                }
            ],
        },
    )
    db_session.add(
        HealthGateWaiver(
            resume_kind="base", resume_key=slug, gate_id="S1", reason="Known extractor quirk"
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_create_session_stays_blocked_when_the_waiver_names_another_gate(
    db_session, tmp_path, monkeypatch
):
    """A waiver is per-gate: waiving S1 must not release S2."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 70,
            "grade": "C",
            "gates": [
                {"id": "S2", "tier": "fatal", "status": "fail", "label": "Contact block"},
            ],
        },
    )
    db_session.add(
        HealthGateWaiver(
            resume_kind="base", resume_key=slug, gate_id="S1", reason="A different gate"
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "S2" in response.json()["detail"]


def test_create_session_waiver_does_not_travel_to_another_base_resume(
    db_session, tmp_path, monkeypatch
):
    """A waiver belongs to the resume it was filed against.

    Reading waivers by gate id alone (or by kind alone) would let one waived
    resume release the gate for every other one — the whole suite stayed green
    under exactly that mutation until this test existed.
    """
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 70,
            "grade": "C",
            "gates": [
                {"id": "S1", "tier": "fatal", "status": "fail", "label": "Parse fidelity"},
            ],
        },
    )
    db_session.add(
        HealthGateWaiver(
            resume_kind="base",
            resume_key="some_other_resume",
            gate_id="S1",
            reason="Waived over there, not here",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "S1" in response.json()["detail"]


def test_create_session_warns_when_health_under_55(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _seed_health_report(db_session, slug, {"score": 40, "grade": "D", "gates": []})

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["health_warning"] is not None
    assert "40" in body["health_warning"]


def test_create_session_healthy_report_no_warning(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _seed_health_report(
        db_session,
        slug,
        {
            "score": 90,
            "grade": "A",
            "gates": [
                {"id": "S1", "tier": "fatal", "status": "pass", "label": "Parse fidelity",
                 "detail": "ok"},
                {"id": "S2", "tier": "fatal", "status": "pass", "label": "Contact reachable",
                 "detail": "ok"},
            ],
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["health_warning"] is None


def test_create_session_no_health_report_proceeds_silently(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    # no ResumeLintReport seeded — health is opt-in

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = _create(TestClient(app), job, slug, enrich=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["health_warning"] is None


def test_get_session_and_404(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        found = client.get(f"/api/tailoring-sessions/{created['id']}")
        missing = client.get(f"/api/tailoring-sessions/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert found.status_code == 200
    assert found.json()["id"] == created["id"]
    assert found.json()["gaps_json"] == created["gaps_json"]
    assert missing.status_code == 404


def test_list_sessions_newest_first(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    other_job = Job(raw_text="jd2", raw_text_hash="router-ts-hash-2", extracted_json=SAMPLE_JD)
    db_session.add(other_job)
    db_session.commit()
    db_session.refresh(other_job)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        first = _create(client, job, slug, enrich=False).json()
        second = _create(client, job, slug, enrich=False).json()
        _create(client, other_job, slug, enrich=False)
        listing = client.get(f"/api/tailoring-sessions?job_id={job.id}")
    finally:
        app.dependency_overrides.clear()

    assert listing.status_code == 200
    body = listing.json()
    assert [item["id"] for item in body] == [second["id"], first["id"]]


def test_patch_merges_resolutions_by_gap_id(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        session_id = created["id"]
        gap_ids = [gap["gap_id"] for gap in _all_gaps(created["gaps_json"])]
        assert "skill:salesforce" in gap_ids
        other_gap_id = next(gap_id for gap_id in gap_ids if gap_id != "skill:salesforce")

        first = client.patch(
            f"/api/tailoring-sessions/{session_id}",
            json={
                "resolutions": [
                    {
                        "gap_id": "skill:salesforce",
                        "action": "user_input",
                        "payload": {"answer": "Owned Salesforce data pipelines at DataCo."},
                    }
                ]
            },
        )
        second = client.patch(
            f"/api/tailoring-sessions/{session_id}",
            json={
                "resolutions": [
                    {"gap_id": "skill:salesforce", "action": "skip"},
                    {"gap_id": other_gap_id, "action": "skip"},
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["resolutions_json"] == [
        {
            "gap_id": "skill:salesforce",
            "action": "user_input",
            "payload": {"answer": "Owned Salesforce data pipelines at DataCo."},
        }
    ]

    assert second.status_code == 200
    merged = second.json()["resolutions_json"]
    assert len(merged) == 2
    by_gap = {item["gap_id"]: item for item in merged}
    assert by_gap["skill:salesforce"]["action"] == "skip"  # second batch wins
    assert by_gap[other_gap_id]["action"] == "skip"


def test_patch_duplicate_gap_id_in_one_batch_last_wins(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        response = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={
                "resolutions": [
                    {
                        "gap_id": "skill:salesforce",
                        "action": "user_input",
                        "payload": {"answer": "first"},
                    },
                    {"gap_id": "skill:salesforce", "action": "skip"},
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["resolutions_json"] == [
        {"gap_id": "skill:salesforce", "action": "skip", "payload": {}}
    ]


def test_patch_empty_batch_is_a_noop(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        first = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
        empty = client.patch(
            f"/api/tailoring-sessions/{created['id']}", json={"resolutions": []}
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert empty.status_code == 200
    assert empty.json()["resolutions_json"] == first.json()["resolutions_json"]


def test_patch_replace_true_removes_omitted_entries(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        session_id = created["id"]
        gap_ids = [gap["gap_id"] for gap in _all_gaps(created["gaps_json"])]
        other_gap_id = next(gap_id for gap_id in gap_ids if gap_id != "skill:salesforce")

        first = client.patch(
            f"/api/tailoring-sessions/{session_id}",
            json={
                "resolutions": [
                    {"gap_id": "skill:salesforce", "action": "skip"},
                    {"gap_id": other_gap_id, "action": "skip"},
                ]
            },
        )
        # replace=True with only one entry (sent twice — dedup, last wins):
        # the omitted gap_id is deleted, not merged around.
        replaced = client.patch(
            f"/api/tailoring-sessions/{session_id}",
            json={
                "resolutions": [
                    {
                        "gap_id": "skill:salesforce",
                        "action": "user_input",
                        "payload": {"text": "first"},
                    },
                    {
                        "gap_id": "skill:salesforce",
                        "action": "user_input",
                        "payload": {"text": "Owned Salesforce pipelines at DataCo."},
                    },
                ],
                "replace": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert len(first.json()["resolutions_json"]) == 2
    assert replaced.status_code == 200
    assert replaced.json()["resolutions_json"] == [
        {
            "gap_id": "skill:salesforce",
            "action": "user_input",
            "payload": {"text": "Owned Salesforce pipelines at DataCo."},
        }
    ]


def test_patch_replace_true_empty_list_clears_all(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        first = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
        cleared = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [], "replace": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert len(first.json()["resolutions_json"]) == 1
    assert cleared.status_code == 200
    assert cleared.json()["resolutions_json"] == []


def test_patch_replace_rejected_batch_saves_nothing(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        first = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
        rejected = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={
                "resolutions": [{"gap_id": "skill:nonexistent", "action": "skip"}],
                "replace": True,
            },
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert rejected.status_code == 400
    assert "Unknown gap_id" in rejected.json()["detail"]
    # the rejected replace batch neither replaced nor cleared anything
    assert after.json()["resolutions_json"] == first.json()["resolutions_json"]


def test_patch_unknown_gap_id_returns_400(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        response = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:nonexistent", "action": "skip"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Unknown gap_id" in response.json()["detail"]


def test_patch_illegal_action_returns_400(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        # a mirror_wording gap only allows add_keyword/skip; attach_project
        # (offered only for missing skills) is not allowed here.
        response = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:aws", "action": "attach_project"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_patch_unverified_add_keyword_must_target_skills(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        sid = created["id"]
        # missing skill (salesforce, fix_hint=="absent"): add_keyword into experience
        # is blocked server-side regardless of the caller (honesty invariant).
        rejected = client.patch(
            f"/api/tailoring-sessions/{sid}",
            json={
                "resolutions": [
                    {
                        "gap_id": "skill:salesforce",
                        "action": "add_keyword",
                        "payload": {
                            "placement_target": {"section": "experience", "index_or_category": 0},
                            "wording": "Salesforce",
                        },
                    }
                ]
            },
        )
        # the same add_keyword into skills is accepted and saved.
        accepted = client.patch(
            f"/api/tailoring-sessions/{sid}",
            json={
                "resolutions": [
                    {
                        "gap_id": "skill:salesforce",
                        "action": "add_keyword",
                        "payload": {
                            "placement_target": {
                                "section": "skills",
                                "index_or_category": "Additional Skills",
                            },
                            "wording": "Salesforce",
                        },
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 400
    assert "skills section" in rejected.json()["detail"]

    assert accepted.status_code == 200
    saved = accepted.json()["resolutions_json"]
    assert len(saved) == 1
    assert saved[0]["gap_id"] == "skill:salesforce"
    assert saved[0]["payload"]["placement_target"]["section"] == "skills"


# --- add_keyword placement_target / attach_project project_name validation (D1) ---
#
# SAMPLE_RESUME shape the cases below rely on: skills categories are
# {Languages, Cloud, Tools}; experience has 2 ENABLED entries (HiddenCo is
# disabled) so valid experience indices are 0 and 1; the only enabled project is
# "RAG Search". skill:tableau is stale (add_keyword allowed, NOT absent, so the
# honesty invariant does not pre-empt the range check); skill:salesforce is a
# missing skill, so attach_project is an allowed action for it.


def _patch(client, session_id, resolutions):
    return client.patch(
        f"/api/tailoring-sessions/{session_id}", json={"resolutions": resolutions}
    )


def _open_library_session(db_session, tmp_path, monkeypatch):
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    resume["projects"] = [
        {
            "name": "Ingestion Pipeline",
            "enabled": False,
            "bullets": ["Streamed events with Kafka"],
            "tech": "Kafka",
        },
        {
            "name": "Churn Model",
            "enabled": True,
            "bullets": ["Trained XGBoost model"],
            "tech": "",
        },
    ]
    job = _seed_job(db_session)
    slug = _seed_base(
        db_session,
        tmp_path,
        monkeypatch,
        slug="library_validation",
        resume_json=resume,
    )
    gaps = [
        {
            "gap_id": gap_id,
            "kind": "skill",
            "jd_skill": skill,
            "diagnostic": {"fix_hint": "absent"},
            "actions": [
                "add_keyword",
                "user_input",
                "attach_project",
                "skip",
                "enable_entry",
                "port_kb_point",
            ],
        }
        for gap_id, skill in (("skill:kafka", "Kafka"), ("skill:mlflow", "MLflow"))
    ]
    tailoring = TailoringSession(
        job_id=job.id,
        base_resume=slug,
        status="open",
        gaps_json={"categories": [{"key": "missing_skills", "gaps": gaps}]},
        resolutions_json=[],
    )
    db_session.add(tailoring)
    db_session.commit()
    db_session.refresh(tailoring)
    return tailoring


def _seed_kb_points(db_session):
    entity = KBEntity(
        kind="project",
        title="Churn Model",
        status="completed",
        detail_json={"tech": ["MLflow"]},
    )
    db_session.add(entity)
    db_session.flush()
    approved = KBPoint(
        entity_id=entity.id,
        text="Tracked runs in MLflow",
        state="approved",
        origin="manual",
    )
    draft = KBPoint(
        entity_id=entity.id,
        text="Deployed with Docker",
        state="draft",
        origin="manual",
    )
    db_session.add_all([approved, draft])
    db_session.flush()
    return approved, draft


def test_enable_entry_validates_section_and_index(db_session, tmp_path, monkeypatch):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    ok = [
        {
            "gap_id": "skill:kafka",
            "action": "enable_entry",
            "payload": {"section": "projects", "index": 0},
        }
    ]

    tailoring_session.save_resolutions(tailoring.id, ok, session=db_session)

    for bad in (
        {"section": "skills", "index": 0},
        {"section": "projects", "index": 99},
        {"section": "projects", "index": 1},
        {"section": "projects", "index": True},
    ):
        with pytest.raises(ValueError):
            tailoring_session.save_resolutions(
                tailoring.id,
                [{"gap_id": "skill:kafka", "action": "enable_entry", "payload": bad}],
                session=db_session,
            )


def test_port_kb_point_requires_approved_point_and_valid_target(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, draft = _seed_kb_points(db_session)
    good = {
        "gap_id": "skill:mlflow",
        "action": "port_kb_point",
        "payload": {
            "kb_point_id": str(approved.id),
            "placement_target": {"section": "projects", "index_or_category": 1},
            "wording": approved.text,
        },
    }

    tailoring_session.save_resolutions(tailoring.id, [good], session=db_session)

    bad_payloads = (
        {**good["payload"], "kb_point_id": str(draft.id)},
        {**good["payload"], "kb_point_id": str(uuid4())},
        {**good["payload"], "wording": "   "},
        {
            **good["payload"],
            "placement_target": {"section": "skills", "index_or_category": "Data"},
        },
        {
            **good["payload"],
            "placement_target": {"section": "projects", "index_or_category": 99},
        },
    )
    for payload in bad_payloads:
        with pytest.raises(ValueError):
            tailoring_session.save_resolutions(
                tailoring.id,
                [{**good, "payload": payload}],
                session=db_session,
            )


def test_port_may_target_entry_enabled_in_same_batch(db_session, tmp_path, monkeypatch):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    batch = [
        {
            "gap_id": "skill:kafka",
            "action": "enable_entry",
            "payload": {"section": "projects", "index": 0},
        },
        {
            "gap_id": "skill:mlflow",
            "action": "port_kb_point",
            "payload": {
                "kb_point_id": str(approved.id),
                "placement_target": {"section": "projects", "index_or_category": 0},
                "wording": approved.text,
            },
        },
    ]

    saved = tailoring_session.save_resolutions(tailoring.id, batch, session=db_session)

    assert [item["action"] for item in saved.resolutions_json] == [
        "enable_entry",
        "port_kb_point",
    ]


def test_port_may_target_entry_enabled_by_stored_resolution(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    tailoring_session.save_resolutions(
        tailoring.id,
        [
            {
                "gap_id": "skill:kafka",
                "action": "enable_entry",
                "payload": {"section": "projects", "index": 0},
            }
        ],
        session=db_session,
    )

    saved = tailoring_session.save_resolutions(
        tailoring.id,
        [
            {
                "gap_id": "skill:mlflow",
                "action": "port_kb_point",
                "payload": {
                    "kb_point_id": str(approved.id),
                    "placement_target": {"section": "projects", "index_or_category": 0},
                    "wording": approved.text,
                },
            }
        ],
        session=db_session,
    )

    assert len(saved.resolutions_json) == 2


def test_replace_port_cannot_rely_on_omitted_stored_enable(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    tailoring_session.save_resolutions(
        tailoring.id,
        [
            {
                "gap_id": "skill:kafka",
                "action": "enable_entry",
                "payload": {"section": "projects", "index": 0},
            }
        ],
        session=db_session,
    )

    with pytest.raises(ValueError):
        tailoring_session.save_resolutions(
            tailoring.id,
            [
                {
                    "gap_id": "skill:mlflow",
                    "action": "port_kb_point",
                    "payload": {
                        "kb_point_id": str(approved.id),
                        "placement_target": {
                            "section": "projects",
                            "index_or_category": 0,
                        },
                        "wording": approved.text,
                    },
                }
            ],
            replace=True,
            session=db_session,
        )


def _save_library_preops(tailoring, approved_point, db_session):
    return tailoring_session.save_resolutions(
        tailoring.id,
        [
            {
                "gap_id": "skill:kafka",
                "action": "enable_entry",
                "payload": {
                    "section": "projects",
                    "index": 0,
                    "name": "Ingestion Pipeline",
                    "provenance": {"source": "library_auto"},
                },
            },
            {
                "gap_id": "skill:mlflow",
                "action": "port_kb_point",
                "payload": {
                    "kb_point_id": str(approved_point.id),
                    "kb_entity_id": str(approved_point.entity_id),
                    "placement_target": {
                        "section": "projects",
                        "index_or_category": 1,
                    },
                    "wording": approved_point.text,
                    "provenance": {
                        "source": "kb_auto",
                        "kb_point_id": str(approved_point.id),
                        "kb_entity_id": str(approved_point.entity_id),
                    },
                },
            },
        ],
        session=db_session,
    )


def test_tailor_applies_enable_and_port_before_llm(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    _save_library_preops(tailoring, approved, db_session)
    llm_calls = []
    monkeypatch.setattr(
        tailoring_session.llm,
        "call_openai",
        lambda **kwargs: llm_calls.append(kwargs) or {"ops": []},
    )

    tailored = tailoring_session.tailor(tailoring.id, session=db_session)

    application = db_session.get(Application, tailored.application_id)
    assert application.customized_json["projects"][0]["enabled"] is True
    assert approved.text in application.customized_json["projects"][1]["bullets"]
    assert llm_calls == []


def test_port_writes_kb_port_log(db_session, tmp_path, monkeypatch):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    _save_library_preops(tailoring, approved, db_session)
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )

    tailored = tailoring_session.tailor(tailoring.id, session=db_session)

    row = db_session.scalar(select(KBPortLog).where(KBPortLog.point_id == approved.id))
    assert row is not None
    assert row.resume_kind == "application"
    assert row.resume_key == str(tailored.application_id)
    assert row.section == "projects"
    assert row.ported_text == approved.text
    # Model contract (career_kb.py): NULL = verbatim port, ported_text doubles
    # as the snapshot; source_text is set only when the wording was adapted.
    assert row.source_text is None


def test_gap_tailor_prompt_lists_already_applied(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: (
            "JUDGMENT RULES" if key == "tailoring_skill" else
            "Resume=${resume_json}\n${already_applied_section}"
        ),
    )

    prompt = prompt_assembly.build_gap_tailor_prompt(
        {},
        {},
        resolutions=[],
        skipped_gaps=[],
        already_applied=[
            "Enabled project 'Ingestion Pipeline'",
            "Ported KB point into projects entry 1",
        ],
    )

    assert "Already applied — do not redo or undo" in prompt
    assert "Enabled project 'Ingestion Pipeline'" in prompt
    assert "Ported KB point into projects entry 1" in prompt


def _open_keyword_add_session(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(
        db_session, tmp_path, monkeypatch, slug="keyword_survival"
    )
    created = tailoring_session.create_session(
        job.id, slug, enrich=False, session=db_session
    )
    tailoring_session.save_resolutions(
        created.id,
        [
            {
                "gap_id": "skill:snowflake",
                "action": "add_keyword",
                "payload": {
                    "placement_target": {
                        "section": "skills",
                        "index_or_category": "Additional Skills",
                    },
                    "wording": "Snowflake",
                },
            }
        ],
        session=db_session,
    )
    return created


def test_dropped_keyword_triggers_retry_then_fallback(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_keyword_add_session(db_session, tmp_path, monkeypatch)
    _mock_prompt_files(monkeypatch)
    calls = []

    def drop_keyword(**kwargs):
        calls.append(kwargs)
        return {"ops": []}

    monkeypatch.setattr(tailoring_session.llm, "call_openai", drop_keyword)

    tailored = tailoring_session.tailor(tailoring.id, session=db_session)

    application = db_session.get(Application, tailored.application_id)
    assert "snowflake" in json.dumps(application.customized_json).lower()
    assert len(calls) == 2
    assert "Snowflake" in calls[1]["prompt"]


def test_surviving_keywords_skip_retry(db_session, tmp_path, monkeypatch):
    tailoring = _open_keyword_add_session(db_session, tmp_path, monkeypatch)
    _mock_prompt_files(monkeypatch)
    calls = []

    def keep_keyword(**kwargs):
        calls.append(kwargs)
        return {
            "ops": [
                {
                    "kind": "add_skill_item",
                    "category": "Additional Skills",
                    "item": "Snowflake",
                }
            ]
        }

    monkeypatch.setattr(tailoring_session.llm, "call_openai", keep_keyword)

    tailoring_session.tailor(tailoring.id, session=db_session)

    assert len(calls) == 1


def test_patch_add_keyword_experience_index_out_of_range_returns_400(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        # index 2 is the DISABLED HiddenCo entry -> not an enabled placement target
        response = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:tableau",
                    "action": "add_keyword",
                    "payload": {
                        "placement_target": {"section": "experience", "index_or_category": 2},
                        "wording": "Tableau",
                    },
                }
            ],
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "not an enabled experience entry" in response.json()["detail"]
    # whole-batch-before-save: nothing persisted
    assert after.json()["resolutions_json"] == []


def test_patch_add_keyword_skills_unknown_category_returns_400(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        response = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:tableau",
                    "action": "add_keyword",
                    "payload": {
                        "placement_target": {
                            "section": "skills",
                            "index_or_category": "Nonexistent Category",
                        },
                        "wording": "Tableau",
                    },
                }
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "skills category" in response.json()["detail"]


def test_patch_add_keyword_skills_additional_skills_accepted(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        response = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:tableau",
                    "action": "add_keyword",
                    "payload": {
                        "placement_target": {
                            "section": "skills",
                            "index_or_category": "Additional Skills",
                        },
                        "wording": "Tableau",
                    },
                }
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = response.json()["resolutions_json"]
    assert len(saved) == 1
    assert saved[0]["payload"]["placement_target"]["index_or_category"] == "Additional Skills"


def test_patch_add_keyword_experience_valid_index_accepted(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        # index 1 (OldCo) is a valid ENABLED experience entry
        response = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:tableau",
                    "action": "add_keyword",
                    "payload": {
                        "placement_target": {"section": "experience", "index_or_category": 1},
                        "wording": "Tableau",
                    },
                }
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = response.json()["resolutions_json"]
    assert len(saved) == 1
    assert saved[0]["payload"]["placement_target"] == {
        "section": "experience",
        "index_or_category": 1,
    }


def test_patch_attach_project_unknown_project_returns_400(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        response = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:salesforce",
                    "action": "attach_project",
                    "payload": {"project_name": "Ghost Project"},
                }
            ],
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "enabled project" in response.json()["detail"]
    assert after.json()["resolutions_json"] == []


def test_patch_attach_project_valid_name_accepted(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        # case-insensitive match against the enabled project "RAG Search"
        response = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:salesforce",
                    "action": "attach_project",
                    "payload": {"project_name": "rag search"},
                }
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = response.json()["resolutions_json"]
    assert len(saved) == 1
    assert saved[0]["action"] == "attach_project"
    assert saved[0]["payload"]["project_name"] == "rag search"


def test_patch_rejected_batch_saves_nothing(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        response = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={
                "resolutions": [
                    {"gap_id": "skill:salesforce", "action": "skip"},
                    {"gap_id": "skill:nonexistent", "action": "skip"},
                ]
            },
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert after.json()["resolutions_json"] == []


def test_patch_non_open_session_returns_409(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        row = db_session.get(TailoringSession, created["id"])
        row.status = "tailored"
        db_session.commit()
        response = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "not open" in response.json()["detail"]


def test_patch_unknown_session_returns_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/tailoring-sessions/{uuid4()}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# --- POST /{id}/tailor -------------------------------------------------------

# Deterministic ops against SAMPLE_RESUME: add Salesforce to the Languages skills
# group and weave it into the current DataCo bullet (absent -> dual placement).
TAILOR_OPS = {
    "ops": [
        {
            "kind": "replace_skills_group",
            "category": "Languages",
            "items": ["Python", "SQL", "Salesforce"],
        },
        {
            "kind": "replace_bullet",
            "section": "experience",
            "index": 0,
            "bullet_index": 0,
            "value": (
                "Shipped Python forecasting models on AWS integrating Salesforce "
                "CRM data, reducing costs 20%."
            ),
        },
    ]
}

SALESFORCE_RESOLUTION = {
    "gap_id": "skill:salesforce",
    "action": "user_input",
    "payload": {"text": "Owned Salesforce CRM data pipelines at DataCo since 2023."},
}


def _mock_tailor_llm(monkeypatch, response=None, error=None):
    """Mock the ops-generating LLM call (sessions under test are created enrich=False)."""
    _mock_prompt_files(monkeypatch)
    calls = []

    def fake_call_openai(**kwargs):
        calls.append(kwargs)
        if error is not None:
            raise error
        return response if response is not None else TAILOR_OPS

    monkeypatch.setattr(tailoring_session.llm, "call_openai", fake_call_openai)
    return calls


def _open_session(client, job, slug, resolutions=None):
    created = _create_clean(client, job, slug)
    if resolutions is not None:
        patched = client.patch(
            f"/api/tailoring-sessions/{created['id']}", json={"resolutions": resolutions}
        )
        assert patched.status_code == 200
    return created


def _tailor(client, session_id, body=None):
    return client.post(f"/api/tailoring-sessions/{session_id}/tailor", json=body)


def test_tailor_request_apply_profile_defaults_false():
    from app.schemas.tailoring_session import TailorRequest

    assert TailorRequest().apply_profile is False
    assert TailorRequest(apply_profile=True).apply_profile is True


def test_apply_profile_fills_only_unresolved_gaps(db_session, tmp_path, monkeypatch):
    """Quick tailor fills holes: a hand resolution and a pre-stored auto both
    survive verbatim, and every remaining gap gets a decision."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        # The SAMPLE fixtures pre-store a wording_auto for AWS at creation.
        auto = next(
            item for item in created["resolutions_json"]
            if item["payload"].get("provenance", {}).get("source") == "wording_auto"
        )
        # One hand-made resolution the profile must not touch.
        hand = {
            "gap_id": "skill:salesforce",
            "action": "user_input",
            "payload": {"text": "Owned Salesforce CRM pipelines at DataCo since 2023."},
        }
        assert _patch(client, created["id"], [hand]).status_code == 200

        response = client.post(
            f"/api/tailoring-sessions/{created['id']}/tailor",
            json={"apply_profile": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = response.json()["session"]["resolutions_json"]
    by_id = {item["gap_id"]: item for item in saved}

    # The auto and the hand resolution are untouched.
    assert by_id[auto["gap_id"]] == auto
    assert by_id["skill:salesforce"] == hand
    # Every gap now carries a decision.
    gap_ids = {gap["gap_id"] for gap in _all_gaps(created["gaps_json"])}
    assert gap_ids <= set(by_id)


def test_apply_profile_does_not_reopen_a_stored_skip(db_session, tmp_path, monkeypatch):
    """A stored skip is a decision already made; the planner must not re-plan it
    into an add. This is why the filter is membership, not truthiness."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        skipped = {"gap_id": "skill:salesforce", "action": "skip", "payload": {}}
        keep = {
            "gap_id": "skill:docker",
            "action": "add_keyword",
            "payload": {
                "placement_target": {
                    "section": "skills",
                    "index_or_category": "Additional Skills",
                },
                "wording": "Docker",
            },
        }
        assert _patch(client, created["id"], [skipped, keep]).status_code == 200

        response = client.post(
            f"/api/tailoring-sessions/{created['id']}/tailor",
            json={"apply_profile": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = response.json()["session"]["resolutions_json"]
    by_id = {item["gap_id"]: item for item in saved}
    assert by_id["skill:salesforce"]["action"] == "skip"


def test_apply_profile_absent_skill_still_lands_in_skills(db_session, tmp_path, monkeypatch):
    """The honesty invariant holds through this path: the fill goes through
    save_resolutions, which re-enforces skills-only for absent skills."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        response = client.post(
            f"/api/tailoring-sessions/{created['id']}/tailor",
            json={"apply_profile": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = response.json()["session"]["resolutions_json"]
    for item in saved:
        if item["action"] == "add_keyword":
            assert item["payload"]["placement_target"]["section"] == "skills"


def test_apply_profile_uses_standing_instruction_only_as_fallback(
    db_session, tmp_path, monkeypatch
):
    """The standing instruction reaches tailor() when the session has no note of
    its own, and NEVER overrides one that does — the gap page's textarea wins."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)
    monkeypatch.setattr(
        "app.routers.tailoring_sessions.quick_tailor.get_profile",
        lambda session=None: {**quick_tailor.DEFAULTS, "instruction": "Keep it to one page."},
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        # (a) no session note -> the standing instruction is used
        created = _create(client, job, slug, enrich=False).json()
        client.post(
            f"/api/tailoring-sessions/{created['id']}/tailor",
            json={"apply_profile": True},
        )
        assert any("Keep it to one page." in str(c) for c in calls)

        # (b) a session note wins over the standing instruction
        calls.clear()
        second = _create(client, job, slug, enrich=False).json()
        client.patch(
            f"/api/tailoring-sessions/{second['id']}",
            json={"resolutions": [], "user_prompt": "Lead with the fintech project."},
        )
        client.post(
            f"/api/tailoring-sessions/{second['id']}/tailor",
            json={"apply_profile": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert any("Lead with the fintech project." in str(c) for c in calls)
    assert not any("Keep it to one page." in str(c) for c in calls)


def test_tailor_without_apply_profile_leaves_resolutions_alone(
    db_session, tmp_path, monkeypatch
):
    """The flag is opt-in: the normal Tailor button path is untouched."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, [SALESFORCE_RESOLUTION])
        before = client.get(f"/api/tailoring-sessions/{created['id']}").json()[
            "resolutions_json"
        ]
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["session"]["resolutions_json"] == before


def test_apply_profile_with_nothing_actionable_400s(db_session, tmp_path, monkeypatch):
    """Profile off + nothing addressed + no self-nominable evidence: the fill
    plans only skips, so tailor() raises its existing guard. The UI maps this
    to 'use base resume as-is'.

    Strips SAMPLE_RESUME's disabled-HiddenCo Salesforce mention: stamp_library_
    candidates' self-nomination now runs UNCONDITIONALLY (Task: hoist the KB
    pass out from under the LLM call), and an enable_entry/port_kb_point auto
    bypasses the profile toggles entirely (see _plan_gap) — so with that
    mention left in, this scenario would no longer be "nothing actionable".
    """
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    hidden_co = next(e for e in resume["experience"] if e["company"] == "HiddenCo")
    hidden_co["bullets"] = ["Handled internal admin tooling."]
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch, resume_json=resume)
    _mock_tailor_llm(monkeypatch)
    monkeypatch.setattr(
        "app.routers.tailoring_sessions.quick_tailor.get_profile",
        lambda session=None: {
            **quick_tailor.DEFAULTS,
            "keywords_into_skills": False,
            "mirror_wording": False,
            "summary_rename": False,
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        response = client.post(
            f"/api/tailoring-sessions/{created['id']}/tailor",
            json={"apply_profile": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "No actionable resolutions to tailor"


# --- POST /{id}/apply-profile ------------------------------------------------
# The MCP quick path's fill-only step: same fill_checkpoint_session the /tailor
# route's apply_profile flag uses, but stopping before tailor() so the agent can
# read what was planned and author its own ops (SYSTEM.md §11 item 13).


def test_apply_profile_fills_resolutions_without_tailoring(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    # Proves the route stops at the fill: a stray call into tailor() (LLM ops,
    # application, render) fails the test outright rather than merely going
    # unasserted.
    monkeypatch.setattr(
        tailoring_session,
        "tailor",
        lambda *a, **k: pytest.fail("apply-profile must not tailor"),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        # _create_clean wipes the pre-stored autos so resolutions_json starts at
        # [] — a no-op fill would leave it empty, so the non-empty assertion
        # below is a real delta, not an artifact of pre-seeded state.
        created = _create_clean(client, job, slug)
        assert created["resolutions_json"] == []

        response = client.post(f"/api/tailoring-sessions/{created['id']}/apply-profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    # NOT `assert body["resolutions_json"]`: plan_resolutions emits an entry for
    # EVERY gap, undecided ones as "skip", so a non-empty list only proves the
    # fill ran — it stays non-empty when the profile plans nothing actionable, a
    # state test_apply_profile_with_nothing_actionable_400s proves is reachable.
    # Assert on the actionable subset, which is what the endpoint exists to add.
    planned = [r for r in body["resolutions_json"] if r["action"] != "skip"]
    assert planned, "profile planned nothing actionable"


def test_apply_profile_maps_plain_value_errors_to_400(db_session, tmp_path, monkeypatch):
    """A plain ValueError out of the fill is a bad-session 400, not a 500.

    save_resolutions raises bare ValueErrors for an unknown gap_id, a
    disallowed action, or a base resume that will not load (reachable on a
    legacy row with no base_content_hash, which staleness treats as fresh).
    patch_resolutions already maps them; an agent caller reading a 500 would
    conclude the server is broken rather than that its session is unusable.
    """
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    monkeypatch.setattr(
        quick_tailor,
        "fill_checkpoint_session",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("base resume not found: ghost")),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        response = client.post(f"/api/tailoring-sessions/{created['id']}/apply-profile")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "ghost" in response.json()["detail"]


def test_apply_profile_409s_on_a_closed_session_and_404s_on_a_missing_one(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        closed = client.post(f"/api/tailoring-sessions/{created['id']}/close")
        assert closed.status_code == 200

        on_closed = client.post(f"/api/tailoring-sessions/{created['id']}/apply-profile")
        # Same call shape against an id that was never created: must land on the
        # 404 branch, not fall through to the same 409 the closed session hits.
        on_missing = client.post(f"/api/tailoring-sessions/{uuid4()}/apply-profile")
    finally:
        app.dependency_overrides.clear()

    assert on_closed.status_code == 409
    assert "not open" in on_closed.json()["detail"]
    assert on_missing.status_code == 404


def test_tailor_happy_path(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()

    # session closed and linked
    assert body["session"]["status"] == "tailored"
    assert body["session"]["application_id"] is not None
    assert body["session"]["resolutions_json"] == [SALESFORCE_RESOLUTION]

    # application persisted with the ops applied
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert application is not None
    assert application.job_id == job.id
    assert application.base_resume == slug
    languages = next(
        g for g in application.customized_json["skills"] if g["category"] == "Languages"
    )
    assert "Salesforce" in languages["items"]
    assert "Salesforce" in application.customized_json["experience"][0]["bullets"][0]

    # tailored score row persisted and linked to the application
    tailored_rows = list(
        db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored"))
    )
    assert len(tailored_rows) == 1
    assert tailored_rows[0].application_id == application.id

    # embedded compare: positive composite delta and the Salesforce flip
    compare = body["compare"]
    assert compare["application_id"] == body["session"]["application_id"]
    assert compare["delta"]["composite"] > 0
    salesforce_diff = next(
        d for d in compare["skill_diff"] if d["jd_skill"] == "Salesforce"
    )
    assert salesforce_diff["before"]["matched"] is False
    assert salesforce_diff["after"]["matched"] is True

    # one ops LLM call, JSON mode
    assert len(calls) == 1
    assert calls[0]["response_format"] == "json"
    assert calls[0]["model"] == settings.smart_model


def test_tailor_unverified_skill_add_keyword_lands_in_skills(db_session, tmp_path, monkeypatch):
    """Missing-skill add_keyword (skills placement) -> add_skill_item op -> the skill
    lands in customized_json.skills, in a category the base resume did not have."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(
        monkeypatch,
        response={
            "ops": [
                {"kind": "add_skill_item", "category": "Additional Skills", "item": "Salesforce"}
            ]
        },
    )

    unverified_resolution = {
        "gap_id": "skill:salesforce",
        "action": "add_keyword",
        "payload": {
            "placement_target": {"section": "skills", "index_or_category": "Additional Skills"},
            "wording": "Salesforce",
        },
    }

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        # A2 makes add_keyword a legal action for a missing skill, so save_resolutions
        # accepts this batch (the create->resolve->tailor path works end to end).
        created = _open_session(client, job, slug, resolutions=[unverified_resolution])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["status"] == "tailored"

    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert application is not None
    # the skill was appended into a newly-created skills category (add_skill_item)
    assert any(
        g["category"] == "Additional Skills" and "Salesforce" in g["items"]
        for g in application.customized_json["skills"]
    )
    # skills-list only: experience is untouched (no fabricated bullet for the unproven skill)
    assert application.customized_json["experience"] == SAMPLE_RESUME["experience"]


def test_tailor_user_prompt_reaches_prompt_and_application(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"], body={"user_prompt": "Keep bullets terse."})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Keep bullets terse." in calls[0]["prompt"]
    application = db_session.get(
        Application, UUID(response.json()["session"]["application_id"])
    )
    assert application.user_prompt == "Keep bullets terse."


def test_tailor_prompt_excludes_skipped_gaps_from_mandate(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    tableau_wording = "Tableau dashboards consumed by 40+ execs"

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        gaps_by_id = {gap["gap_id"]: gap for gap in _all_gaps(created["gaps_json"])}
        # fixture pair guarantees: Docker missing (skippable), Tableau stale (add_keyword)
        assert "add_keyword" in gaps_by_id["skill:tableau"]["actions"]
        patched = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={
                "resolutions": [
                    SALESFORCE_RESOLUTION,
                    {
                        "gap_id": "skill:tableau",
                        "action": "add_keyword",
                        "payload": {
                            "placement_target": {
                                "section": "skills",
                                "index_or_category": "Tools",
                            },
                            "wording": tableau_wording,
                        },
                    },
                    {"gap_id": "skill:docker", "action": "skip"},
                ]
            },
        )
        assert patched.status_code == 200
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    prompt = calls[0]["prompt"]

    resolutions_start = prompt.index("Resolutions (")
    skipped_start = prompt.index("Skipped gaps")
    assert resolutions_start < skipped_start
    resolutions_section = prompt[resolutions_start:skipped_start]
    skipped_section = prompt[skipped_start:]

    assert "Salesforce" in resolutions_section
    # resolution payloads reach the LLM verbatim: the user's answer text and the
    # add_keyword placement/wording travel with their resolutions
    assert SALESFORCE_RESOLUTION["payload"]["text"] in resolutions_section
    assert tableau_wording in resolutions_section
    assert '"index_or_category": "Tools"' in resolutions_section
    # the skipped skill is out of the mandate: named only in the do-not-touch list
    assert "Docker" not in resolutions_section
    assert "Docker" in skipped_section.split("Edit op JSON schemas")[0]
    # the diagnostic evidence travels with the actionable resolution
    assert '"diagnostic"' in resolutions_section


def _mock_session_render(monkeypatch, error=None):
    """Stub the render the tailor endpoint now runs. Returns the call log so a
    test can prove it fired for the right application rather than trusting a
    green run — the endpoint degrades on failure, so an un-called render and a
    successful one are otherwise indistinguishable from the response."""
    calls = []

    def fake_render(db, application_id, *, template_id=None):
        calls.append(application_id)
        if error is not None:
            raise error
        return ("/tmp/x.tex", "/tmp/x.pdf")

    monkeypatch.setattr(
        "app.routers.tailoring_sessions.application_render.render_resume", fake_render
    )
    return calls


def test_tailor_renders_the_pdf(db_session, tmp_path, monkeypatch):
    """The in-app tailor renders, like the one-shot path already did. Without
    it a tailored draft reached the studio with no PDF, so seeing it meant
    pressing Save on an unedited draft purely to trigger a compile."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)
    renders = _mock_session_render(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert body["pdf_ready"] is True
    # Fired exactly once, for the application the tailor just produced.
    assert renders == [UUID(body["session"]["application_id"])]


def test_tailor_render_failure_only_degrades(db_session, tmp_path, monkeypatch):
    """Same policy as the one-shot path: the tailor is already committed, so a
    render failure reports pdf_ready=False rather than failing the request."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)
    _mock_session_render(monkeypatch, error=RuntimeError("typst exploded"))

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["status"] == "tailored"
    assert body["pdf_ready"] is False
    # The tailor still landed.
    assert db_session.get(Application, UUID(body["session"]["application_id"])) is not None


def test_tailor_renders_even_when_compare_fails(db_session, tmp_path, monkeypatch):
    """A compare failure must not also cost the PDF. The compare branch used to
    return early, which would have skipped the render entirely — this is the
    test that pins why it no longer does."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)
    renders = _mock_session_render(monkeypatch)

    def boom(*args, **kwargs):
        raise ValueError("scores were produced by different engine/config versions")

    monkeypatch.setattr(tailoring_session.ats_score, "compare", boom)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert body["compare"] is None
    assert "tailoring succeeded" in body["compare_error"]
    # …and the PDF was still produced.
    assert body["pdf_ready"] is True
    assert renders == [UUID(body["session"]["application_id"])]


def test_tailor_compare_failure_still_reports_success(db_session, tmp_path, monkeypatch):
    """A post-commit compare failure must not mask the successful tailor: the
    session is already committed 'tailored' with an application, so the response
    is 200 with compare=None and an explanatory compare_error."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    def boom(*args, **kwargs):
        raise ValueError("scores were produced by different engine/config versions")

    monkeypatch.setattr(tailoring_session.ats_score, "compare", boom)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["status"] == "tailored"
    assert body["session"]["application_id"] is not None
    assert body["compare"] is None
    assert "tailoring succeeded" in body["compare_error"]
    assert "different engine/config versions" in body["compare_error"]
    # the pipeline really persisted
    assert db_session.get(Application, UUID(body["session"]["application_id"])) is not None


def test_tailor_invalid_ops_from_llm_leaves_nothing(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch, response={"ops": [{"kind": "garbage_op", "value": 1}]})

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid edit ops" in response.json()["detail"]

    db_session.rollback()
    row = db_session.get(TailoringSession, created["id"])
    assert row.status == "open"
    assert row.application_id is None
    assert row.resolutions_json == [SALESFORCE_RESOLUTION]
    assert db_session.scalars(select(Application)).first() is None
    assert (
        db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored")).first()
        is None
    )


def test_tailor_out_of_range_ops_leave_nothing(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(
        monkeypatch,
        response={
            "ops": [
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 99,
                    "bullet_index": 0,
                    "value": "x",
                }
            ]
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid edit ops" in response.json()["detail"]
    db_session.rollback()
    assert db_session.get(TailoringSession, created["id"]).status == "open"
    assert db_session.scalars(select(Application)).first() is None


def test_tailor_provider_failure_returns_502(db_session, tmp_path, monkeypatch):
    """A provider outage/quota failure is a gateway error, not an opaque 500.

    llm.py normalizes every provider failure to LLMProviderError precisely so the
    HTTP layer can name it; without the mapping the UI showed only "Request
    failed: 500" and the actual cause (e.g. an exhausted API credit balance) was
    visible nowhere but a container traceback.
    """
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(
        monkeypatch,
        error=llm.LLMProviderError(
            "OpenAI API request failed: Error code: 429 - insufficient_quota"
        ),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "insufficient_quota" in response.json()["detail"]
    db_session.rollback()
    row = db_session.get(TailoringSession, created["id"])
    assert row.status == "open"
    assert row.application_id is None
    assert db_session.scalars(select(Application)).first() is None


def test_tailor_non_provider_runtime_error_is_not_a_502(db_session, tmp_path, monkeypatch):
    """The 502 handler is scoped to LLMProviderError, not to RuntimeError.

    pdf_render and typst_compiler raise plain RuntimeErrors for local render
    failures; sweeping those into 502 would blame the model provider for our own
    bugs. A non-provider RuntimeError must stay an unhandled server error.
    """
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch, error=RuntimeError("not a provider failure"))

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        with pytest.raises(RuntimeError, match="not a provider failure"):
            _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()


def test_tailor_llm_failure_leaves_session_open(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch, error=RuntimeError("llm down"))

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    tailoring_session.save_resolutions(
        created.id, [SALESFORCE_RESOLUTION], replace=True, session=db_session
    )

    with pytest.raises(RuntimeError, match="llm down"):
        tailoring_session.tailor(created.id, session=db_session)

    db_session.rollback()
    row = db_session.get(TailoringSession, created.id)
    assert row.status == "open"
    assert row.application_id is None
    assert row.resolutions_json == [SALESFORCE_RESOLUTION]
    assert db_session.scalars(select(Application)).first() is None


def test_tailor_scoring_failure_persists_nothing(db_session, tmp_path, monkeypatch):
    """Atomicity: score_target's internal commit is the transaction boundary.

    The application flush and session mutations happen before score_target; if
    scoring raises before its commit, nothing at all is persisted.
    """
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    tailoring_session.save_resolutions(
        created.id, [SALESFORCE_RESOLUTION], replace=True, session=db_session
    )

    def boom(*args, **kwargs):
        raise RuntimeError("scoring exploded")

    monkeypatch.setattr(tailoring_session.ats_score, "score_target", boom)

    with pytest.raises(RuntimeError, match="scoring exploded"):
        tailoring_session.tailor(created.id, session=db_session)

    db_session.rollback()
    row = db_session.get(TailoringSession, created.id)
    assert row.status == "open"
    assert row.application_id is None
    assert row.resolutions_json == [SALESFORCE_RESOLUTION]
    assert db_session.scalars(select(Application)).first() is None
    assert (
        db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored")).first()
        is None
    )


def test_tailor_engine_failure_inside_score_target_persists_nothing(
    db_session, tmp_path, monkeypatch
):
    """Same atomicity, but through the REAL score_target: its only commit comes
    after scoring succeeds, so an engine failure inside it persists nothing."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    tailoring_session.save_resolutions(
        created.id, [SALESFORCE_RESOLUTION], session=db_session
    )

    def boom(*args, **kwargs):
        raise RuntimeError("engine exploded")

    # patched after create_session (which scores the base via the same engine)
    monkeypatch.setattr(tailoring_session.ats_score, "score_resume", boom)

    with pytest.raises(RuntimeError, match="engine exploded"):
        tailoring_session.tailor(created.id, session=db_session)

    db_session.rollback()
    row = db_session.get(TailoringSession, created.id)
    assert row.status == "open"
    assert row.application_id is None
    assert db_session.scalars(select(Application)).first() is None
    assert (
        db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored")).first()
        is None
    )


def test_tailor_second_call_returns_409(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        first = _tailor(client, created["id"])
        second = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 409
    assert "not open" in second.json()["detail"]
    # no second application was created
    assert len(list(db_session.scalars(select(Application)))) == 1


def test_tailor_without_actionable_resolutions_returns_400(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug)  # no resolutions at all
        empty = _tailor(client, created["id"])
        patched = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
        assert patched.status_code == 200
        all_skips = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert empty.status_code == 400
    assert all_skips.status_code == 400
    assert "No actionable resolutions" in all_skips.json()["detail"]
    assert calls == []  # never reached the LLM
    assert db_session.get(TailoringSession, created["id"]).status == "open"


def test_tailor_unknown_session_returns_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/tailoring-sessions/{uuid4()}/tailor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# --- per-session user_prompt persistence (D2) --------------------------------


def test_read_exposes_user_prompt_default_none(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
    finally:
        app.dependency_overrides.clear()

    # the field is present in TailoringSessionRead so the UI can prefill; it
    # defaults to None on a fresh session
    assert "user_prompt" in created
    assert created["user_prompt"] is None


def test_patch_persists_user_prompt(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        patched = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [], "user_prompt": "focus on Airflow"},
        )
        fetched = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert patched.status_code == 200
    assert patched.json()["user_prompt"] == "focus on Airflow"
    # survives a re-read (persisted on the session row, not just echoed back)
    assert fetched.json()["user_prompt"] == "focus on Airflow"


def test_patch_empty_user_prompt_clears_it(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [], "user_prompt": "focus on Airflow"},
        )
        cleared = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [], "user_prompt": ""},
        )
    finally:
        app.dependency_overrides.clear()

    assert cleared.status_code == 200
    # an empty string clears the stored prompt back to None
    assert cleared.json()["user_prompt"] is None


def test_patch_omitting_user_prompt_leaves_it_unchanged(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [], "user_prompt": "focus on Airflow"},
        )
        # a resolutions-only PATCH (no user_prompt key) must not wipe it
        unchanged = client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={"resolutions": [{"gap_id": "skill:salesforce", "action": "skip"}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert unchanged.status_code == 200
    assert unchanged.json()["user_prompt"] == "focus on Airflow"


def test_tailor_falls_back_to_stored_user_prompt(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={
                "resolutions": [SALESFORCE_RESOLUTION],
                "user_prompt": "Prioritize Airflow orchestration.",
            },
        )
        # no user_prompt in the tailor request -> the stored session value is used
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Prioritize Airflow orchestration." in calls[0]["prompt"]
    application = db_session.get(
        Application, UUID(response.json()["session"]["application_id"])
    )
    assert application.user_prompt == "Prioritize Airflow orchestration."


def test_tailor_request_user_prompt_overrides_stored(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create(client, job, slug, enrich=False).json()
        client.patch(
            f"/api/tailoring-sessions/{created['id']}",
            json={
                "resolutions": [SALESFORCE_RESOLUTION],
                "user_prompt": "Stored fallback prompt.",
            },
        )
        response = _tailor(
            client, created["id"], body={"user_prompt": "Explicit request wins."}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # the explicit request value wins; the stored fallback is not used
    assert "Explicit request wins." in calls[0]["prompt"]
    assert "Stored fallback prompt." not in calls[0]["prompt"]
    application = db_session.get(
        Application, UUID(response.json()["session"]["application_id"])
    )
    assert application.user_prompt == "Explicit request wins."


# --- re-tailor reuses the job's existing application (D3) --------------------

# Distinctive second-pass ops so the re-tailor's customized_json is provably the
# new one (a fresh DataCo bullet carrying a marker string).
SECOND_TAILOR_OPS = {
    "ops": [
        {
            "kind": "replace_bullet",
            "section": "experience",
            "index": 0,
            "bullet_index": 0,
            "value": "SECOND-PASS MARKER: re-tailored DataCo bullet.",
        }
    ]
}


def _applications_for(db_session, job, slug):
    return list(
        db_session.scalars(
            select(Application).where(
                Application.job_id == job.id, Application.base_resume == slug
            )
        )
    )


def test_tailor_reuses_existing_application_preserving_state(
    db_session, tmp_path, monkeypatch
):
    """A second tailoring pass for the same job+base updates the existing
    application in place: same row, refreshed customized_json, but status, notes,
    Q&A, and other tracking fields survive and stale artifacts are unlinked."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)  # first pass: default TAILOR_OPS

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        first_session = _open_session(
            client, job, slug, resolutions=[SALESFORCE_RESOLUTION]
        )
        first = _tailor(client, first_session["id"])
        assert first.status_code == 200
        application_id = UUID(first.json()["session"]["application_id"])

        # Simulate real post-tailor state on the application: applied status, a
        # note, a Q&A entry, and rendered artifacts on disk.
        application = db_session.get(Application, application_id)
        application.status = "applied"
        application.notes = "Reached out to referrer."
        art_dir = tmp_path / "artifacts"
        art_dir.mkdir()
        pdf_path = art_dir / "resume.pdf"
        tex_path = art_dir / "resume.tex"
        pdf_path.write_text("%PDF fake")
        tex_path.write_text("fake tex")
        application.pdf_path = str(pdf_path)
        application.tex_path = str(tex_path)
        db_session.add(
            QAEntry(
                application_id=application_id,
                kind="behavioral",
                prompt="Tell me about a time...",
                answer="At DataCo I owned the pipeline.",
            )
        )
        db_session.commit()

        # Second pass over the SAME job + base, with distinctive ops so we can
        # prove customized_json is the new one.
        _mock_tailor_llm(monkeypatch, response=SECOND_TAILOR_OPS)
        second_session = _open_session(
            client, job, slug, resolutions=[SALESFORCE_RESOLUTION]
        )
        second = _tailor(client, second_session["id"])
    finally:
        app.dependency_overrides.clear()

    assert second.status_code == 200
    # (a) the SAME application is reused — no orphaned duplicate row
    reused_id = UUID(second.json()["session"]["application_id"])
    assert reused_id == application_id
    assert len(_applications_for(db_session, job, slug)) == 1

    db_session.refresh(application)
    # (b) customized_json reflects the SECOND tailoring pass
    assert (
        "SECOND-PASS MARKER"
        in application.customized_json["experience"][0]["bullets"][0]
    )
    # (c) status, note, and Q&A preserved across the re-tailor
    assert application.status == "applied"
    assert application.notes == "Reached out to referrer."
    qa = list(
        db_session.scalars(
            select(QAEntry).where(QAEntry.application_id == application_id)
        )
    )
    assert len(qa) == 1
    assert qa[0].answer == "At DataCo I owned the pipeline."
    # (d) stale rendered artifacts were unlinked (paths nulled + files removed)
    assert application.pdf_path is None
    assert application.tex_path is None
    assert not pdf_path.exists()
    assert not tex_path.exists()


def test_tailor_first_time_inserts_single_application(db_session, tmp_path, monkeypatch):
    """A job+base with no prior application still inserts exactly one row."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    apps = _applications_for(db_session, job, slug)
    assert len(apps) == 1
    assert str(apps[0].id) == response.json()["session"]["application_id"]


# --- caller-supplied ops bypass the backend LLM (D4) -------------------------
#
# When Claude (via MCP) supplies its own typed edit ops, tailor() must skip its
# own LLM call AND the resolution-bundle/actionable guard, apply the caller's ops
# directly, and run the same application-reuse + auto-score tail as the LLM path.


def _ops_from(dicts):
    """Build validated ResumeEdit objects the way the schema layer does."""
    return ResumeEditRequest.model_validate({"ops": dicts}).ops


def _forbid_llm(monkeypatch):
    """Fail loudly if the ops-generating LLM is called when ops are supplied."""

    def fake_call_openai(**kwargs):
        raise AssertionError("llm.call_openai must not be called when ops are supplied")

    monkeypatch.setattr(tailoring_session.llm, "call_openai", fake_call_openai)


def test_tailor_with_caller_ops_skips_llm(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)

    # No resolutions at all: the LLM path would raise "No actionable resolutions",
    # so a success here proves the ops path skips the resolution-bundle/actionable
    # guard as well as the LLM call (which is wired to raise if reached).
    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)

    ops = _ops_from(
        [{"kind": "add_skill_item", "category": "Languages", "item": "Salesforce"}]
    )
    result = tailoring_session.tailor(created.id, ops=ops, session=db_session)

    assert result.status == "tailored"
    assert result.application_id is not None

    application = db_session.get(Application, result.application_id)
    languages = next(
        g for g in application.customized_json["skills"] if g["category"] == "Languages"
    )
    assert "Salesforce" in languages["items"]

    # the shared tail still auto-scored the reused/created application
    tailored = list(
        db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored"))
    )
    assert len(tailored) == 1
    assert tailored[0].application_id == application.id


def test_tailor_with_caller_ops_places_resolution_in_extra_section(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    resume_json = json.loads(json.dumps(SAMPLE_RESUME))
    resume_json["extra_sections"] = [
        {
            "key": "volunteer",
            "title": "Volunteer Work",
            "type": "entries",
            "enabled": True,
            "entries": [
                {
                    "heading": "STEM Mentor",
                    "subheading": "Community Lab",
                    "location": None,
                    "date": "2025",
                    "link": None,
                    "enabled": True,
                    "bullets": ["Coached students on data projects."],
                }
            ],
        }
    ]
    slug = _seed_base(
        db_session,
        tmp_path,
        monkeypatch,
        slug="extra_target",
        resume_json=resume_json,
    )
    _forbid_llm(monkeypatch)
    created = tailoring_session.create_session(
        job.id, slug, enrich=False, session=db_session
    )
    tailoring_session.save_resolutions(
        created.id,
        [
            {
                "gap_id": "skill:tableau",
                "action": "add_keyword",
                "payload": {
                    "placement_target": {
                        "section": "extra",
                        "section_key": "volunteer",
                        "index_or_category": 0,
                    },
                    "wording": "Tableau",
                },
            }
        ],
        session=db_session,
    )

    replacement = json.loads(json.dumps(resume_json["extra_sections"][0]))
    replacement["entries"][0]["bullets"].append(
        "Taught Tableau dashboard design using de-identified student datasets."
    )
    ops = _ops_from(
        [
            {
                "kind": "replace_extra_section",
                "section_key": "volunteer",
                "value": replacement,
            }
        ]
    )
    result = tailoring_session.tailor(created.id, ops=ops, session=db_session)

    application = db_session.get(Application, result.application_id)
    section = application.customized_json["extra_sections"][0]
    assert section["key"] == "volunteer"
    assert section["entries"][0]["bullets"][-1].startswith("Taught Tableau")


def test_tailor_with_caller_ops_still_requires_open_session(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    row = db_session.get(TailoringSession, created.id)
    row.status = "tailored"
    db_session.commit()

    ops = _ops_from(
        [{"kind": "add_skill_item", "category": "Languages", "item": "Salesforce"}]
    )
    # open-session guard is preserved for the ops path (router maps this to 409)
    with pytest.raises(tailoring_session.SessionNotOpenError):
        tailoring_session.tailor(created.id, ops=ops, session=db_session)


def test_tailor_with_invalid_caller_ops_maps_to_clean_error(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)

    # schema-valid op that fails apply_edits (experience index out of range):
    # the caller-supplied ops go through the SAME error mapping as LLM ops.
    ops = _ops_from(
        [
            {
                "kind": "replace_bullet",
                "section": "experience",
                "index": 99,
                "bullet_index": 0,
                "value": "x",
            }
        ]
    )
    with pytest.raises(ValueError, match="invalid edit ops"):
        tailoring_session.tailor(created.id, ops=ops, session=db_session)

    db_session.rollback()
    row = db_session.get(TailoringSession, created.id)
    assert row.status == "open"
    assert row.application_id is None
    assert db_session.scalars(select(Application)).first() is None
    assert (
        db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored")).first()
        is None
    )


# --- HTTP tailor endpoint forwards caller ops (D5) ---------------------------
#
# The POST /{id}/tailor endpoint accepts an optional `ops` array and forwards it
# to tailor(..., ops=...), which bypasses the backend LLM entirely.


def _forbid_llm(monkeypatch):
    """Fail loudly if the ops-generating LLM is reached on the HTTP ops path."""

    def fake_call_openai(**kwargs):
        raise AssertionError("llm.call_openai must not be called when ops are supplied")

    monkeypatch.setattr(tailoring_session.llm, "call_openai", fake_call_openai)


def test_tailor_http_with_caller_ops_bypasses_llm(db_session, tmp_path, monkeypatch):
    """POST tailor with an `ops` array applies them directly, skipping the LLM and
    the actionable-resolutions guard (the session carries no resolutions at all)."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug)  # no resolutions
        response = _tailor(
            client,
            created["id"],
            body={
                "ops": [
                    {
                        "kind": "add_skill_item",
                        "category": "Languages",
                        "item": "Salesforce",
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["status"] == "tailored"
    assert body["session"]["application_id"] is not None

    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    languages = next(
        g for g in application.customized_json["skills"] if g["category"] == "Languages"
    )
    assert "Salesforce" in languages["items"]
    # the shared tail auto-scored the application
    tailored = list(db_session.scalars(select(AtsScore).where(AtsScore.phase == "tailored")))
    assert len(tailored) == 1
    assert tailored[0].application_id == application.id


def test_tailor_http_invalid_caller_ops_returns_400(db_session, tmp_path, monkeypatch):
    """Schema-valid but un-appliable ops (experience index out of range) map to a
    clean 400 through the same error mapping the LLM path uses; nothing persists."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug)
        response = _tailor(
            client,
            created["id"],
            body={
                "ops": [
                    {
                        "kind": "replace_bullet",
                        "section": "experience",
                        "index": 99,
                        "bullet_index": 0,
                        "value": "x",
                    }
                ]
            },
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "invalid edit ops" in response.json()["detail"]
    assert after.json()["status"] == "open"
    assert db_session.scalars(select(Application)).first() is None


def test_tailor_http_without_ops_uses_llm(db_session, tmp_path, monkeypatch):
    """The no-ops HTTP path is unchanged: it still builds the prompt and calls the
    LLM to produce the edit ops."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    calls = _mock_tailor_llm(monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _open_session(client, job, slug, resolutions=[SALESFORCE_RESOLUTION])
        response = _tailor(client, created["id"])  # no ops in the body
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["session"]["status"] == "tailored"
    assert len(calls) == 1  # the LLM ops path ran


def test_validate_placement_target_accepts_enabled_index_beyond_count():
    """Regression (user-reported): buildPlacementTargets emits FULL-ARRAY indices;
    a disabled project earlier in the array must not make a valid later project's
    index (e.g. 3) fail save-time validation."""
    import pytest

    from app.services import placement_targets
    from app.services.tailoring_session import _validate_placement_target

    resume = {
        "skills": [{"category": "Cloud", "items": ["AWS"]}],
        "experience": [{"enabled": True}],
        "projects": [
            {"enabled": True},
            {"enabled": False},
            {"enabled": False},
            {"enabled": True},
        ],
    }
    targets = placement_targets.build_targets(resume)
    assert targets["projects_indices"] == {0, 3}
    # enabled project at full-array index 3 must NOT raise
    _validate_placement_target(
        {"section": "projects", "index_or_category": 3}, targets, "skill:x"
    )
    # a disabled project's index must raise
    with pytest.raises(ValueError):
        _validate_placement_target(
            {"section": "projects", "index_or_category": 1}, targets, "skill:x"
        )


# --- extra-section placement validation: user_input + honesty + staleness ----
#
# (findings F#4, F#7, F#5). SAMPLE_RESUME + one enabled custom "volunteer"
# section; skill:salesforce is engine-ABSENT (fix_hint == "absent"), skill:tableau
# is matched (NOT absent, so the honesty guard does not pre-empt target checks).


def _resume_with_volunteer(*, section_enabled=True):
    resume_json = json.loads(json.dumps(SAMPLE_RESUME))
    resume_json["extra_sections"] = [
        {
            "key": "volunteer",
            "title": "Volunteer Work",
            "type": "entries",
            "enabled": section_enabled,
            "entries": [
                {"heading": "Mentor", "enabled": True, "bullets": ["Coached students."]}
            ],
        }
    ]
    return resume_json


def test_patch_user_input_valid_extra_placement_target_accepted(
    db_session, tmp_path, monkeypatch
):
    # F#4: user_input resolutions can carry a placement_target (phase-2 chips
    # include custom sections). A VALID extras target is accepted, and the
    # add_keyword-only honesty guard does NOT apply — even an engine-absent skill's
    # user_input (user-authored evidence) may point at a custom section.
    job = _seed_job(db_session)
    slug = _seed_base(
        db_session, tmp_path, monkeypatch, slug="ui_extra", resume_json=_resume_with_volunteer()
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        accepted = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:salesforce",
                    "action": "user_input",
                    "payload": {
                        "placement_target": {
                            "section": "extra",
                            "section_key": "volunteer",
                            "index_or_category": 0,
                        },
                        "text": "Led a Salesforce-based volunteer CRM rollout.",
                    },
                }
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert accepted.status_code == 200
    saved = accepted.json()["resolutions_json"]
    assert len(saved) == 1 and saved[0]["action"] == "user_input"
    assert saved[0]["payload"]["placement_target"]["section_key"] == "volunteer"


def test_patch_user_input_bogus_extra_placement_target_rejected(
    db_session, tmp_path, monkeypatch
):
    # F#4: a user_input placement_target that does not resolve to a live custom
    # section (here: the section is disabled) is rejected 400 — the target space is
    # validated regardless of action, guarding MCP/API callers.
    job = _seed_job(db_session)
    slug = _seed_base(
        db_session,
        tmp_path,
        monkeypatch,
        slug="ui_bad_extra",
        resume_json=_resume_with_volunteer(section_enabled=False),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        rejected = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:salesforce",
                    "action": "user_input",
                    "payload": {
                        "placement_target": {
                            "section": "extra",
                            "section_key": "volunteer",
                            "index_or_category": 0,
                        },
                        "text": "irrelevant",
                    },
                }
            ],
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 400
    assert "extra section" in rejected.json()["detail"]
    assert after.json()["resolutions_json"] == []


def test_patch_absent_add_keyword_extra_target_rejected_by_honesty(
    db_session, tmp_path, monkeypatch
):
    # F#7: the full save path rejects an add_keyword on an engine-ABSENT skill
    # whose placement_target points at a custom section — the honesty invariant
    # (unverified adds go to skills only) fires for extras exactly as for core
    # experience/projects, even though the extra target is otherwise valid.
    job = _seed_job(db_session)
    slug = _seed_base(
        db_session,
        tmp_path,
        monkeypatch,
        slug="honesty_extra",
        resume_json=_resume_with_volunteer(),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = _create_clean(client, job, slug)
        rejected = _patch(
            client,
            created["id"],
            [
                {
                    "gap_id": "skill:salesforce",  # absent -> fix_hint == "absent"
                    "action": "add_keyword",
                    "payload": {
                        "placement_target": {
                            "section": "extra",
                            "section_key": "volunteer",
                            "index_or_category": 0,
                        },
                        "wording": "Salesforce",
                    },
                }
            ],
        )
        after = client.get(f"/api/tailoring-sessions/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 400
    assert "skills section" in rejected.json()["detail"]
    assert after.json()["resolutions_json"] == []


def test_tailor_revalidates_stale_extra_placement_target_on_legacy_session(
    db_session, tmp_path, monkeypatch
):
    # F#5: a LEGACY session (no staleness hashes) whose saved placement_target's
    # custom section is deleted AFTER save must fail at tailor() time — the second
    # net catches what base_content_hash normally would. The offending gap_id is
    # named and the session stays open.
    job = _seed_job(db_session)
    slug = _seed_base(
        db_session,
        tmp_path,
        monkeypatch,
        slug="stale_extra",
        resume_json=_resume_with_volunteer(),
    )
    _forbid_llm(monkeypatch)  # re-validation must raise BEFORE any LLM/ops work

    created = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    tailoring_session.save_resolutions(
        created.id,
        [
            {
                "gap_id": "skill:tableau",  # matched (not absent) -> extra target OK at save
                "action": "add_keyword",
                "payload": {
                    "placement_target": {
                        "section": "extra",
                        "section_key": "volunteer",
                        "index_or_category": 0,
                    },
                    "wording": "Tableau",
                },
            }
        ],
        session=db_session,
    )

    # Make it a legacy session (staleness unknowable) and delete the extra section
    # from the base on disk (load_base_resume reads disk).
    row = db_session.get(TailoringSession, created.id)
    row.base_content_hash = None
    row.jd_extraction_hash = None
    db_session.commit()
    stripped = _resume_with_volunteer()
    stripped["extra_sections"] = []  # the whole section is gone now
    (tmp_path / f"{slug}.json").write_text(json.dumps(stripped))

    with pytest.raises(ValueError, match="skill:tableau"):
        tailoring_session.tailor(created.id, session=db_session)

    db_session.rollback()
    assert db_session.get(TailoringSession, created.id).status == "open"


# --- Post-review hardening: evidence gates, pre-op dedupe, live-text survival ---


def test_enable_entry_requires_literal_evidence_of_the_gap_skill(
    db_session, tmp_path, monkeypatch
):
    """The skills-only honesty exemption is earned: enabling an entry that does
    not literally evidence the gap's JD skill must be rejected at save time."""
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="no literal evidence"):
        tailoring_session.save_resolutions(
            tailoring.id,
            [
                {
                    # MLflow gap, but entry 0's evidence is Kafka-only.
                    "gap_id": "skill:mlflow",
                    "action": "enable_entry",
                    "payload": {"section": "projects", "index": 0},
                }
            ],
            session=db_session,
        )


def test_port_kb_point_requires_point_and_wording_to_evidence_the_skill(
    db_session, tmp_path, monkeypatch
):
    """An approved-but-unrelated point must not authorize arbitrary prose."""
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)  # text: "Tracked runs in MLflow"

    # Point does not evidence the Kafka gap at all.
    with pytest.raises(ValueError, match="does not literally evidence"):
        tailoring_session.save_resolutions(
            tailoring.id,
            [
                {
                    "gap_id": "skill:kafka",
                    "action": "port_kb_point",
                    "payload": {
                        "kb_point_id": str(approved.id),
                        "placement_target": {
                            "section": "projects",
                            "index_or_category": 1,
                        },
                        "wording": "Streamed events with Kafka at scale",
                    },
                }
            ],
            session=db_session,
        )

    # Point evidences MLflow, but the wording that would land does not.
    with pytest.raises(ValueError, match="wording must contain"):
        tailoring_session.save_resolutions(
            tailoring.id,
            [
                {
                    "gap_id": "skill:mlflow",
                    "action": "port_kb_point",
                    "payload": {
                        "kb_point_id": str(approved.id),
                        "placement_target": {
                            "section": "projects",
                            "index_or_category": 1,
                        },
                        "wording": "Led Kubernetes migration of 200 microservices",
                    },
                }
            ],
            session=db_session,
        )


def test_pre_ops_dedupe_repeated_point_and_enable():
    """Two gaps satisfied by the same point (or entry) produce ONE op each —
    the single bullet already evidences both JD terms."""
    port_payload = {
        "kb_point_id": "11111111-1111-1111-1111-111111111111",
        "placement_target": {"section": "projects", "index_or_category": 1},
        "wording": "Deployed models with Docker and Kubernetes",
    }
    resolutions = [
        {"gap_id": "skill:docker", "action": "port_kb_point", "payload": dict(port_payload)},
        {"gap_id": "skill:kubernetes", "action": "port_kb_point", "payload": dict(port_payload)},
        {"gap_id": "skill:kafka", "action": "enable_entry",
         "payload": {"section": "projects", "index": 0}},
        {"gap_id": "skill:spark", "action": "enable_entry",
         "payload": {"section": "projects", "index": 0}},
    ]
    ops, handled, lines = tailoring_session._deterministic_pre_ops(resolutions)
    assert [op.kind for op in ops] == ["add_bullet", "toggle_entry"]
    assert len(handled) == 2
    assert len(lines) == 2


def test_missing_keywords_ignores_disabled_entries_and_fused_fragments():
    """Survival must be judged on engine-visible text only, per fragment:
    a keyword surviving only inside a disabled entry is still missing, and
    adjacent list items must not fuse into a phantom multi-word match."""
    document = {
        "summary": "",
        "skills": [{"category": "Data", "items": ["Apache", "Kafka"]}],
        "experience": [],
        "projects": [
            {
                "name": "Warehouse",
                "enabled": False,
                "bullets": ["Built Snowflake ELT pipelines"],
                "tech": "Snowflake",
            }
        ],
    }
    resolutions = [
        {"gap_id": "skill:snowflake", "action": "add_keyword",
         "payload": {"wording": "Snowflake",
                     "placement_target": {"section": "skills", "index_or_category": "Data"}}},
        {"gap_id": "skill:apache-kafka", "action": "add_keyword",
         "payload": {"wording": "Apache Kafka",
                     "placement_target": {"section": "skills", "index_or_category": "Data"}}},
        {"gap_id": "skill:kafka", "action": "add_keyword",
         "payload": {"wording": "Kafka",
                     "placement_target": {"section": "skills", "index_or_category": "Data"}}},
    ]
    missing = tailoring_session._missing_keywords(document, resolutions)
    assert [wording for wording, _ in missing] == ["Snowflake", "Apache Kafka"]


# --- Task 17: KB write-back of elicited answers (the flywheel) ---

_ELICITED_TEXT = (
    "Tuned Kafka consumer groups to cut end-to-end event latency from 9s to 2s "
    "across three ingestion topics"
)


def _save_user_input(tailoring, db_session, *, text=_ELICITED_TEXT, index=1):
    return tailoring_session.save_resolutions(
        tailoring.id,
        [
            {
                "gap_id": "skill:kafka",
                "action": "user_input",
                "payload": {
                    "text": text,
                    "placement_target": {
                        "section": "projects",
                        "index_or_category": index,
                    },
                },
            }
        ],
        session=db_session,
    )


def test_write_back_creates_draft_point_on_matching_entity(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)  # entity titled "Churn Model"
    _save_user_input(tailoring, db_session)  # targets projects[1] = "Churn Model"
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )

    tailored = tailoring_session.tailor(tailoring.id, session=db_session)

    point = db_session.scalar(
        select(KBPoint).where(KBPoint.origin == "gap_elicitation")
    )
    assert point is not None
    assert point.state == "draft"
    assert point.text == _ELICITED_TEXT
    assert point.entity_id == approved.entity_id
    assert point.origin_detail == f"tailoring_session:{tailored.id}"


def test_write_back_dedups_and_skips_short_or_unmatched(
    db_session, tmp_path, monkeypatch
):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    approved, _ = _seed_kb_points(db_session)
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )
    # Seed a long approved point, then answer with a case-tweaked duplicate:
    # cosine ~1.0 → dedup must refuse the write-back.
    long_point = KBPoint(
        entity_id=approved.entity_id,
        text=_ELICITED_TEXT,
        state="approved",
        origin="manual",
    )
    db_session.add(long_point)
    db_session.flush()
    _save_user_input(tailoring, db_session, text=_ELICITED_TEXT.upper())

    tailoring_session.tailor(tailoring.id, session=db_session)

    assert (
        db_session.scalar(select(KBPoint).where(KBPoint.origin == "gap_elicitation"))
        is None
    )


def test_is_duplicate_point_falls_back_to_exact_match(monkeypatch):
    monkeypatch.setattr(
        "app.services.ats.embeddings.embed_texts",
        lambda texts: (_ for _ in ()).throw(RuntimeError("no model")),
    )
    assert tailoring_session._is_duplicate_point("Some Text", ["  some text  "])
    assert not tailoring_session._is_duplicate_point("Some Text", ["different"])


def test_write_back_skips_when_no_entity_matches(db_session, tmp_path, monkeypatch):
    tailoring = _open_library_session(db_session, tmp_path, monkeypatch)
    # No KB entities seeded at all.
    _save_user_input(tailoring, db_session)
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )

    tailoring_session.tailor(tailoring.id, session=db_session)

    assert (
        db_session.scalar(select(KBPoint).where(KBPoint.origin == "gap_elicitation"))
        is None
    )
