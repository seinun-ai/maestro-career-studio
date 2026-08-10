"""Slice 1 invariants for base_resumes.role_category.

The design's core promise is that the field can never be NULL on any write path
(a REST-only validator would not hold — the documented onboarding path drops
JSON into base_resumes/ and reaches seeding.py without touching the API), while
"unknown" stays a legitimate, visible state.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.services import role_categories, seeding

SAMPLE = {
    "contact": {"name": "Sample Person", "email": "sample@example.com"},
    "summary": "Summary",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _client(db_session) -> TestClient:
    app.dependency_overrides[get_db] = _override_db(db_session)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


# --- the null invariant, one test per insert site -------------------------

def test_insert_site_1_rest_create_defaults_to_unknown(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        "app.routers.base_resumes.base_resume_render.render_base_resume",
        lambda slug, db, **kw: db.get(BaseResume, slug),
    )
    body = _client(db_session).post(
        "/api/base-resumes", json={"slug": "no_role", "display_name": "No Role", "data": SAMPLE}
    ).json()
    assert body["role_category"] == "unknown"
    assert db_session.get(BaseResume, "no_role").role_category == "unknown"


def test_insert_site_2_duplicate_inherits_role(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        "app.routers.base_resumes.base_resume_render.render_base_resume",
        lambda slug, db, **kw: db.get(BaseResume, slug),
    )
    db_session.add(
        BaseResume(slug="src", display_name="Src", data_json=SAMPLE, role_category="bi_developer")
    )
    db_session.commit()
    body = _client(db_session).post(
        "/api/base-resumes/src/duplicate", json={"new_slug": "clone"}
    ).json()
    assert body["role_category"] == "bi_developer"


def test_insert_site_3_seeding_declares_only_what_is_certain(db_session, tmp_path, monkeypatch):
    """A slug that IS a category resolves; anything else stays unknown.

    This is the normative path: the migration backfill matches zero rows on a
    fresh install because migrations run before seeding.
    """
    (tmp_path / "data_engineer.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    (tmp_path / "my_custom_resume.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)

    seeding.seed_base_resumes(db_session)

    assert db_session.get(BaseResume, "data_engineer").role_category == "data_engineer"
    assert db_session.get(BaseResume, "my_custom_resume").role_category == "unknown"


def test_no_write_path_can_produce_null(db_session):
    """The column is NOT NULL; an explicit None still lands on the default."""
    col = sa_inspect(BaseResume).columns["role_category"]
    assert col.nullable is False
    assert col.server_default is not None

    db_session.add(BaseResume(slug="explicit_none", data_json=SAMPLE, role_category=None))
    db_session.commit()
    assert db_session.get(BaseResume, "explicit_none").role_category == "unknown"


# --- human-supplied values are validated, not coerced ---------------------

def test_explicit_bad_role_is_422_not_silently_other(db_session):
    """normalize() maps typos to "other"; a person gets a 422 instead.

    Otherwise "data_scientistt" is indistinguishable from a deliberate "Other" —
    the silent plausible answer the design forbids.
    """
    resp = _client(db_session).post(
        "/api/base-resumes",
        json={"slug": "typo", "data": SAMPLE, "role_category": "data_scientistt"},
    )
    assert resp.status_code == 422
    assert "data_scientistt" in resp.json()["detail"]
    assert role_categories.normalize("data_scientistt") == "other"  # the contrast


# --- PATCH /identity ------------------------------------------------------

def test_patch_identity_sets_role_without_touching_the_document(db_session):
    """Declaring a role must not re-render, re-version, or rewrite the JSON."""
    db_session.add(
        BaseResume(
            slug="declare_me", data_json=SAMPLE, role_category="unknown",
            pdf_path="/kept.pdf", pdf_pages=2,
        )
    )
    db_session.commit()

    body = _client(db_session).patch(
        "/api/base-resumes/declare_me/identity", json={"role_category": "data_analyst"}
    ).json()

    assert body["role_category"] == "data_analyst"
    row = db_session.get(BaseResume, "declare_me")
    assert row.pdf_path == "/kept.pdf" and row.pdf_pages == 2  # artifacts untouched


def test_patch_identity_explicit_null_clears_back_to_unknown(db_session):
    db_session.add(BaseResume(slug="clearme", data_json=SAMPLE, role_category="data_analyst"))
    db_session.commit()
    body = _client(db_session).patch(
        "/api/base-resumes/clearme/identity", json={"role_category": None}
    ).json()
    assert body["role_category"] == "unknown"


# --- vocabulary drift guard ----------------------------------------------

def test_role_categories_endpoint_matches_the_vocabulary(db_session):
    rows = _client(db_session).get("/api/role-categories").json()
    keys = [r["key"] for r in rows]
    assert keys == role_categories.all_keys()
    assert [r["key"] for r in rows if r["reserved"]] == ["other", "unknown"]


@pytest.mark.parametrize("key", role_categories.all_keys())
def test_every_vocabulary_key_is_storable(db_session, key):
    """Pins the column's accepted values to the YAML, mirroring the family-key
    drift guard added when role categories became data."""
    db_session.add(BaseResume(slug=f"v_{key}", data_json=SAMPLE, role_category=key))
    db_session.commit()
    assert db_session.get(BaseResume, f"v_{key}").role_category == key
