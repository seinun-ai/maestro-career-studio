"""Provenance is stamped at every KBPoint creation site (orthogonal to origin)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.career_kb import KBDocument, KBEntity, KBPoint
from app.services import kb_ingest
from app.services.kb_consolidation import consolidate, consolidate_deterministic
from app.services.tailoring_session import _write_back_elicited_points


def _resume(**sections):
    base = {
        "contact": {"name": "A", "email": "a@x.com"},
        "summary": None,
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    base.update(sections)
    return base


def _make_llm(entity_payload=None, cluster_payload=None, capture_payload=None):
    def fake(*, prompt, model, response_format="json", **kw):
        if capture_payload is not None:
            return capture_payload
        if "group_indices" in prompt:
            return entity_payload if entity_payload is not None else {"clusters": []}
        if "bullet_indices" in prompt:
            return cluster_payload if cluster_payload is not None else {"clusters": []}
        if "points" in prompt or "document" in prompt.lower():
            return {"points": [{"text": "Cut latency 30% via caching"}]}
        raise AssertionError(f"unexpected prompt: {prompt[:80]!r}")

    return fake


def _entity_cluster(group_indices, title):
    return {
        "group_indices": group_indices,
        "existing_entity_id": None,
        "canonical": {
            "kind": "project",
            "title": title,
            "org": None,
            "start_date": None,
            "end_date": None,
        },
    }


def _drive_manual_point(db_session, monkeypatch, tmp_path):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
        client.post(f"/api/kb/entities/{eid}/points", json={"text": "Typed by hand on the page."})
        return db_session.scalars(select(KBPoint)).one()
    finally:
        app.dependency_overrides.clear()


def _drive_mint_document(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(capture_payload={"points": [{"text": "Extracted from an uploaded notes file."}]}),
    )
    ent = KBEntity(kind="project", title="X")
    db_session.add(ent)
    db_session.flush()
    doc = KBDocument(
        entity_id=ent.id,
        filename="notes.md",
        mime="text/markdown",
        text_content="we cut latency after weeks of work",
        ingest_status="extracted",
    )
    db_session.add(doc)
    db_session.flush()
    kb_ingest.mint_document(db_session, doc)
    db_session.flush()
    return db_session.scalars(select(KBPoint)).one()


def _drive_ingest_document(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: {
            "entity_id": None,
            "new_entity": {"kind": "project", "title": "DocThing", "org": None},
            "points": ["Validated a claim from the uploaded document itself."],
        },
    )
    kb_ingest.ingest_document(db_session, "notes.md", "text/markdown", b"document body text here")
    db_session.flush()
    return db_session.scalars(select(KBPoint)).one()


def _drive_capture(db_session, monkeypatch, tmp_path):
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: {
            "entity_id": str(ent.id),
            "new_entity": None,
            "points": ["Added agentic retrieval after a chat dump."],
        },
    )
    _entity, points = kb_ingest.capture(db_session, "did agentic retrieval on orbit")
    db_session.flush()
    return points[0]


def _drive_consolidate_verbatim(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={
                "clusters": [
                    {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
                ]
            },
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built the ingestion pipeline"]}])
    consolidate(db_session, [("a", r)])
    return db_session.scalars(select(KBPoint)).one()


def _drive_consolidate_merged(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={
                "clusters": [
                    {
                        "bullet_indices": [0, 1],
                        "existing_point_id": None,
                        "merged_text": "Improved retrieval recall",
                    }
                ]
            },
        ),
    )
    r1 = _resume(projects=[{"name": "Orbit", "bullets": ["Increased recall by 30%"]}])
    r2 = _resume(projects=[{"name": "Orbit", "bullets": ["Boosted recall substantially"]}])
    consolidate(db_session, [("a", r1), ("b", r2)])
    return db_session.scalars(select(KBPoint)).one()


def _drive_verbatim_points(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("no LLM on deterministic path")),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Shipped the pipeline"]}])
    consolidate_deterministic(db_session, [("ds", r)], commit=False)
    return db_session.scalars(select(KBPoint)).one()


def _drive_gap_writeback(db_session, monkeypatch, tmp_path):
    ent = KBEntity(kind="project", title="Churn Model")
    db_session.add(ent)
    db_session.flush()
    text = (
        "Tuned Kafka consumer groups to cut end-to-end event latency from 9s to 2s "
        "across three ingestion topics"
    )
    tailoring = SimpleNamespace(
        id=uuid4(),
        # Task 11: the skip reporter reads the frozen gaps for skill labels.
        gaps_json={"categories": []},
        resolutions_json=[
            {
                "gap_id": "skill:kafka",
                "action": "user_input",
                "payload": {
                    "text": text,
                    "placement_target": {"section": "projects", "index_or_category": 0},
                },
            }
        ],
    )
    _write_back_elicited_points(
        db_session, tailoring, {"projects": [{"name": "Churn Model"}]}
    )
    db_session.flush()
    return db_session.scalars(select(KBPoint)).one()


SITE_DRIVERS = {
    "manual_point": (_drive_manual_point, "user_stated"),
    "mint_document": (_drive_mint_document, "user_authored"),
    "ingest_document": (_drive_ingest_document, "user_authored"),
    "capture": (_drive_capture, "user_stated"),
    "consolidate_verbatim": (_drive_consolidate_verbatim, "user_authored"),
    "consolidate_merged": (_drive_consolidate_merged, "derived_unverified"),
    "write_verbatim_points": (_drive_verbatim_points, "user_authored"),
    "gap_writeback": (_drive_gap_writeback, "user_stated"),
}


@pytest.mark.parametrize("site,expected", [(k, v[1]) for k, v in SITE_DRIVERS.items()])
def test_every_point_creation_site_stamps_provenance(db_session, monkeypatch, tmp_path, site, expected):
    driver, _ = SITE_DRIVERS[site]
    point = driver(db_session, monkeypatch, tmp_path)
    assert point.provenance == expected


def test_llm_merged_wording_is_never_user_authored(db_session, monkeypatch, tmp_path):
    point = _drive_consolidate_merged(db_session, monkeypatch, tmp_path)
    assert point.provenance == "derived_unverified"
    assert point.provenance != "user_authored"
    assert point.text == "Improved retrieval recall"


def test_ingest_document_stamps_entity_origin_from_caller(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: {
            "entity_id": None,
            "new_entity": {"kind": "certification", "title": "AWS SAA", "org": "AWS"},
            "points": ["Passed the associate exam on the first attempt."],
        },
    )
    kb_ingest.ingest_document(
        db_session,
        "cert.txt",
        "text/plain",
        b"AWS certificate text",
        origin="mcp",
        origin_detail="Claude Desktop",
    )
    db_session.flush()
    entity = db_session.scalars(select(KBEntity)).one()
    assert entity.origin == "mcp"
    assert entity.origin_detail == "Claude Desktop"


def test_llm_consolidate_entity_builders_stamp_origin(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={
                "clusters": [
                    {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
                ]
            },
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built the ingestion pipeline"]}])
    consolidate(db_session, [("a", r)], commit=False)
    ents = db_session.scalars(select(KBEntity)).all()
    assert ents
    assert all(e.origin == "consolidated" for e in ents)


def test_consolidation_entity_builders_stamp_origin(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("no LLM on deterministic path")),
    )
    r = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": ["Shipped the pipeline"],
            }
        ],
        education=[{"institution": "State U", "degree": "BS CS"}],
        certifications=["AWS SAA"],
    )
    consolidate_deterministic(
        db_session, [("ds", r)], origin="mcp", origin_detail="Claude Desktop", commit=False
    )
    origins = {(e.kind, e.origin, e.origin_detail) for e in db_session.scalars(select(KBEntity))}
    assert origins == {
        ("experience", "mcp", "Claude Desktop"),
        ("education", "mcp", "Claude Desktop"),
        ("certification", "mcp", "Claude Desktop"),
    }


def test_no_writer_flips_user_cannot_confirm(db_session, monkeypatch):
    """user_cannot_confirm is durable: re-running writers never upgrades it.

    Phase C's never-upgrade test is out of this lane; this is the pin for
    inv-provenance-no-decay until that path ships.
    """
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    point = KBPoint(
        entity_id=ent.id,
        text="I cannot confirm the 40% recall claim",
        state="approved",
        origin="gap_elicitation",
        provenance="user_cannot_confirm",
    )
    db_session.add(point)
    db_session.flush()
    point_id = point.id

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={
                "clusters": [
                    {
                        "group_indices": [0],
                        "existing_entity_id": str(ent.id),
                        "canonical": {
                            "kind": "project",
                            "title": "Orbit",
                            "org": None,
                            "start_date": None,
                            "end_date": None,
                        },
                    }
                ]
            },
            cluster_payload={
                "clusters": [
                    {
                        "bullet_indices": [0],
                        "existing_point_id": str(point_id),
                        "merged_text": "Laundered into a fact",
                    }
                ]
            },
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["I cannot confirm the 40% recall claim"]}])
    consolidate(db_session, [("a", r)], commit=False)

    refreshed = db_session.get(KBPoint, point_id)
    assert refreshed.provenance == "user_cannot_confirm"
    assert refreshed.text == "I cannot confirm the 40% recall claim"

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: {
            "entity_id": str(ent.id),
            "new_entity": None,
            "points": ["A different user-stated claim about Orbit."],
        },
    )
    kb_ingest.capture(db_session, "another dump")
    db_session.flush()
    assert db_session.get(KBPoint, point_id).provenance == "user_cannot_confirm"
