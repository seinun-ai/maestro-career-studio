from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.services.exports import CareerExportResult


FIXED = CareerExportResult(
    markdown="# Career Profile\n",
    content_hash="abc123",
    generated_at=datetime(2026, 8, 3, 15, 30, tzinfo=UTC),
    cached=False,
)


def _client(db_session, *, raise_server_exceptions=True):
    from app.db import get_db
    from app.main import app
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app, raise_server_exceptions=raise_server_exceptions), app


def test_list_exports_returns_one_career_row(db_session, monkeypatch):
    from app.routers import exports as router
    monkeypatch.setattr(router.career_exports, "get_career_export", lambda _db, force=False: FIXED)
    client, app = _client(db_session)
    try:
        response = client.get("/api/exports")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == [{
        "name": "career",
        "filename": "career.md",
        "generated_at": "2026-08-03T15:30:00Z",
        "content_hash": "abc123",
        "download_url": "/api/exports/career",
    }]


def test_download_returns_markdown_attachment(db_session, monkeypatch):
    from app.routers import exports as router
    monkeypatch.setattr(router.career_exports, "get_career_export", lambda _db, force=False: FIXED)
    client, app = _client(db_session)
    try:
        response = client.get("/api/exports/career")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.text == "# Career Profile\n"
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="career.md"'
    assert response.headers["x-content-sha256"] == "abc123"


def test_refresh_forces_render_and_returns_metadata(db_session, monkeypatch):
    from app.routers import exports as router
    calls = []
    monkeypatch.setattr(router.career_exports, "get_career_export", lambda _db, force=False: calls.append(force) or FIXED)
    client, app = _client(db_session)
    try:
        response = client.post("/api/exports/career/refresh")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert calls == [True]
    assert response.json()["filename"] == "career.md"


def test_download_does_not_mask_composition_failure(db_session, monkeypatch):
    from app.routers import exports as router
    monkeypatch.setattr(router.career_exports, "get_career_export", lambda _db, force=False: (_ for _ in ()).throw(RuntimeError("compose failed")))
    client, app = _client(db_session, raise_server_exceptions=False)
    try:
        response = client.get("/api/exports/career")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500

