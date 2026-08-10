from copy import deepcopy

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.routers import base_resumes as base_resumes_module
from app.services import base_resume_render
from app.services.resume_versions import record_version

SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Summary",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _client(db_session, monkeypatch, tmp_path) -> TestClient:
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    monkeypatch.setattr(base_resumes_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        base_resume_render, "render_base_resume", lambda slug, db, template_id=None: None
    )
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _seed_with_versions(db_session):
    row = BaseResume(slug="ds", display_name="DS", data_json=deepcopy(SAMPLE_DATA))
    db_session.add(row)
    record_version(db_session, "base", "ds", SAMPLE_DATA, source="create")
    v2_data = deepcopy(SAMPLE_DATA)
    v2_data["summary"] = "Better summary"
    row.data_json = v2_data
    record_version(db_session, "base", "ds", v2_data, source="form_edit")
    db_session.commit()
    return row


def test_list_versions_newest_first(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    _seed_with_versions(db_session)
    resp = client.get("/api/resume-versions/base/ds")
    assert resp.status_code == 200
    body = resp.json()
    assert [v["version_number"] for v in body] == [2, 1]
    assert body[0]["source"] == "form_edit"


def test_get_version_detail_includes_snapshot_and_diff(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    _seed_with_versions(db_session)
    resp = client.get("/api/resume-versions/base/ds/2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot"]["summary"] == "Better summary"
    assert any(c["section"] == "summary" for c in body["diff"])

    assert client.get("/api/resume-versions/base/ds/9").status_code == 404


def test_restore_updates_live_row_and_appends_version(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    row = _seed_with_versions(db_session)

    resp = client.post("/api/resume-versions/base/ds/1/restore")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_number"] == 3
    assert body["source"] == "restore"

    db_session.refresh(row)
    assert row.data_json["summary"] == "Summary"
    assert len(client.get("/api/resume-versions/base/ds").json()) == 3


def test_label_patch(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    _seed_with_versions(db_session)
    resp = client.patch("/api/resume-versions/base/ds/2", json={"label": "Sent to Google"})
    assert resp.status_code == 200
    assert resp.json()["label"] == "Sent to Google"
    resp = client.patch("/api/resume-versions/base/ds/2", json={"label": ""})
    assert resp.json()["label"] is None


def test_invalid_kind_rejected(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    assert client.get("/api/resume-versions/banana/ds").status_code == 422
