import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.job_preferences import JobPreferences
from app.services import job_preferences


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_empty_preferences_are_valid_and_not_set():
    prefs = JobPreferences()
    assert prefs.role_categories == []
    assert not job_preferences.is_set(prefs)


def test_unknown_role_category_is_rejected_never_normalized():
    # "Data Science" is an ALIAS that normalize() would accept — a typed PUT
    # must reject it: human input is validated, never coerced.
    with pytest.raises(ValidationError):
        JobPreferences(role_categories=["Data Science"])
    with pytest.raises(ValidationError):
        JobPreferences(role_categories=["definitely_not_a_role"])


def test_declared_and_reserved_keys_are_accepted():
    prefs = JobPreferences(role_categories=["data_scientist", "other"])
    assert job_preferences.is_set(prefs)


def test_round_trip_through_setting(db_session):
    saved = job_preferences.set_preferences(
        JobPreferences(role_categories=["data_engineer"], remote="remote"), db_session
    )
    assert saved.remote == "remote"
    loaded = job_preferences.get_preferences(db_session)
    assert loaded.role_categories == ["data_engineer"]
    assert loaded.remote == "remote"


def test_corrupt_stored_json_reads_as_defaults(db_session):
    from app.services import text_settings

    text_settings.set_text(
        job_preferences.JOB_PREFERENCES_KEY,
        job_preferences.JOB_PREFERENCES_FILE,
        "not json{",
        db_session,
    )
    assert job_preferences.get_preferences(db_session) == JobPreferences()


def test_get_returns_defaults_then_put_round_trips(client):
    r = client.get("/api/settings/job-preferences")
    assert r.status_code == 200
    assert r.json()["value"]["role_categories"] == []

    r = client.put(
        "/api/settings/job-preferences",
        json={"value": {"role_categories": ["ai_ml_engineer"], "remote": "hybrid"}},
    )
    assert r.status_code == 200
    assert client.get("/api/settings/job-preferences").json()["value"]["remote"] == "hybrid"


def test_put_bad_role_key_is_422(client):
    r = client.put(
        "/api/settings/job-preferences",
        json={"value": {"role_categories": ["nope_not_real"]}},
    )
    assert r.status_code == 422
