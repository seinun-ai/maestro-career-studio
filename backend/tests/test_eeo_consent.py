"""EEO standing consent is a typed backend setting: auditable opt-in for
deterministic autofill, never a place for EEO answer values."""

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.main import app
from app.schemas.eeo_consent import EeoConsent
from app.services import eeo_consent


@pytest.fixture
def client(db_session):
    from app.db import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_defaults_are_disabled_with_null_acknowledgement():
    consent = EeoConsent()
    assert consent.enabled is False
    assert consent.acknowledged_at is None
    assert consent.policy_version == eeo_consent.CURRENT_POLICY_VERSION


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        EeoConsent(enabled=True, gender="female")


def test_round_trip_through_setting(db_session):
    saved = eeo_consent.set_consent(
        EeoConsent(
            enabled=True,
            acknowledged_at="2026-07-30T12:00:00+00:00",
            policy_version="1",
        ),
        db_session,
    )
    assert saved.enabled is True
    loaded = eeo_consent.get_consent(db_session)
    assert loaded.enabled is True
    assert loaded.acknowledged_at == "2026-07-30T12:00:00+00:00"
    assert loaded.policy_version == "1"


def test_corrupt_stored_json_reads_as_defaults(db_session):
    from app.services import text_settings

    text_settings.set_text(
        eeo_consent.EEO_CONSENT_KEY,
        eeo_consent.EEO_CONSENT_FILE,
        "not json{",
        db_session,
    )
    assert eeo_consent.get_consent(db_session) == EeoConsent()


def test_settings_get_defaults_then_put_round_trips(client):
    r = client.get("/api/settings/eeo-consent")
    assert r.status_code == 200
    assert r.json() == {
        "key": "eeo_consent",
        "value": {
            "enabled": False,
            # The second permission in the same record: authorizing the
            # extension to tick an application's own agreement boxes. Separate
            # from `enabled` so opting into EEO fill cannot silently also opt
            # into agreeing to terms.
            "consent_forms": False,
            "acknowledged_at": None,
            "policy_version": eeo_consent.CURRENT_POLICY_VERSION,
        },
    }

    r = client.put(
        "/api/settings/eeo-consent",
        json={
            "value": {
                "enabled": True,
                "acknowledged_at": "2026-07-30T18:00:00+00:00",
                "policy_version": "1",
            }
        },
    )
    assert r.status_code == 200
    body = r.json()["value"]
    assert body["enabled"] is True
    assert body["acknowledged_at"] == "2026-07-30T18:00:00+00:00"
    assert body["policy_version"] == "1"
    assert client.get("/api/settings/eeo-consent").json()["value"]["enabled"] is True


def test_settings_put_rejects_eeo_answer_fields(client):
    r = client.put(
        "/api/settings/eeo-consent",
        json={"value": {"enabled": True, "gender": "female"}},
    )
    assert r.status_code == 422


def test_enabling_without_acknowledgement_stamps_server_time(client, monkeypatch):
    monkeypatch.setattr(
        eeo_consent,
        "_now_iso",
        lambda: "2026-07-30T20:00:00+00:00",
    )
    r = client.put(
        "/api/settings/eeo-consent",
        json={"value": {"enabled": True}},
    )
    assert r.status_code == 200
    value = r.json()["value"]
    assert value["enabled"] is True
    assert value["acknowledged_at"] == "2026-07-30T20:00:00+00:00"
    assert value["policy_version"] == eeo_consent.CURRENT_POLICY_VERSION
