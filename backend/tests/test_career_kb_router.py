import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBProfile


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


def test_create_entity_surfaces_same_identity_as_possible_duplicate(client, db_session):
    existing = client.post(
        "/api/kb/entities",
        json={
            "kind": "experience",
            "title": "Data Analyst",
            "org": "TCS",
            "start_date": "2021-06",
            "status": "completed",
        },
    ).json()

    response = client.post(
        "/api/kb/entities",
        json={
            "kind": "experience",
            "title": "Data Analyst",
            "org": "TCS",
            "start_date": "2021-06",
            "status": "ongoing",
        },
    )

    assert response.status_code == 200
    created = response.json()
    assert created["id"] != existing["id"]
    assert created["title"] == "Data Analyst"
    assert created["org"] == "TCS"
    assert created["status"] == "ongoing"
    assert created["possible_duplicates"] == [
        {"id": existing["id"], "title": "Data Analyst", "org": "TCS"}
    ]
    assert db_session.query(KBEntity).filter_by(kind="experience").count() == 2


def test_create_entity_returns_no_hint_for_unrelated_same_kind(client):
    client.post("/api/kb/entities", json={"kind": "project", "title": "Resume Tailor"})

    response = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Warehouse Forecasting"},
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == []


def test_create_entity_returns_no_hint_for_same_title_in_another_kind(client):
    client.post(
        "/api/kb/entities",
        json={"kind": "certification", "title": "Data Platform"},
    )

    response = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Data Platform"},
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == []


def test_create_entity_surfaces_valid_near_identity(client):
    existing = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Resume Tailor Platform"},
    ).json()

    response = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Resume Tailor"},
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == [
        {"id": existing["id"], "title": "Resume Tailor Platform", "org": None}
    ]


@pytest.mark.parametrize("incoming_title", ["Resume Tailor Platform", "Resume Tailor"])
def test_create_project_rejects_exact_or_near_hint_when_orgs_conflict(
    client, incoming_title
):
    client.post(
        "/api/kb/entities",
        json={
            "kind": "project",
            "title": "Resume Tailor Platform",
            "org": "Northwind Labs",
        },
    )

    response = client.post(
        "/api/kb/entities",
        json={
            "kind": "project",
            "title": incoming_title,
            "org": "Contoso Labs",
        },
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == []


def test_create_project_finds_compatible_exact_after_older_org_conflict(client):
    client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Atlas", "org": "Org A"},
    )
    compatible = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Atlas", "org": "Org B"},
    ).json()

    response = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Atlas", "org": "Org B"},
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == [
        {"id": compatible["id"], "title": "Atlas", "org": "Org B"}
    ]


def test_create_project_finds_compatible_near_after_conflicting_exact(client):
    client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Resume Tailor", "org": "Org A"},
    )
    compatible = client.post(
        "/api/kb/entities",
        json={
            "kind": "project",
            "title": "Resume Tailor Platform",
            "org": "Org B",
        },
    ).json()

    response = client.post(
        "/api/kb/entities",
        json={"kind": "project", "title": "Resume Tailor", "org": "Org B"},
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == [
        {
            "id": compatible["id"],
            "title": "Resume Tailor Platform",
            "org": "Org B",
        }
    ]


def test_create_entity_keeps_conflicting_certification_orgs_distinct(client):
    client.post(
        "/api/kb/entities",
        json={"kind": "certification", "title": "AI Practitioner", "org": "AWS"},
    )

    response = client.post(
        "/api/kb/entities",
        json={"kind": "certification", "title": "AI Practitioner", "org": "Google"},
    )

    assert response.status_code == 200
    assert response.json()["possible_duplicates"] == []


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


def test_list_points_caps_default_page_at_500(client, db_session):
    entity = KBEntity(kind="project", title="Pagination")
    db_session.add(entity)
    db_session.flush()
    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    for number in range(1, 502):
        db_session.add(
            KBPoint(
                id=uuid.UUID(int=number),
                entity_id=entity.id,
                text=f"Point {number}",
                state="draft",
                origin="ingested",
                created_at=created_at,
            )
        )
    db_session.commit()

    response = client.get("/api/kb/points")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 500
    assert rows[0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert rows[-1]["id"] == "00000000-0000-0000-0000-0000000001f4"


def test_list_points_offset_pages_keep_stable_order_and_state_filter(client, db_session):
    entity = KBEntity(kind="project", title="Stable pages")
    db_session.add(entity)
    db_session.flush()
    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    db_session.add(
        KBPoint(
            id=uuid.UUID("00000000-0000-0000-0000-000000000009"),
            entity_id=entity.id,
            text="Retired point",
            state="retired",
            origin="ingested",
            created_at=created_at,
        )
    )
    for number in range(10, 14):
        db_session.add(
            KBPoint(
                id=uuid.UUID(int=number),
                entity_id=entity.id,
                text=f"Draft point {number}",
                state="draft",
                origin="ingested",
                created_at=created_at,
            )
        )
    db_session.commit()

    page_one = client.get("/api/kb/points?state=draft&limit=2&offset=0")
    page_two = client.get("/api/kb/points?state=draft&limit=2&offset=2")

    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert [row["id"] for row in page_one.json()] == [
        "00000000-0000-0000-0000-00000000000a",
        "00000000-0000-0000-0000-00000000000b",
    ]
    assert [row["id"] for row in page_two.json()] == [
        "00000000-0000-0000-0000-00000000000c",
        "00000000-0000-0000-0000-00000000000d",
    ]


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
