"""EEO standing consent is a typed backend setting: auditable opt-in for
deterministic autofill, never a place for EEO answer values."""

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.config import settings
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
            # Derived on read: an agreement given under an older policy.
            "consent_forms_lapsed": False,
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


# --- Policy v2: the agreement permission must be given again -------------------
#
# Policy 2 widened `consent_forms` from "an application's own agreement boxes"
# to every field (signatures, initials, typed-name attestations, salary, IDs).
# An agreement given under policy 1 covered less, so it must not silently
# carry over. The diversity opt-in (`enabled`) did not change and stays valid.


def _context(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    r = client.get("/api/autofill/context")
    assert r.status_code == 200
    return r.json()


def test_policy_version_is_two():
    assert eeo_consent.CURRENT_POLICY_VERSION == "2"
    assert EeoConsent().policy_version == "2"


def test_a_policy_one_agreement_is_not_granted_where_it_is_served(
    client, db_session, tmp_path, monkeypatch
):
    eeo_consent.set_consent(
        EeoConsent(
            enabled=False,
            consent_forms=True,
            acknowledged_at="2026-09-01T12:00:00+00:00",
            policy_version="1",
        ),
        db_session,
    )
    # The extension's only source for the permission.
    served = _context(client, tmp_path, monkeypatch)["eeo_consent"]
    assert served["consent_forms"] is False
    assert served["consent_forms_lapsed"] is True
    # The web app's switch reads the same answer, so it shows OFF with a note.
    setting = client.get("/api/settings/eeo-consent").json()["value"]
    assert setting["consent_forms"] is False
    assert setting["consent_forms_lapsed"] is True
    assert eeo_consent.get_consent(db_session).consent_forms is False
    assert eeo_consent.peek_consent(db_session).consent_forms is False


@pytest.mark.parametrize("version", ["", "0", "one", "1.5"])
def test_an_unreadable_policy_version_fails_closed(db_session, version):
    eeo_consent.set_consent(
        EeoConsent(
            consent_forms=True,
            acknowledged_at="2026-09-01T12:00:00+00:00",
            policy_version=version,
        ),
        db_session,
    )
    assert eeo_consent.get_consent(db_session).consent_forms is False


def test_echoing_an_old_agreement_back_does_not_grant_it(client, db_session):
    """A client that sends back the policy-1 stamp has not agreed again."""
    r = client.put(
        "/api/settings/eeo-consent",
        json={
            "value": {
                "consent_forms": True,
                "acknowledged_at": "2026-09-01T12:00:00+00:00",
                "policy_version": "1",
            }
        },
    )
    assert r.status_code == 200
    assert r.json()["value"]["consent_forms"] is False
    assert r.json()["value"]["consent_forms_lapsed"] is True


def test_the_lapse_is_derived_never_taken_from_a_client(client):
    r = client.put(
        "/api/settings/eeo-consent",
        json={"value": {"consent_forms_lapsed": True}},
    )
    assert r.status_code == 200
    assert r.json()["value"]["consent_forms_lapsed"] is False
    assert (
        client.get("/api/settings/eeo-consent").json()["value"]["consent_forms_lapsed"]
        is False
    )


def test_agreeing_again_records_policy_two_and_grants(
    client, db_session, tmp_path, monkeypatch
):
    eeo_consent.set_consent(
        EeoConsent(
            consent_forms=True,
            acknowledged_at="2026-09-01T12:00:00+00:00",
            policy_version="1",
        ),
        db_session,
    )
    monkeypatch.setattr(eeo_consent, "_now_iso", lambda: "2026-09-26T09:00:00+00:00")
    # What the web app's switch sends on a yes: a null stamp, so the server
    # records the time and the policy the user just agreed to.
    r = client.put(
        "/api/settings/eeo-consent",
        json={
            "value": {
                "consent_forms": True,
                "acknowledged_at": None,
                "policy_version": "1",
            }
        },
    )
    value = r.json()["value"]
    assert value["consent_forms"] is True
    assert value["consent_forms_lapsed"] is False
    assert value["policy_version"] == "2"
    assert value["acknowledged_at"] == "2026-09-26T09:00:00+00:00"
    served = _context(client, tmp_path, monkeypatch)["eeo_consent"]
    assert served["consent_forms"] is True
    assert served["consent_forms_lapsed"] is False


def test_a_policy_one_diversity_opt_in_stays_valid(
    client, db_session, tmp_path, monkeypatch
):
    """Policy 2 changed nothing the diversity opt-in covers, so no re-consent."""
    from app.services import autofill_profile

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"eeo": {"gender": "female"}}, db_session)
    eeo_consent.set_consent(
        EeoConsent(
            enabled=True,
            consent_forms=True,
            acknowledged_at="2026-09-01T12:00:00+00:00",
            policy_version="1",
        ),
        db_session,
    )
    body = _context(client, tmp_path, monkeypatch)
    assert body["eeo_consent"]["enabled"] is True
    assert body["eeo_consent"]["consent_forms"] is False
    assert body["profile"]["eeo"]["gender"] == "female"
    assert eeo_consent.disclosable_profile(db_session)["eeo"]["gender"] == "female"
