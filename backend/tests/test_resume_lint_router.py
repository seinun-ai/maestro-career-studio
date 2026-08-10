from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.bullet_classification import BulletClassification
from app.models.health_gate_waiver import HealthGateWaiver
from app.models.resume_lint_report import ResumeLintReport
from app.routers import resume_lint as lint_router

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


def test_answer_ask_returns_suggestion(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "ask-bullet-1", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 1},
        }],
    )
    monkeypatch.setattr(
        lint_router.health_guards, "guarded_rewrite",
        lambda db, text, *, context: "Served 5000 users with the platform.",
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
    assert r.json() == {"suggestion": "Served 5000 users with the platform."}


def test_answer_ask_missing_finding_returns_404(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "some-other-finding", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 0},
        }],
    )
    monkeypatch.setattr(
        lint_router.health_guards, "guarded_rewrite",
        lambda db, text, *, context: "x",
    )

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
    monkeypatch.setattr(
        lint_router.health_guards, "guarded_rewrite",
        lambda db, text, *, context: "x",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/resume-lint/base/data_scientist/ask/gap-ask/answer",
            json={"answer": "hello"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


def test_answer_ask_returns_422_when_rewrite_none(db_session, monkeypatch):
    _seed(db_session, slug="data_scientist")
    _seed_report(
        db_session, "data_scientist",
        [{
            "id": "ask-bullet-1", "type": "ask",
            "location": {"section": "experience", "index": 0, "bullet_index": 0},
        }],
    )
    monkeypatch.setattr(
        lint_router.health_guards, "guarded_rewrite",
        lambda db, text, *, context: None,
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
    # Would return a string if the extraction ever reached the rewrite.
    monkeypatch.setattr(
        lint_router.health_guards, "guarded_rewrite",
        lambda db, text, *, context: "should not be reached",
    )

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
