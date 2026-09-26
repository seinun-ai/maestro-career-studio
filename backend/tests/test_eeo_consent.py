"""EEO standing consent is a typed backend setting: auditable opt-in for
deterministic autofill, never a place for EEO answer values."""

import json

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
    eeo_consent.EEO_CONSENT.set(
        EeoConsent(
            enabled=True,
            acknowledged_at="2026-07-30T12:00:00+00:00",
            policy_version="1",
        ),
        db_session,
    )
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


def test_settings_get_defaults_then_put_round_trips(client, monkeypatch):
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

    # The server owns the audit stamp: a yes is stamped with the server's time
    # and the current policy, whatever the client says it is.
    monkeypatch.setattr(eeo_consent, "_now_iso", lambda: "2026-09-26T10:00:00+00:00")
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
    assert body["acknowledged_at"] == "2026-09-26T10:00:00+00:00"
    assert body["policy_version"] == eeo_consent.CURRENT_POLICY_VERSION
    assert "agreed_policy" not in body
    assert client.get("/api/settings/eeo-consent").json()["value"] == body


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
#
# Historical records are seeded through the RAW writer: `set_consent` owns the
# stamp and would never store one of them.

_OLD_STAMP = "2026-09-01T12:00:00+00:00"


def _seed(db_session, **fields):
    record = {"acknowledged_at": _OLD_STAMP, "policy_version": "1", **fields}
    eeo_consent.EEO_CONSENT.set(EeoConsent(**record), db_session)


def _put(client, **value):
    r = client.put("/api/settings/eeo-consent", json={"value": value})
    assert r.status_code == 200
    return r.json()["value"]


def _stored(db_session):
    """The record as written, before the read-side lapse."""
    from app.services import text_settings

    return json.loads(
        text_settings.peek_text(
            eeo_consent.EEO_CONSENT_KEY, eeo_consent.EEO_CONSENT_FILE, db_session
        )
    )


def _context(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    r = client.get("/api/autofill/context")
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def now(monkeypatch):
    stamp = "2026-09-26T09:00:00+00:00"
    monkeypatch.setattr(eeo_consent, "_now_iso", lambda: stamp)
    return stamp


def test_policy_version_is_two():
    assert eeo_consent.CURRENT_POLICY_VERSION == "2"
    assert EeoConsent().policy_version == "2"


def test_a_policy_one_agreement_is_not_granted_where_it_is_served(
    client, db_session, tmp_path, monkeypatch
):
    _seed(db_session, consent_forms=True)
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


@pytest.mark.parametrize("version", ["", "one", "1.5", "\u00b2", " 2"])
def test_an_unreadable_policy_version_fails_closed(db_session, version):
    _seed(db_session, consent_forms=True, policy_version=version)
    assert eeo_consent.get_consent(db_session).consent_forms is False


@pytest.mark.parametrize(
    ("version", "granted"), [("0", False), ("1", False), ("2", True), ("10", True)]
)
def test_the_policy_floor_compares_numbers(db_session, version, granted):
    _seed(db_session, consent_forms=True, policy_version=version)
    assert eeo_consent.get_consent(db_session).consent_forms is granted


def test_echoing_an_old_agreement_back_does_not_grant_it(client, db_session):
    """A client that sends back the policy-1 stamp has not agreed again: the
    permission is held at the served value (off), and the stamp is kept."""
    _seed(db_session, consent_forms=True)
    value = _put(client, consent_forms=True, acknowledged_at=_OLD_STAMP, policy_version="1")
    assert value["consent_forms"] is False
    assert value["consent_forms_lapsed"] is False
    assert value["acknowledged_at"] == _OLD_STAMP
    assert value["policy_version"] == "1"
    assert _stored(db_session)["consent_forms"] is False


def test_a_client_cannot_claim_the_current_policy(client, db_session):
    """I-1: once the version decides a grant, it cannot come from the client."""
    _seed(db_session, consent_forms=True)
    value = _put(client, consent_forms=True, acknowledged_at=_OLD_STAMP, policy_version="2")
    assert value["consent_forms"] is False
    assert value["policy_version"] == "1"
    stored = _stored(db_session)
    assert stored["consent_forms"] is False
    assert stored["policy_version"] == "1"


def test_a_grant_carrying_a_stamp_is_held(client, db_session):
    """A yes is a null stamp; one that arrives stamped is not a yes."""
    value = _put(
        client, consent_forms=True, acknowledged_at=_OLD_STAMP,
        policy_version="2", agreed_policy="2",
    )
    assert value["consent_forms"] is False
    assert value["acknowledged_at"] is None


def test_an_agreement_yes_without_the_policy_it_agreed_to_is_held(client, db_session, now):
    """An old tab never sends `agreed_policy`, so its yes cannot re-grant under
    the old wording. Held, never refused."""
    _seed(db_session, consent_forms=True)
    value = _put(client, consent_forms=True, acknowledged_at=None, policy_version="1")
    assert value["consent_forms"] is False
    assert value["acknowledged_at"] == _OLD_STAMP
    assert _stored(db_session)["consent_forms"] is False


def test_an_old_tabs_diversity_yes_leaves_the_agreement_off(client, db_session, now):
    """I-2: a tab loaded before the upgrade still shows the agreement ON and
    sends it back with its diversity yes. The diversity yes goes through and is
    stamped; the agreement nobody re-read stays off."""
    _seed(db_session, enabled=False, consent_forms=True)
    value = _put(
        client, enabled=True, consent_forms=True, acknowledged_at=None, policy_version="1"
    )
    assert value["enabled"] is True
    assert value["consent_forms"] is False
    assert value["consent_forms_lapsed"] is False
    assert value["acknowledged_at"] == now
    assert value["policy_version"] == "2"
    assert _stored(db_session)["consent_forms"] is False


def test_an_agreement_yes_does_not_ride_on_a_diversity_change(client, db_session, now):
    value = _put(client, enabled=True, consent_forms=True, acknowledged_at=None, agreed_policy="2")
    assert value["enabled"] is True
    assert value["consent_forms"] is False


def test_a_turn_off_from_an_old_tab_goes_through(client, db_session):
    _seed(db_session, enabled=True, consent_forms=True, policy_version="2")
    value = _put(
        client, enabled=False, consent_forms=False, acknowledged_at=_OLD_STAMP,
        policy_version="1",
    )
    assert value["enabled"] is False
    assert value["consent_forms"] is False
    stored = _stored(db_session)
    assert stored["enabled"] is False and stored["consent_forms"] is False
    # Turning off is not a yes: the stamp stays the server's.
    assert stored["acknowledged_at"] == _OLD_STAMP and stored["policy_version"] == "2"


def test_the_lapse_is_derived_never_taken_from_a_client(client):
    value = _put(client, consent_forms_lapsed=True)
    assert value["consent_forms_lapsed"] is False
    assert (
        client.get("/api/settings/eeo-consent").json()["value"]["consent_forms_lapsed"]
        is False
    )


def test_agreeing_again_records_policy_two_and_grants(
    client, db_session, tmp_path, monkeypatch, now
):
    _seed(db_session, consent_forms=True)
    # What the web app's switch sends on a yes: a null stamp and the policy its
    # wording describes. The server records the time and its own policy.
    value = _put(
        client, consent_forms=True, acknowledged_at=None, policy_version="1",
        agreed_policy="2",
    )
    assert value["consent_forms"] is True
    assert value["consent_forms_lapsed"] is False
    assert value["policy_version"] == "2"
    assert value["acknowledged_at"] == now
    assert "agreed_policy" not in value
    stored = _stored(db_session)
    assert "agreed_policy" not in stored
    assert stored["consent_forms"] is True
    served = _context(client, tmp_path, monkeypatch)["eeo_consent"]
    assert served["consent_forms"] is True
    assert served["consent_forms_lapsed"] is False


def test_a_granted_agreement_survives_a_diversity_change(client, db_session, now):
    _seed(db_session, consent_forms=True, policy_version="2")
    value = _put(client, enabled=True, consent_forms=True, acknowledged_at=None)
    assert value["enabled"] is True
    assert value["consent_forms"] is True
    assert value["acknowledged_at"] == now


def test_a_policy_one_diversity_opt_in_stays_valid(
    client, db_session, tmp_path, monkeypatch
):
    """Policy 2 changed nothing the diversity opt-in covers, so no re-consent."""
    from app.services import autofill_profile

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"eeo": {"gender": "female"}}, db_session)
    _seed(db_session, enabled=True, consent_forms=True)
    body = _context(client, tmp_path, monkeypatch)
    assert body["eeo_consent"]["enabled"] is True
    assert body["eeo_consent"]["consent_forms"] is False
    assert body["profile"]["eeo"]["gender"] == "female"
    assert eeo_consent.disclosable_profile(db_session)["eeo"]["gender"] == "female"
