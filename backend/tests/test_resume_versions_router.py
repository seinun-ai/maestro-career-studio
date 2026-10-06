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


# --- if_latest: Undo after a health question pass (health check v3, Task 12) ---------------------


def test_restore_if_latest_mismatch_is_409_and_restores_nothing(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    row = _seed_with_versions(db_session)

    # The pass wrote on top of Version 1 and asks to undo only if its write is still the latest
    # (Version 2 + 1 = 3). Nothing wrote Version 3, so the latest is 2: refused.
    resp = client.post("/api/resume-versions/base/ds/1/restore?if_latest=3")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "resume changed since"

    db_session.rollback()
    db_session.refresh(row)
    assert row.data_json["summary"] == "Better summary"
    assert [v["version_number"] for v in client.get("/api/resume-versions/base/ds").json()] == [2, 1]


def test_restore_if_latest_match_restores(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    row = _seed_with_versions(db_session)

    resp = client.post("/api/resume-versions/base/ds/1/restore?if_latest=2")
    assert resp.status_code == 200
    assert resp.json()["version_number"] == 3
    assert resp.json()["source"] == "restore"

    db_session.refresh(row)
    assert row.data_json["summary"] == "Summary"


def test_restore_without_if_latest_restores_as_before(db_session, monkeypatch, tmp_path):
    client = _client(db_session, monkeypatch, tmp_path)
    row = _seed_with_versions(db_session)
    # Version history's Restore passes nothing: an older latest is no reason to refuse.
    extra = deepcopy(SAMPLE_DATA)
    extra["summary"] = "Third"
    row.data_json = extra
    record_version(db_session, "base", "ds", extra, source="form_edit")
    db_session.commit()

    resp = client.post("/api/resume-versions/base/ds/1/restore")
    assert resp.status_code == 200
    assert resp.json()["version_number"] == 4
    db_session.refresh(row)
    assert row.data_json["summary"] == "Summary"


def test_restore_if_latest_checks_under_the_write_lock(db_session, monkeypatch, tmp_path):
    """The check and the restore are one transaction: the write lock is taken before the latest
    version is read, so no write can land between the check and the restore."""
    from app.routers import resume_versions as router_module
    from app.services import resume_versions as service_module

    client = _client(db_session, monkeypatch, tmp_path)
    _seed_with_versions(db_session)
    calls: list[str] = []
    monkeypatch.setattr(router_module, "begin_write", lambda db: calls.append("lock"))
    real_latest = service_module.latest_version

    def _latest(db, kind, key):
        calls.append("latest")
        return real_latest(db, kind, key)

    monkeypatch.setattr(service_module, "latest_version", _latest)

    assert client.post("/api/resume-versions/base/ds/1/restore?if_latest=2").status_code == 200
    assert calls[:2] == ["lock", "latest"]

    calls.clear()
    assert client.post("/api/resume-versions/base/ds/1/restore").status_code == 200
    assert "lock" not in calls
