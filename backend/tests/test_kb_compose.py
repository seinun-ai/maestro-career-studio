import inspect
import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.career_kb import KBEntity, KBPoint
from app.services import career_kb


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _profile(db_session, **kw):
    profile = career_kb.get_or_create_profile(db_session)
    for key, value in kw.items():
        setattr(profile, key, value)
    db_session.flush()
    return profile


def test_compose_context_shape(db_session):
    _profile(db_session, summary="MSBA grad", notes="OPT eligible mid-2026")
    edu = KBEntity(
        kind="education",
        title="MS Business Analytics",
        org="UT Dallas",
        start_date="2024",
        end_date="2026",
        status="completed",
    )
    cert = KBEntity(kind="certification", title="AWS SAA", org="Amazon", status="completed")
    proj = KBEntity(
        kind="project",
        title="DocCompare",
        org="Fictional Data Studio",
        status="ongoing",
        detail_json={"tech": "RAG"},
        notes="RAG, pgvector, prod",
    )
    archived = KBEntity(kind="project", title="OldThing", status="archived", notes="secret")
    db_session.add_all([edu, cert, proj, archived])
    db_session.flush()
    point = KBPoint(
        entity_id=proj.id,
        text="Shipped retrieval eval harness",
        state="approved",
        origin="manual",
    )
    db_session.add(point)
    db_session.flush()

    ctx = career_kb.compose_context(db_session)

    assert "IDENTITY" in ctx
    assert "OPT eligible mid-2026" in ctx
    # identity carries education + certification titles
    assert "MS Business Analytics" in ctx
    assert "AWS SAA" in ctx
    # depth carries the ongoing project + its notes
    assert "DEPTH BEYOND THE RESUME" in ctx
    assert "DocCompare" in ctx
    assert "RAG, pgvector, prod" in ctx
    # archived entity notes are excluded
    assert "secret" not in ctx
    # approved point texts are resume-visible, not part of beyond-the-resume context
    assert "Shipped retrieval eval harness" not in ctx


def test_compose_context_structured_first(db_session):
    _profile(db_session, summary="", notes="")
    edu = KBEntity(
        kind="education",
        title="BS Computer Science",
        org="VIT",
        start_date="2018",
        end_date="2022",
        status="completed",
    )
    db_session.add(edu)
    db_session.flush()

    ctx = career_kb.compose_context(db_session)

    # even with an empty profile.notes, identity has an Education line built
    # from the entity's structured fields (not relocated free text)
    assert "IDENTITY" in ctx
    assert "Education: BS Computer Science" in ctx
    assert "VIT" in ctx


def test_compose_context_size_cap_trims_completed_first(db_session):
    _profile(db_session, summary="S", notes="N")
    ongoing = KBEntity(
        kind="project",
        title="OngoingProj",
        status="ongoing",
        notes="ONGOING_" + "x" * 100,
    )
    old = KBEntity(
        kind="experience",
        title="OldJob",
        org="OldCo",
        status="completed",
        end_date="2019",
        notes="OLD_" + "x" * 5000,
    )
    recent = KBEntity(
        kind="experience",
        title="RecentJob",
        org="RecentCo",
        status="completed",
        end_date="2023",
        notes="RECENT_" + "x" * 1000,
    )
    db_session.add_all([ongoing, old, recent])
    db_session.flush()

    ctx = career_kb.compose_context(db_session)

    assert len(ctx) <= career_kb.CONTEXT_CHAR_CAP
    # the OLDEST completed entity's notes drop first (header survives)
    assert "OLD_" not in ctx
    assert "OldJob" in ctx
    # the newer completed entity's notes are retained (proves oldest-first)
    assert "RECENT_" in ctx
    # the ongoing entity's notes are never trimmed
    assert "ONGOING_" in ctx
    # identity survives untouched
    assert "IDENTITY" in ctx


def test_compose_endpoint_returns_valid_resume_data(client, db_session):
    profile = career_kb.get_or_create_profile(db_session)
    profile.contact_json = {"name": "Riley", "email": "a@b.com"}
    profile.summary = "Data scientist"
    profile.skills_json = [{"category": "Languages", "items": ["Python"]}]
    db_session.commit()

    # A completed (older) role and an ongoing role — ongoing must sort first.
    client.post(
        "/api/kb/entities",
        json={
            "kind": "experience",
            "title": "OldRole",
            "org": "OldCo",
            "start_date": "2018",
            "end_date": "2020",
            "status": "completed",
        },
    )
    ongoing_id = client.post(
        "/api/kb/entities",
        json={
            "kind": "experience",
            "title": "DS",
            "org": "Acme",
            "start_date": "2022",
            "status": "ongoing",
        },
    ).json()["id"]
    # manual point is born approved
    client.post(f"/api/kb/entities/{ongoing_id}/points", json={"text": "Approved bullet"})
    # a draft point must NOT surface as a resume bullet
    db_session.add(
        KBPoint(
            entity_id=uuid.UUID(ongoing_id),
            text="Draft bullet",
            state="draft",
            origin="ingested",
        )
    )
    db_session.commit()

    r = client.get("/api/kb/compose")
    assert r.status_code == 200
    body = r.json()

    from app.schemas.resume import ResumeData

    ResumeData.model_validate(body)  # composed payload validates

    # ongoing-first ordering: the ongoing role precedes the completed one
    roles = [e["role"] for e in body["experience"]]
    assert roles == ["DS", "OldRole"]

    ongoing_exp = body["experience"][0]
    assert "Approved bullet" in ongoing_exp["bullets"]
    assert "Draft bullet" not in ongoing_exp["bullets"]


def test_compose_emits_empty_extra_sections(client, db_session):
    # KB has no model for arbitrary custom sections yet, so compose emits [] —
    # it never maps cert/project entities into extras by display title.
    profile = career_kb.get_or_create_profile(db_session)
    profile.contact_json = {"name": "Riley", "email": "a@b.com"}
    db_session.commit()

    body = client.get("/api/kb/compose").json()
    assert body["extra_sections"] == []


def test_gap_tailor_prompt_has_no_memory_param():
    from app.services import prompt_assembly

    assert "memory" not in inspect.signature(
        prompt_assembly.build_gap_tailor_prompt
    ).parameters
