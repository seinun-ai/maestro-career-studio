"""Provenance columns for KB writes: who wrote this row, from which client."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.models.career_kb import KBEntity, KBPoint


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


MCP_HEADERS = {
    "X-Maestro-CS-Origin": "mcp",
    "X-Maestro-CS-Origin-Detail": "Claude Desktop",
}


def test_entity_origin_defaults_to_none(db_session):
    entity = KBEntity(kind="certification", title="AWS SAA")
    db_session.add(entity)
    db_session.flush()
    assert entity.origin is None
    assert entity.origin_detail is None


def test_point_origin_detail_records_the_client(db_session):
    entity = KBEntity(kind="certification", title="AWS SAA")
    db_session.add(entity)
    db_session.flush()
    point = KBPoint(
        entity_id=entity.id,
        text="Passed the exam on 12 July 2026.",
        state="draft",
        origin="mcp",
        origin_detail="Claude Desktop",
    )
    db_session.add(point)
    db_session.flush()
    assert point.origin_detail == "Claude Desktop"


def test_create_entity_records_mcp_origin(client, db_session):
    resp = client.post(
        "/api/kb/entities",
        json={"kind": "certification", "title": "AWS SAA"},
        headers=MCP_HEADERS,
    )
    assert resp.status_code == 200
    entity = db_session.get(KBEntity, UUID(resp.json()["id"]))
    assert (entity.origin, entity.origin_detail) == ("mcp", "Claude Desktop")


def test_create_entity_without_headers_stays_unattributed(client, db_session):
    resp = client.post("/api/kb/entities", json={"kind": "project", "title": "Web thing"})
    assert resp.status_code == 200
    entity = db_session.get(KBEntity, UUID(resp.json()["id"]))
    assert entity.origin is None


def test_demoting_a_point_clears_approved_at(client, db_session):
    entity = KBEntity(kind="project", title="Thing")
    db_session.add(entity)
    db_session.flush()
    point = KBPoint(entity_id=entity.id, text="Old text", state="approved", origin="manual")
    point.approved_at = datetime.now(UTC)
    db_session.add(point)
    db_session.commit()

    resp = client.patch(
        f"/api/kb/points/{point.id}",
        json={"text": "New text", "state": "draft"},
    )
    assert resp.status_code == 200
    assert resp.json()["approved_at"] is None


def test_timeline_names_the_client_that_captured_a_point(client, db_session):
    entity = KBEntity(kind="project", title="Thing", origin="mcp", origin_detail="ChatGPT")
    db_session.add(entity)
    db_session.flush()
    db_session.add(
        KBPoint(
            entity_id=entity.id,
            text="Shipped the ingest pipeline.",
            state="draft",
            origin="mcp",
            origin_detail="ChatGPT",
        )
    )
    db_session.commit()

    body = client.get(f"/api/kb/entities/{entity.id}").json()
    labels = [ev["label"] for ev in body["timeline"]]
    assert "Entity created by ChatGPT" in labels
    assert any(
        ev["type"] == "point_captured" and "ChatGPT" in ev["label"]
        for ev in body["timeline"]
    )


def test_web_written_points_add_no_capture_event(client, db_session):
    entity = KBEntity(kind="project", title="Thing")
    db_session.add(entity)
    db_session.flush()
    db_session.add(
        KBPoint(entity_id=entity.id, text="Typed by hand.", state="draft", origin="manual")
    )
    db_session.commit()

    body = client.get(f"/api/kb/entities/{entity.id}").json()
    assert [ev for ev in body["timeline"] if ev["type"] == "point_captured"] == []
    assert "Entity created" in [ev["label"] for ev in body["timeline"]]
