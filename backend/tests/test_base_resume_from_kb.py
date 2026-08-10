"""Slice 6: compose a role-targeted base resume from selected KB entities.

The KB is the master. `compose_resume_data()` with no argument returns the WHOLE
knowledge base, which is a master view — useful for /kb/compose and chat
grounding, wrong as a base resume. This endpoint narrows it.
"""

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint
from app.services import career_kb


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _client(db_session) -> TestClient:
    app.dependency_overrides[get_db] = _override_db(db_session)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _entity(db_session, kind, title, org=None, approved=("Did the thing.",)):
    ent = KBEntity(kind=kind, title=title, org=org, status="completed")
    db_session.add(ent)
    db_session.flush()
    for text in approved:
        db_session.add(KBPoint(entity_id=ent.id, text=text, state="approved", origin="manual"))
    db_session.commit()
    return ent


def _profile(db_session, **kw):
    p = career_kb.get_or_create_profile(db_session)
    p.contact_json = {"name": "Sam Sample", "email": "sam@example.com"}
    p.summary = kw.get("summary", "Whole-career summary spanning every role.")
    p.skills_json = kw.get("skills", [{"category": "Core", "items": ["Python", "SQL"]}])
    db_session.commit()
    return p


def _stub_side_effects(monkeypatch, tmp_path):
    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        "app.routers.base_resumes.base_resume_render.render_base_resume",
        lambda slug, db, **kw: db.get(BaseResume, slug),
    )


# --- the scoping contract -------------------------------------------------

def test_compose_with_none_is_the_whole_kb(db_session):
    _profile(db_session)
    _entity(db_session, "experience", "Data Scientist", "Acme")
    _entity(db_session, "project", "Churn Model")

    data = career_kb.compose_resume_data(db_session)
    assert len(data["experience"]) == 1 and len(data["projects"]) == 1


def test_compose_narrows_to_the_selection(db_session):
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Scientist", "Acme")
    _entity(db_session, "project", "Unrelated Project")

    data = career_kb.compose_resume_data(db_session, entity_ids=[keep.id])
    assert [e["role"] for e in data["experience"]] == ["Data Scientist"]
    assert data["projects"] == []


def test_empty_selection_composes_nothing_not_everything(db_session):
    """`entity_ids=[]` is falsy — a truthy check would return the whole KB."""
    _profile(db_session)
    _entity(db_session, "experience", "Data Scientist", "Acme")

    data = career_kb.compose_resume_data(db_session, entity_ids=[])
    assert data["experience"] == [] and data["projects"] == []
    # ...and the unscoped call still returns everything, unchanged.
    assert len(career_kb.compose_resume_data(db_session)["experience"]) == 1


def test_unknown_entity_ids_are_ignored_not_fatal(db_session):
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Scientist", "Acme")
    data = career_kb.compose_resume_data(db_session, entity_ids=[keep.id, uuid.uuid4()])
    assert len(data["experience"]) == 1


# --- the endpoint ---------------------------------------------------------

def test_from_kb_creates_a_targeted_base(db_session, tmp_path, monkeypatch):
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Engineer", "Acme")
    _entity(db_session, "project", "Left Out")

    body = _client(db_session).post(
        "/api/base-resumes/from-kb",
        json={
            "slug": "de_focus",
            "display_name": "Data Engineering",
            "role_category": "data_engineer",
            "entity_ids": [str(keep.id)],
        },
    ).json()

    assert body["slug"] == "de_focus"
    assert body["role_category"] == "data_engineer"
    assert [e["role"] for e in body["data"]["experience"]] == ["Data Engineer"]
    assert body["data"]["projects"] == []
    # Reused the create pipeline, so the disk file exists (SYSTEM.md §3).
    assert (tmp_path / "de_focus.json").exists()


def test_summary_is_dropped_by_default(db_session, tmp_path, monkeypatch):
    """A whole-career summary on a role-targeted resume is usually wrong;
    blank-and-visible beats plausible-and-wrong."""
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session, summary="Whole-career summary spanning every role.")
    keep = _entity(db_session, "experience", "Data Engineer", "Acme")

    body = _client(db_session).post(
        "/api/base-resumes/from-kb",
        json={"slug": "no_summary", "entity_ids": [str(keep.id)]},
    ).json()
    assert body["data"]["summary"] is None

    body2 = _client(db_session).post(
        "/api/base-resumes/from-kb",
        json={"slug": "with_summary", "entity_ids": [str(keep.id)], "include_summary": True},
    ).json()
    assert "Whole-career" in body2["data"]["summary"]


def test_empty_result_is_422_not_a_contact_only_resume(db_session, tmp_path, monkeypatch):
    """ResumeData requires only `contact`, so a non-matching selection would
    otherwise mint an empty base with no error."""
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session)
    _entity(db_session, "experience", "Data Scientist", "Acme")

    resp = _client(db_session).post(
        "/api/base-resumes/from-kb",
        json={"slug": "empty_one", "entity_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 422
    assert db_session.get(BaseResume, "empty_one") is None


def test_from_kb_enforces_the_same_guards_as_create(db_session, tmp_path, monkeypatch):
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Scientist", "Acme")
    client = _client(db_session)

    assert client.post("/api/base-resumes/from-kb", json={
        "slug": "Bad-Slug", "entity_ids": [str(keep.id)]}).status_code == 400
    assert client.post("/api/base-resumes/from-kb", json={
        "slug": "dupe", "entity_ids": [str(keep.id)]}).status_code == 200
    assert client.post("/api/base-resumes/from-kb", json={
        "slug": "dupe", "entity_ids": [str(keep.id)]}).status_code == 409


def test_from_kb_allocates_slug_past_soft_deleted_tombstones(
    db_session, tmp_path, monkeypatch
):
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Engineer", "Acme")
    client = _client(db_session)

    first = client.post(
        "/api/base-resumes/from-kb",
        json={
            "slug": "data_engineer",
            "role_category": "data_engineer",
            "entity_ids": [str(keep.id)],
        },
    )
    assert first.status_code == 200
    tombstone = db_session.get(BaseResume, "data_engineer")
    tombstone.deleted_at = datetime.now(UTC)
    db_session.commit()

    response = client.post(
        "/api/base-resumes/from-kb",
        json={
            "role_category": "data_engineer",
            "entity_ids": [str(keep.id)],
        },
    )
    assert response.status_code == 200
    assert response.json()["slug"] == "data_engineer_2"


def test_from_kb_auto_slug_requires_role_category(db_session, tmp_path, monkeypatch):
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Engineer", "Acme")

    response = _client(db_session).post(
        "/api/base-resumes/from-kb",
        json={"entity_ids": [str(keep.id)]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "role_category is required when slug is omitted"
    )


def test_skills_arrive_in_full_and_that_is_documented(db_session, tmp_path, monkeypatch):
    """Scope limit, pinned: skills live on KBProfile with no per-entity data to
    filter by, so a narrowed compose still carries the whole union. Narrowing
    them would mean guessing which skill belongs to which entity."""
    _stub_side_effects(monkeypatch, tmp_path)
    _profile(db_session, skills=[{"category": "Core", "items": ["Python", "Airflow", "Figma"]}])
    keep = _entity(db_session, "experience", "Data Engineer", "Acme")

    body = _client(db_session).post(
        "/api/base-resumes/from-kb",
        json={"slug": "skills_full", "entity_ids": [str(keep.id)]},
    ).json()
    assert body["data"]["skills"][0]["items"] == ["Python", "Airflow", "Figma"]
