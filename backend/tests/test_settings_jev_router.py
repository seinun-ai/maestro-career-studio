import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import jev
from app.services.llm import LLMProviderError


@pytest.fixture
def client(db_session):
    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_reports_defaults_and_never_the_key(client):
    body = client.get("/api/settings/jev").json()
    assert body == {"api_key_configured": False, "base_url": "https://openrouter.ai/api",
                    "model": "typesafe/jev-1.13", "engine": "fast"}


def test_put_is_a_patch_and_the_key_is_write_only(client):
    body = client.put("/api/settings/jev", json={"api_key": "sk-or-test"}).json()
    assert body["api_key_configured"] is True
    assert "sk-or-test" not in str(body)
    body = client.put("/api/settings/jev", json={"engine": "jev"}).json()
    assert body["engine"] == "jev" and body["api_key_configured"] is True


def test_switching_to_jev_without_a_key_is_a_400(client):
    assert client.put("/api/settings/jev", json={"engine": "jev"}).status_code == 400


def test_a_non_http_base_url_is_a_400(client):
    assert client.put("/api/settings/jev", json={"base_url": "ftp://x"}).status_code == 400


def test_probe_reports_ok(client, monkeypatch):
    monkeypatch.setattr(jev, "probe", lambda session=None: None)
    assert client.post("/api/settings/jev/probe").json() == {"ok": True, "error": None}


def test_probe_reports_failure_without_a_502(client, monkeypatch):
    def refused(session=None):
        raise LLMProviderError("Jev refused your API key.")

    monkeypatch.setattr(jev, "probe", refused)
    resp = client.post("/api/settings/jev/probe")
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error": "Jev refused your API key."}
