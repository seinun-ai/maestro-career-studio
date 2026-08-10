import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.career_kb import KBDocument, KBPoint, KBProfile


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_profile_get_creates_singleton_and_patch_is_partial(client, db_session):
    initial = client.get("/api/kb/profile")
    assert initial.status_code == 200
    assert initial.json()["contact"] == {}

    updated = client.patch(
        "/api/kb/profile",
        json={
            "contact": {"name": "Sample", "email": "sample@example.com"},
            "summary": "Data and AI builder",
            "skills": [{"category": "Core", "items": ["Python"]}],
            "notes": "OPT eligible through 2028",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["contact"]["name"] == "Sample"
    assert body["skills"][0]["items"] == ["Python"]

    notes_only = client.patch("/api/kb/profile", json={"notes": "Updated note"})
    assert notes_only.status_code == 200
    assert notes_only.json()["summary"] == "Data and AI builder"
    assert notes_only.json()["notes"] == "Updated note"
    assert db_session.get(KBProfile, 1) is not None


def test_profile_patch_rejects_explicit_null(client):
    response = client.patch("/api/kb/profile", json={"summary": None})
    assert response.status_code == 422


def test_create_and_list_entities(client):
    r = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "DocCompare", "org": "Fictional Data Studio", "status": "ongoing"},
    )
    assert r.status_code == 200
    body = client.get("/api/kb/entities?kind=project").json()
    assert body[0]["title"] == "DocCompare"
    assert body[0]["point_count"] == 0 and body[0]["draft_count"] == 0


def test_manual_point_born_approved(client):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    r = client.post(f"/api/kb/entities/{eid}/points", json={"text": "Did a thing"})
    assert r.json()["state"] == "approved" and r.json()["origin"] == "manual"
    assert r.json()["approved_at"] is not None


def test_point_approve_sets_approved_at(client, db_session):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    point = KBPoint(entity_id=uuid.UUID(eid), text="draft point", state="draft", origin="ingested")
    db_session.add(point)
    db_session.commit()
    pid = str(point.id)

    r = client.patch(f"/api/kb/points/{pid}", json={"state": "approved"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "approved"
    assert body["approved_at"] is not None


def test_draft_inbox_lists_across_entities(client, db_session):
    a = client.post("/api/kb/entities", json={"kind": "project", "title": "Alpha"}).json()
    b = client.post("/api/kb/entities", json={"kind": "experience", "title": "Beta"}).json()
    db_session.add(KBPoint(entity_id=uuid.UUID(a["id"]), text="pa", state="draft", origin="ingested"))
    db_session.add(KBPoint(entity_id=uuid.UUID(b["id"]), text="pb", state="draft", origin="ingested"))
    db_session.commit()

    rows = client.get("/api/kb/points?state=draft").json()
    assert len(rows) == 2
    titles = {row["entity_title"] for row in rows}
    kinds = {row["entity_kind"] for row in rows}
    assert titles == {"Alpha", "Beta"}
    assert kinds == {"project", "experience"}


def test_entity_detail_includes_points_documents_timeline(client, db_session):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    client.post(f"/api/kb/entities/{eid}/points", json={"text": "approved point"})
    db_session.add(
        KBDocument(
            entity_id=uuid.UUID(eid),
            filename="resume.pdf",
            ingest_status="minted",
            ingest_summary="minted 3 points",
        )
    )
    db_session.commit()

    detail = client.get(f"/api/kb/entities/{eid}").json()
    assert len(detail["points"]) == 1
    assert len(detail["documents"]) == 1
    types = {ev["type"] for ev in detail["timeline"]}
    assert "created" in types
    assert "doc_added" in types


def test_patch_entity_fields_and_status(client):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "Old"}).json()["id"]
    r = client.patch(f"/api/kb/entities/{eid}", json={"title": "New", "status": "archived"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "New"
    assert body["status"] == "archived"


def test_patch_entity_detail_null_is_ignored_not_500(client):
    eid = client.post(
        "/api/kb/entities", json={"kind": "project", "title": "X", "detail": {"tech": "py"}}
    ).json()["id"]
    r = client.patch(f"/api/kb/entities/{eid}", json={"detail": None})
    assert r.status_code == 200
    assert r.json()["detail"] == {"tech": "py"}  # unchanged, no 500


def test_reassign_point_via_patch(client, db_session):
    a = client.post("/api/kb/entities", json={"kind": "project", "title": "A"}).json()
    b = client.post("/api/kb/entities", json={"kind": "project", "title": "B"}).json()
    point = KBPoint(entity_id=uuid.UUID(a["id"]), text="movable", state="draft", origin="ingested")
    db_session.add(point)
    db_session.commit()
    pid = str(point.id)

    r = client.patch(f"/api/kb/points/{pid}", json={"entity_id": b["id"]})
    assert r.status_code == 200
    assert r.json()["entity_id"] == b["id"]

    db_session.refresh(point)
    assert str(point.entity_id) == b["id"]


def test_reassign_point_to_missing_entity_404(client, db_session):
    a = client.post("/api/kb/entities", json={"kind": "project", "title": "A"}).json()
    point = KBPoint(entity_id=uuid.UUID(a["id"]), text="movable", state="draft", origin="ingested")
    db_session.add(point)
    db_session.commit()
    pid = str(point.id)

    r = client.patch(f"/api/kb/points/{pid}", json={"entity_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_delete_entity_cascades(client, db_session):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    point = KBPoint(entity_id=uuid.UUID(eid), text="p", state="draft", origin="ingested")
    db_session.add(point)
    db_session.commit()
    pid = point.id

    r = client.delete(f"/api/kb/entities/{eid}")
    assert r.status_code == 204
    assert db_session.get(KBPoint, pid) is None


def test_delete_point(client, db_session):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    point = KBPoint(entity_id=uuid.UUID(eid), text="p", state="draft", origin="ingested")
    db_session.add(point)
    db_session.commit()
    pid = point.id

    r = client.delete(f"/api/kb/points/{pid}")
    assert r.status_code == 204
    assert db_session.get(KBPoint, pid) is None


def test_invalid_kind_rejected(client):
    r = client.post("/api/kb/entities", json={"kind": "nonsense", "title": "X"})
    assert r.status_code == 422


def test_patch_entity_null_required_field_rejected(client):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    assert client.patch(f"/api/kb/entities/{eid}", json={"title": None}).status_code == 422
    assert client.patch(f"/api/kb/entities/{eid}", json={"kind": None}).status_code == 422
    assert client.patch(f"/api/kb/entities/{eid}", json={"status": None}).status_code == 422
    # nullable fields still accept explicit null
    assert client.patch(f"/api/kb/entities/{eid}", json={"org": None}).status_code == 200


def test_kb_context_returns_composed_resume_and_memory(client, db_session):
    """GET /api/kb/context = the chat get_career_context pair, over REST —
    the grounding surface for MCP social-post generation."""
    from app.services import career_kb as kb_svc

    profile = kb_svc.get_or_create_profile(db_session)
    profile.summary = "Data scientist"
    profile.notes = "OPT eligible mid-2026"
    db_session.commit()

    response = client.get("/api/kb/context")

    assert response.status_code == 200
    body = response.json()
    from app.schemas.resume import ResumeData

    ResumeData.model_validate(body["resume"])
    assert "OPT eligible mid-2026" in body["memory"]

def test_source_mutations_touch_career_export(client, monkeypatch):
    from app.routers import career_kb as router
    calls = []
    monkeypatch.setattr(router.career_exports, "best_effort_refresh", lambda db: calls.append(db))

    client.patch("/api/kb/profile", json={"summary": "Updated"})
    entity_id = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    client.post(f"/api/kb/entities/{entity_id}/points", json={"text": "Approved"})

    assert len(calls) == 3


def test_refresh_failure_never_fails_source_write(client, monkeypatch):
    from app.routers import career_kb as router
    monkeypatch.setattr(router.career_exports, "get_career_export", lambda _db, force=False: (_ for _ in ()).throw(RuntimeError("compose failed")))
    response = client.patch("/api/kb/profile", json={"summary": "Committed"})
    assert response.status_code == 200
    assert client.get("/api/kb/profile").json()["summary"] == "Committed"
