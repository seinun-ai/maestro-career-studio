import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_version_reports_dev_when_unset(client, monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    body = client.get("/api/version").json()
    assert body["version"] == "dev"


def test_version_reads_app_version_env(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "v0.2.0")
    body = client.get("/api/version").json()
    assert body["version"] == "v0.2.0"


def test_version_reports_live_schema_revision(client):
    """schema_revision must be the real alembic head, not a constant: it is the
    first thing worth knowing when a user reports a post-update failure."""
    body = client.get("/api/version").json()
    assert body["schema_revision"]
    assert body["schema_revision"] != "unknown"
