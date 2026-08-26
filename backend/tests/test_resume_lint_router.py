from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.bullet_classification import BulletClassification
from app.models.health_ask_answer import HealthAskAnswer
from app.models.health_gate_waiver import HealthGateWaiver
from app.models.resume_lint_report import ResumeLintReport
from app.routers import resume_lint as lint_router
from app.services import bullet_classify, resume_versions

SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Seasoned data scientist.",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2020",
            "end_date": "2024",
            "bullets": ["Led an analytics project.", "Kept the lights on."],
        }
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed(db_session, slug: str = "data_scientist", data_json=None) -> BaseResume:
    row = BaseResume(
        slug=slug,
        display_name=slug.replace("_", " ").title(),
        data_json=data_json if data_json is not None else SAMPLE_DATA,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _waivers(db_session, kind, key, gate_id):
    return db_session.scalars(
        select(HealthGateWaiver).where(
            HealthGateWaiver.resume_kind == kind,
            HealthGateWaiver.resume_key == key,
            HealthGateWaiver.gate_id == gate_id,
        )
    ).all()


def _unexpected_llm_call(**kwargs):
    raise AssertionError(f"LLM call should not be reached: {kwargs}")


# --------------------------------------------------------------------------- #
# waive


def test_waive_gate_creates_row_then_updates_reason(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        r1 = client.post(
            "/api/resume-lint/base/data_scientist/gates/S3/waive",
            json={"reason": "present role"},
        )
        assert r1.status_code == 204
        rows = _waivers(db_session, "base", "data_scientist", "S3")
        assert len(rows) == 1
        assert rows[0].reason == "present role"

        # Waiving again updates the reason in place (uq_health_waiver: no dup row).
        r2 = client.post(
            "/api/resume-lint/base/data_scientist/gates/S3/waive",
            json={"reason": "confirmed with candidate"},
        )
        assert r2.status_code == 204
        rows = _waivers(db_session, "base", "data_scientist", "S3")
        assert len(rows) == 1
        assert rows[0].reason == "confirmed with candidate"
    finally:
        app.dependency_overrides.clear()


def test_waive_gate_unknown_id_returns_422(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/gates/ZZ/waive",
            json={"reason": "whatever"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422
    assert not _waivers(db_session, "base", "data_scientist", "ZZ")


def test_waive_gate_empty_reason_returns_422(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/gates/S3/waive",
            json={"reason": "   "},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422
    assert not _waivers(db_session, "base", "data_scientist", "S3")


# --------------------------------------------------------------------------- #
# unwaive


def test_unwaive_gate_deletes_row_and_is_idempotent(db_session):
    db_session.add(
        HealthGateWaiver(
            resume_kind="base", resume_key="data_scientist",
            gate_id="S3", reason="present role",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        r1 = client.delete("/api/resume-lint/base/data_scientist/gates/S3/waive")
        assert r1.status_code == 204
        assert not _waivers(db_session, "base", "data_scientist", "S3")

        # Deleting a non-existent waiver is a no-op 204.
        r2 = client.delete("/api/resume-lint/base/data_scientist/gates/S3/waive")
        assert r2.status_code == 204
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# classification override


def test_classification_override_creates_row(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/classification-override",
            json={
                "content_hash": "0123456789abcdef",
                "level": "direct",
                "reason": "  Confirmed with the candidate.  ",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 204
    row = db_session.get(BulletClassification, "0123456789abcdef")
    assert row is not None
    assert row.override_level == "direct"
    assert row.override_reason == "Confirmed with the candidate."


def test_classification_override_invalid_level_returns_422(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/classification-override",
            json={"content_hash": "0123456789abcdef", "level": "amazing"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422
    assert db_session.get(BulletClassification, "0123456789abcdef") is None


def test_classification_override_rejects_non_hash_identifier(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/classification-override",
            json={"content_hash": "not-a-content-hash", "level": "direct"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# ask / answer


def _seed_report(db_session, slug, findings):
    db_session.add(
        ResumeLintReport(
            resume_kind="base", resume_key=slug,
            report_json={"findings": findings},
        )
    )
    db_session.commit()


def _complete_report_json(*, gates=None, insufficient_evidence=False):
    return {
        "score": 69,
        "grade": "C",
        "tier": "experienced",
        "counts": {"gate": 1, "critical": 1, "ask": 0, "note": 0},
        "gates": gates or [],
        "findings": [],
        "insufficient_evidence": insufficient_evidence,
    }


def test_get_latest_lint_surfaces_fresh_score_breakdown(db_session):
    base = _seed(db_session, slug="data_scientist")
    version = resume_versions.record_version(
        db_session, "base", base.slug, base.data_json, source="create"
    )
    report = ResumeLintReport(
        resume_kind="base",
        resume_key=base.slug,
        resume_version_number=version.version_number,
        report_json=_complete_report_json(
            gates=[{"id": "S3", "tier": "serious", "status": "fail"}],
            insufficient_evidence=True,
        ),
        features_json={
            "raw_score": 88,
            "e_hot": 0.75,
            "n_scoreable": 3,
            "levels": {"experience:0:0": 1.0},
        },
    )
    db_session.add(report)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/resume-lint/base/data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is False
    assert body["insufficient_evidence"] is True
    assert body["score_breakdown"] == {
        "raw_score": 88,
        "e_hot": 0.75,
        "n_scoreable": 3,
        "capped_by": "serious",
    }


def test_score_breakdown_omits_unapplied_gate_cap(db_session):
    base = _seed(db_session, slug="data_scientist")
    version = resume_versions.record_version(
        db_session, "base", base.slug, base.data_json, source="create"
    )
    report_json = _complete_report_json(
        gates=[{"id": "S3", "tier": "serious", "status": "fail"}]
    )
    report_json["score"] = 30
    db_session.add(
        ResumeLintReport(
            resume_kind="base",
            resume_key=base.slug,
            resume_version_number=version.version_number,
            report_json=report_json,
            features_json={"raw_score": 30, "e_hot": 0.25, "n_scoreable": 4},
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/resume-lint/base/data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["score_breakdown"]["capped_by"] is None


def test_get_latest_lint_marks_report_stale_after_version_bump(db_session):
    base = _seed(db_session, slug="data_scientist")
    first = resume_versions.record_version(
        db_session, "base", base.slug, base.data_json, source="create"
    )
    db_session.add(
        ResumeLintReport(
            resume_kind="base",
            resume_key=base.slug,
            resume_version_number=first.version_number,
            report_json=_complete_report_json(),
        )
    )
    changed = {**base.data_json, "summary": "Changed after analysis."}
    resume_versions.record_version(
        db_session, "base", base.slug, changed, source="form_edit"
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/resume-lint/base/data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is True
    assert body["insufficient_evidence"] is False
    assert body["score_breakdown"] is None


def test_answer_ask_returns_suggestion(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "ask-bullet-1", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 1},
        }],
    )
    calls = 0

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        nonlocal calls
        calls += 1
        assert "Original bullet: Kept the lights on." in prompt
        assert (
            "Additional context from the candidate (may be empty): served 5000 users"
            in prompt
        )
        assert model == "test-model"
        assert response_format == "json"
        assert trace_name == "resume_bullet_rewrite"
        return {"rewrite": "Served 5,000 users with the platform."}

    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(
        lint_router.health_guards.model_settings,
        "get_smart_model",
        lambda session: "test-model",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-bullet-1/answer",
            json={"answer": "served 5000 users"},
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.json() == {"suggestion": "Served 5,000 users with the platform."}
    assert calls == 1


def test_answer_ask_matching_content_hash_returns_suggestion(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session,
        "data_scientist",
        [
            {
                "id": "ask-current-bullet",
                "type": "ask",
                "content_hash": bullet_classify.content_hash("Kept the lights on."),
                "location": {
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 1,
                },
            }
        ],
    )

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        assert "Original bullet: Kept the lights on." in prompt
        assert model == "test-model"
        assert response_format == "json"
        assert trace_name == "resume_bullet_rewrite"
        return {"rewrite": "Served 5,000 users with the platform."}

    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(
        lint_router.health_guards.model_settings,
        "get_smart_model",
        lambda session: "test-model",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-current-bullet/answer",
            json={"answer": "served 5000 users"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"suggestion": "Served 5,000 users with the platform."}


def test_answer_ask_content_hash_mismatch_returns_409_without_llm(
    db_session, monkeypatch
):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session,
        "data_scientist",
        [
            {
                "id": "ask-stale-bullet",
                "type": "ask",
                "content_hash": bullet_classify.content_hash("Report-time bullet."),
                "location": {
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 1,
                },
            }
        ],
    )
    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", _unexpected_llm_call)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-stale-bullet/answer",
            json={"answer": "served 5000 users"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"].startswith("content changed since analysis")


def test_answer_ask_missing_hashed_target_returns_409_without_llm(
    db_session, monkeypatch
):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session,
        "data_scientist",
        [
            {
                "id": "ask-deleted-bullet",
                "type": "ask",
                "content_hash": bullet_classify.content_hash("Deleted bullet."),
                "location": {
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 99,
                },
            }
        ],
    )
    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", _unexpected_llm_call)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-deleted-bullet/answer",
            json={"answer": "served 5000 users"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"].startswith("content changed since analysis")


def test_answer_ask_missing_finding_returns_404(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "some-other-finding", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 0},
        }],
    )
    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", _unexpected_llm_call)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/nope/answer",
            json={"answer": "hello"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_answer_ask_non_bullet_location_returns_422(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "gap-ask", "type": "ask",
            "location": {"section": "experience"},  # no index/bullet_index
        }],
    )
    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", _unexpected_llm_call)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/gap-ask/answer",
            json={"answer": "hello"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


def test_answer_ask_returns_422_when_llm_fabricates(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "ask-bullet-1", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 0},
        }],
    )
    calls = 0

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        nonlocal calls
        calls += 1
        assert "Original bullet: Led an analytics project." in prompt
        assert "Additional context from the candidate (may be empty): hello" in prompt
        assert model == "test-model"
        assert response_format == "json"
        assert trace_name == "resume_bullet_rewrite"
        return {"rewrite": "Led an analytics project serving 5000 users."}

    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(
        lint_router.health_guards.model_settings,
        "get_smart_model",
        lambda session: "test-model",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-bullet-1/answer",
            json={"answer": "hello"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422
    assert calls == 2


def test_answer_ask_stale_index_degrades_to_422(db_session, monkeypatch):
    # Resume was edited since the report: the finding points past the end of the
    # bullet list. The IndexError is caught and degrades to 422 (not 500/200).
    _seed(
        db_session, slug="data_scientist",
        data_json={
            **SAMPLE_DATA,
            "experience": [
                {"company": "Acme", "role": "DS", "start_date": "2020",
                 "bullets": ["Only bullet."]},
            ],
        },
    )
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "stale-ask", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 5},
        }],
    )
    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", _unexpected_llm_call)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/stale-ask/answer",
            json={"answer": "x"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


def test_classification_override_null_level_clears_existing(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        r1 = client.post(
            "/api/resume-lint/classification-override",
            json={
                "content_hash": "fedcba9876543210",
                "level": "direct",
                "reason": "Candidate confirmed it",
            },
        )
        assert r1.status_code == 204
        db_session.expire_all()
        row = db_session.get(BulletClassification, "fedcba9876543210")
        assert row.override_level == "direct"
        assert row.override_reason == "Candidate confirmed it"

        # Re-posting with level=null clears the override in place.
        r2 = client.post(
            "/api/resume-lint/classification-override",
            json={"content_hash": "fedcba9876543210", "level": None},
        )
        assert r2.status_code == 204
    finally:
        app.dependency_overrides.clear()

    db_session.expire_all()
    row = db_session.get(BulletClassification, "fedcba9876543210")
    assert row is not None
    assert row.override_level is None
    assert row.override_reason is None


def test_answer_ask_no_report_returns_404(db_session):
    _seed(db_session, slug="data_scientist")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/whatever/answer",
            json={"answer": "hello"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def _stored_answer(db_session, finding_id="ask-bullet-1"):
    return db_session.scalar(
        select(HealthAskAnswer).where(
            HealthAskAnswer.resume_kind == "base",
            HealthAskAnswer.resume_key == "data_scientist",
            HealthAskAnswer.finding_id == finding_id,
        )
    )


def test_answer_ask_persists_even_when_rewrite_422s(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "ask-bullet-1", "type": "ask",
            "content_hash": bullet_classify.content_hash("Led an analytics project."),
            "location": {"section": "experience", "index": 0, "bullet_index": 0},
        }],
    )

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        return {"rewrite": "Led an analytics project serving 5000 users."}

    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(
        lint_router.health_guards.model_settings,
        "get_smart_model",
        lambda session: "test-model",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-bullet-1/answer",
            json={"answer": "hello"},
        )
        stored = TestClient(app).get("/api/resume-lint/base/data_scientist/answers")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 422
    row = _stored_answer(db_session)
    assert row is not None
    assert row.answer == "hello"
    assert row.suggestion is None
    body = stored.json()
    assert body["ask-bullet-1"]["answer"] == "hello"
    assert body["ask-bullet-1"]["suggestion"] is None
    assert body["ask-bullet-1"]["content_hash"] == bullet_classify.content_hash(
        "Led an analytics project."
    )


def test_answer_ask_rehydration_round_trip(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "ask-bullet-1", "type": "ask",
            "content_hash": bullet_classify.content_hash("Kept the lights on."),
            "location": {"section": "experience", "index": 0, "bullet_index": 1},
        }],
    )

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        return {"rewrite": "Served 5,000 users with the platform."}

    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(
        lint_router.health_guards.model_settings,
        "get_smart_model",
        lambda session: "test-model",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/ask-bullet-1/answer",
            json={"answer": "served 5000 users"},
        )
        stored = TestClient(app).get("/api/resume-lint/base/data_scientist/answers")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = stored.json()
    assert body["ask-bullet-1"] == {
        "answer": "served 5000 users",
        "suggestion": "Served 5,000 users with the platform.",
        "content_hash": bullet_classify.content_hash("Kept the lights on."),
    }


def test_draft_rewrite_409_never_calls_llm(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    monkeypatch.setattr(
        lint_router.health_guards.llm, "call_openai", _unexpected_llm_call
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/draft-rewrite",
            json={
                "location": {
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 1,
                },
                "expected_content_hash": bullet_classify.content_hash(
                    "Report-time bullet."
                ),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 409
    assert r.json()["detail"].startswith("content changed since analysis")


def test_draft_rewrite_condense_returns_hash_of_source_text(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    source = "Kept the lights on."
    seen = []

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        seen.append(prompt)
        return {"rewrite": "Kept the lights on."}

    monkeypatch.setattr(lint_router.health_guards.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(
        lint_router.health_guards.model_settings,
        "get_smart_model",
        lambda session: "test-model",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/draft-rewrite",
            json={
                "location": {
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 1,
                },
                "objective": "condense",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.json() == {
        "suggestion": "Kept the lights on.",
        "content_hash": bullet_classify.content_hash(source),
    }
    assert seen and "CONDENSE OBJECTIVE" in seen[0]
