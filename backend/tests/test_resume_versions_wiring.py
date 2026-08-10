"""Every resume write path must record a version through record_version."""

import uuid
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.routers import base_resumes as base_resumes_module
from app.services import base_resume_render
from app.services.resume_versions import get_versions

SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Summary",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2020",
            "enabled": True,
            "bullets": ["Built pipeline."],
        }
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _client(db_session, monkeypatch, tmp_path: Path) -> TestClient:
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    monkeypatch.setattr(base_resumes_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        base_resume_render, "render_base_resume", lambda slug, db, template_id=None: None
    )
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _seed_base(db_session, slug="ds"):
    row = BaseResume(slug=slug, display_name="DS", data_json=deepcopy(SAMPLE_DATA))
    db_session.add(row)
    db_session.commit()
    return row


def _seed_job(db_session):
    job = Job(id=uuid.uuid4(), raw_text="jd", raw_text_hash=uuid.uuid4().hex)
    db_session.add(job)
    db_session.commit()
    return job


def test_base_resume_create_put_and_edits_record_versions(
    db_session, monkeypatch, tmp_path
):
    client = _client(db_session, monkeypatch, tmp_path)

    resp = client.post(
        "/api/base-resumes", json={"slug": "ml_eng", "display_name": "ML", "data": SAMPLE_DATA}
    )
    assert resp.status_code == 200
    versions = get_versions(db_session, "base", "ml_eng")
    assert [v.source for v in versions] == ["create"]

    changed = deepcopy(SAMPLE_DATA)
    changed["summary"] = "New summary"
    assert client.put("/api/base-resumes/ml_eng", json={"data": changed}).status_code == 200

    ops = {"ops": [{"kind": "add_bullet", "section": "experience", "index": 0, "text": "Did X."}]}
    assert client.patch("/api/base-resumes/ml_eng/edits", json=ops).status_code == 200

    sources = [v.source for v in get_versions(db_session, "base", "ml_eng")]
    assert sources == ["edit_ops", "form_edit", "create"]


def test_base_resume_put_same_data_dedupes(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    _seed_base(db_session)
    client.put("/api/base-resumes/ds", json={"data": SAMPLE_DATA})
    client.put("/api/base-resumes/ds", json={"data": SAMPLE_DATA})
    # Seeded row had no create version; first PUT records one, second dedupes.
    assert len(get_versions(db_session, "base", "ds")) == 1


def test_duplicate_records_create_version_for_clone(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    _seed_base(db_session)
    resp = client.post(
        "/api/base-resumes/ds/duplicate", json={"new_slug": "ds_two", "new_display_name": "DS2"}
    )
    assert resp.status_code == 200
    assert [v.source for v in get_versions(db_session, "base", "ds_two")] == ["create"]


def test_application_edits_and_materialize_record_versions(db_session, monkeypatch, tmp_path):
    import json

    client = _client(db_session, monkeypatch, tmp_path)
    _seed_base(db_session)
    # materialize-resume loads base data from disk, not the DB row
    (tmp_path / "ds.json").write_text(json.dumps(SAMPLE_DATA), encoding="utf-8")
    job = _seed_job(db_session)
    application = Application(
        job_id=job.id, base_resume="ds", status="draft", customized_json=deepcopy(SAMPLE_DATA)
    )
    db_session.add(application)
    db_session.commit()
    app_id = str(application.id)

    ops = {
        "ops": [
            {
                "kind": "replace_bullet",
                "section": "experience",
                "index": 0,
                "bullet_index": 0,
                "value": "Rewrote pipeline.",
            }
        ]
    }
    assert client.patch(f"/api/applications/{app_id}/edits", json=ops).status_code == 200
    assert [v.source for v in get_versions(db_session, "application", app_id)] == ["edit_ops"]

    assert client.post(f"/api/applications/{app_id}/materialize-resume").status_code == 200
    sources = [v.source for v in get_versions(db_session, "application", app_id)]
    assert sources[0] == "import"


def test_edits_succeed_even_when_pdf_render_fails(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    _seed_base(db_session)

    def boom(slug, db, template_id=None):
        raise RuntimeError("pdflatex exploded")

    monkeypatch.setattr(base_resume_render, "render_base_resume", boom)

    ops = {"ops": [{"kind": "replace_summary", "value": "Still saved."}]}
    resp = client.patch("/api/base-resumes/ds/edits", json=ops)
    assert resp.status_code == 200
    assert resp.json()["data"]["summary"] == "Still saved."
    assert [v.source for v in get_versions(db_session, "base", "ds")][0] == "edit_ops"
