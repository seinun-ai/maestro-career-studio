"""Wire tests for GET kb-sync-status and POST kb-sync."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from tests.test_kb_base_sync_classify import (
    _drifting_resume,
    _exp_entity,
    _resume,
    _seed_base,
)


def _row_counts(db_session):
    return (
        db_session.query(KBPoint).count(),
        db_session.query(KBEntity).count(),
        db_session.query(KBPortLog).count(),
    )


def test_kb_sync_status_404_unknown_slug(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        res = TestClient(app).get("/api/base-resumes/nope/kb-sync-status")
        assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_kb_sync_status_is_read_only(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="Built the ingestion pipeline")
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": ["Negotiated a net-new vendor contract worth two million"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    before = _row_counts(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        res = TestClient(app).get("/api/base-resumes/hybrid/kb-sync-status")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counts"]["new"] == 1
    # `recorded_drift` is always present and is a real count — zero here, never
    # null. Only `last_kb_synced_at` carries null, and only before a first sync.
    assert body["counts"]["recorded_drift"] == 0
    assert body["last_kb_synced_at"] is None
    assert _row_counts(db_session) == before


def test_kb_sync_status_reports_recorded_drift_and_last_synced(
    db_session, tmp_path, monkeypatch
):
    """After a sync, the wire must show drift as recorded, not actionable,
    and say when the sync happened — and the GET itself must write nothing."""
    _exp_entity(db_session, text="machine learning")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        applied = client.post("/api/base-resumes/hybrid/kb-sync")
        assert applied.status_code == 200, applied.text
        assert applied.json()["drifted"] == 1
        assert applied.json()["last_kb_synced_at"] is not None

        before = _row_counts(db_session)
        res = client.get("/api/base-resumes/hybrid/kb-sync-status")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counts"]["drift"] == 0
    assert body["counts"]["recorded_drift"] >= 1
    assert body["last_kb_synced_at"] is not None
    datetime.fromisoformat(body["last_kb_synced_at"])  # ISO-parseable
    assert _row_counts(db_session) == before


def test_kb_sync_apply_reports_skill_items_not_just_categories(
    db_session, tmp_path, monkeypatch
):
    """Two new skills in ONE category is two skills, not one.

    `skills` carries CATEGORY names (one append per category touched), which is
    the shape the port report has always had. Summarising a sync needs the
    ITEMS, so `skills_added` carries those — otherwise the UI reads a category
    count and tells the user it filed one skill when it filed two.
    """
    _exp_entity(db_session, text="machine learning")
    data = _drifting_resume()
    data["skills"] = [{"category": "Infra", "items": ["Kubernetes", "Terraform"]}]
    _seed_base(db_session, tmp_path, monkeypatch, data)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        res = TestClient(app).post("/api/base-resumes/hybrid/kb-sync")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["skills"] == ["Infra"]
    assert body["skills_added"] == ["Kubernetes", "Terraform"]


def test_kb_sync_apply_reports_renamed_entity_once_and_only_once(
    db_session, tmp_path, monkeypatch
):
    """A near match that renames an entity says so on the wire, exactly once.

    Renaming is the only write in sync that CHANGES an existing entity, so it
    cannot be silent. Two bullets under the richer role title produce two sync
    items against the same entity; the second finds the title already upgraded,
    so `renamed` carries one name, not two. A second sync then matches by exact
    identity key — the rename made it exact — and has nothing left to rename.
    """
    _exp_entity(db_session, text="Built the ingestion pipeline")  # title "Engineer"
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer, Platform Team",
                "start_date": "2021",
                "bullets": [
                    "Stood up a greenfield billing service",
                    "Negotiated a net-new vendor contract worth two million",
                ],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        first = client.post("/api/base-resumes/hybrid/kb-sync")
        assert first.status_code == 200, first.text
        assert first.json()["renamed"] == ["Engineer, Platform Team"]

        again = client.post("/api/base-resumes/hybrid/kb-sync")
        assert again.status_code == 200, again.text
        assert again.json()["renamed"] == []
    finally:
        app.dependency_overrides.clear()
    assert db_session.query(KBEntity).count() == 1


def test_kb_sync_apply_creates_drafts(db_session, tmp_path, monkeypatch):
    data = _resume(
        experience=[
            {
                "company": "OtherCo",
                "role": "Lead",
                "start_date": "2024",
                "bullets": ["Stood up a greenfield billing service"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        res = TestClient(app).post("/api/base-resumes/hybrid/kb-sync")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 1
    points = db_session.scalars(select(KBPoint)).all()
    assert len(points) == 1
    assert points[0].origin == "base_sync"
    assert points[0].provenance == "user_authored"


def test_kb_point_json_includes_provenance(db_session):
    ent = KBEntity(kind="experience", title="Acme")
    db_session.add(ent)
    db_session.flush()
    db_session.add(
        KBPoint(
            entity_id=ent.id,
            text="Did a thing",
            state="draft",
            origin="manual",
            provenance="user_stated",
        )
    )
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        res = TestClient(app).get(f"/api/kb/entities/{ent.id}")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    points = res.json()["points"]
    assert points[0]["provenance"] == "user_stated"
