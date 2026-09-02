"""POST /api/base-resumes/import — one file, one new base resume, no KB writes.

The onboarding import (`POST /api/kb/import`) always mints a base AND folds
it into the Career KB, named after the file. The base-resume lane is the
user choosing name and role up front and asking for a base only; the parse
half is shared, the KB half is deliberately absent.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from app.models.resume_version import ResumeVersion
from app.routers import base_resumes as router_module
from app.services import kb_consolidation

RESUME = {
    "contact": {"name": "Jordan Sample", "email": "jordan@example.com"},
    "summary": "Data scientist.",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [
        {"company": "Acme", "role": "Senior Data Scientist", "start_date": "2021-03",
         "bullets": ["Built models."]}
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


@pytest.fixture
def client(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(router_module.base_resume_data.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(router_module.base_resume_render, "render_base_resume", lambda slug, db, **kw: None)
    monkeypatch.setattr(kb_consolidation, "prefetch_prompts", lambda s: None)
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _fake_parse(monkeypatch, payload=RESUME, warnings=(), seen=None):
    def fake(session, text):
        if seen is not None:
            seen.append(text)
        return json.loads(json.dumps(payload)), list(warnings)
    monkeypatch.setattr(kb_consolidation, "parse_resume_text", fake)


def _upload(name, data: bytes, mime="text/plain"):
    return {"file": (name, io.BytesIO(data), mime)}


def test_a_text_resume_becomes_a_base_named_by_the_user(client, db_session, monkeypatch):
    seen = []
    _fake_parse(monkeypatch, seen=seen)
    r = client.post(
        "/api/base-resumes/import",
        files=_upload("old_resume.txt", b"Jordan Sample\nData scientist"),
        data={"display_name": "ML Engineer", "role_category": "data_scientist"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "ml_engineer"
    assert body["display_name"] == "ML Engineer"
    assert body["role_category"] == "data_scientist"
    assert body["data"]["contact"]["name"] == "Jordan Sample"
    assert body["parse_warnings"] == []
    assert seen == ["Jordan Sample\nData scientist"]
    # The standard create pipeline ran: a version row records the birth.
    versions = db_session.query(ResumeVersion).filter_by(resume_key="ml_engineer").all()
    assert [v.source for v in versions] == ["create"]


def test_the_career_kb_is_not_touched(client, db_session, monkeypatch):
    _fake_parse(monkeypatch)
    r = client.post("/api/base-resumes/import", files=_upload("r.txt", b"text"))
    assert r.status_code == 200, r.text
    assert db_session.query(KBEntity).count() == 0
    assert db_session.query(KBPoint).count() == 0
    assert db_session.query(KBPortLog).count() == 0


def test_the_file_stem_names_the_resume_when_the_user_does_not(client, monkeypatch):
    _fake_parse(monkeypatch)
    r = client.post("/api/base-resumes/import", files=_upload("Jordan_Sample_2026.txt", b"text"))
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Jordan Sample 2026"
    assert r.json()["slug"] == "jordan_sample_2026"


def test_a_derived_slug_never_collides(client, db_session, monkeypatch):
    _fake_parse(monkeypatch)
    db_session.add(BaseResume(slug="ml_engineer", display_name="x", data_json=RESUME))
    db_session.commit()
    r = client.post("/api/base-resumes/import", files=_upload("r.txt", b"t"),
                    data={"display_name": "ML Engineer"})
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "ml_engineer_2"


def test_an_explicit_slug_that_exists_is_a_409(client, db_session, monkeypatch):
    _fake_parse(monkeypatch)
    db_session.add(BaseResume(slug="taken", display_name="x", data_json=RESUME))
    db_session.commit()
    r = client.post("/api/base-resumes/import", files=_upload("r.txt", b"t"), data={"slug": "taken"})
    assert r.status_code == 409


def test_json_is_validated_without_the_model(client, monkeypatch):
    called = []
    monkeypatch.setattr(kb_consolidation, "parse_resume_text",
                        lambda *a, **k: called.append(1))
    r = client.post("/api/base-resumes/import",
                    files=_upload("base.json", json.dumps(RESUME).encode(), "application/json"))
    assert r.status_code == 200, r.text
    assert called == []
    assert r.json()["data"]["experience"][0]["company"] == "Acme"


def test_invalid_json_is_a_422(client):
    r = client.post("/api/base-resumes/import",
                    files=_upload("base.json", b'{"contact": {}}', "application/json"))
    assert r.status_code == 422


def test_an_unsupported_file_type_is_a_422(client):
    r = client.post("/api/base-resumes/import",
                    files=_upload("resume.xyz", b"\x00\x01", "application/octet-stream"))
    assert r.status_code == 422
    assert "Unsupported" in r.json()["detail"]


def test_a_provider_outage_is_a_502_not_a_bad_file(client, monkeypatch):
    def down(session, text):
        raise RuntimeError("resume parse LLM call failed: timeout")
    monkeypatch.setattr(kb_consolidation, "parse_resume_text", down)
    r = client.post("/api/base-resumes/import", files=_upload("r.txt", b"t"))
    assert r.status_code == 502


def test_salvage_warnings_reach_the_client(client, monkeypatch):
    _fake_parse(monkeypatch, warnings=["dropped 1 unparseable projects item(s)"])
    r = client.post("/api/base-resumes/import", files=_upload("r.txt", b"t"))
    assert r.status_code == 200
    assert r.json()["parse_warnings"] == ["dropped 1 unparseable projects item(s)"]


def test_the_size_cap_is_a_413(client):
    r = client.post("/api/base-resumes/import",
                    files=_upload("r.txt", b"x" * (router_module.IMPORT_MAX_BYTES + 1)))
    assert r.status_code == 413
