from fastapi.testclient import TestClient

from app.main import app
from app.schemas.auto_apply import AutoApplySettings

client = TestClient(app)


def test_defaults_and_roundtrip(db_session):
    r = client.get("/api/settings/auto-apply")
    assert r.status_code == 200
    assert r.json()["value"] == AutoApplySettings().model_dump()

    r = client.put("/api/settings/auto-apply", json={"value": {
        "cooldown_days": 14, "company_blocklist": ["BadCo"]}})
    assert r.status_code == 200
    assert client.get("/api/settings/auto-apply").json()["value"]["cooldown_days"] == 14


def test_invalid_payload_is_422(db_session):
    assert client.put("/api/settings/auto-apply",
                      json={"value": {"cooldown_days": "soon"}}).status_code == 422
