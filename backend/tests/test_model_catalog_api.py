"""Router coverage for model catalog sync / add / remove."""

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.routers import settings
from app.services import llm


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def test_openai_info_includes_source_on_options(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/settings/openai").json()
    finally:
        app.dependency_overrides.clear()

    assert all(opt["source"] == "seed" for opt in body["model_options"])
    assert "gemini-3.7-flash" in {opt["id"] for opt in body["model_options"]}


def test_add_and_remove_catalog_model(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        added = client.post(
            "/api/settings/openai/models",
            json={"id": "gpt-4.5-preview", "provider": "openai", "label": "4.5"},
        )
        assert added.status_code == 200
        ids = {opt["id"] for opt in added.json()["model_options"]}
        assert "gpt-4.5-preview" in ids
        extra = next(
            opt for opt in added.json()["model_options"] if opt["id"] == "gpt-4.5-preview"
        )
        assert extra["source"] == "extra"

        removed = client.delete("/api/settings/openai/models/gpt-4.5-preview")
        assert removed.status_code == 200
        assert "gpt-4.5-preview" not in {
            opt["id"] for opt in removed.json()["model_options"]
        }
    finally:
        app.dependency_overrides.clear()


def test_remove_in_use_returns_400(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        client.post(
            "/api/settings/openai/models",
            json={"id": "gpt-custom", "provider": "openai"},
        )
        client.put(
            "/api/settings/openai",
            json={
                "fast_model": "gpt-custom",
                "smart_model": "gpt-5.6-luna",
                "chat_model": "gpt-5.6-luna",
            },
        )
        resp = client.delete("/api/settings/openai/models/gpt-custom")
        assert resp.status_code == 400
        assert "in use" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_sync_openai_marks_in_catalog(db_session, monkeypatch):
    def fake_list():
        return [
            {"id": "gpt-5.6-luna", "label": "gpt-5.6-luna", "provider": "openai"},
            {"id": "gpt-brand-new", "label": "gpt-brand-new", "provider": "openai"},
            {"id": "text-embedding-3-small", "label": "emb", "provider": "openai"},
        ]

    monkeypatch.setattr(llm, "list_openai_models", fake_list)
    # list_openai_models already filters embeddings in production; the fake
    # includes one to prove the router does not re-filter — but our real
    # helper filters. Override after filter by patching the router import.
    monkeypatch.setattr(settings.llm, "list_openai_models", fake_list)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).post(
            "/api/settings/openai/sync",
            json={"provider": "openai"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()["models"]}
    assert by_id["gpt-5.6-luna"]["in_catalog"] is True
    assert by_id["gpt-brand-new"]["in_catalog"] is False


def test_sync_gemini_502_on_provider_error(db_session, monkeypatch):
    def boom():
        raise llm.LLMProviderError("no key")

    monkeypatch.setattr(settings.llm, "list_gemini_models", boom)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).post(
            "/api/settings/openai/sync",
            json={"provider": "gemini"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 502
    assert "no key" in resp.json()["detail"]


def test_openai_model_filter_skips_embeddings():
    assert llm._openai_model_is_chatlike("gpt-4o") is True
    assert llm._openai_model_is_chatlike("text-embedding-3-large") is False
    assert llm._openai_model_is_chatlike("whisper-1") is False
