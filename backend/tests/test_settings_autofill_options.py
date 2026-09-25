import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import model_settings


@pytest.fixture
def client(db_session):
    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_low_stakes_defaults_off_and_round_trips(db_session):
    assert model_settings.get_autofill_low_stakes(db_session) is False
    model_settings.set_autofill_low_stakes(db_session, True)
    assert model_settings.get_autofill_low_stakes(db_session) is True
    model_settings.set_autofill_low_stakes(db_session, False)
    assert model_settings.get_autofill_low_stakes(db_session) is False
    assert model_settings._get_raw_value(db_session, model_settings.AUTOFILL_LOW_STAKES_KEY) is None


def test_the_options_endpoint_reads_and_writes_the_flag(client, db_session):
    assert client.get("/api/settings/autofill-options").json() == {"low_stakes": False}
    assert client.put("/api/settings/autofill-options", json={"low_stakes": True}).json() == {"low_stakes": True}
    assert model_settings.get_autofill_low_stakes(db_session) is True
    assert client.get("/api/settings/autofill-options").json() == {"low_stakes": True}
    assert client.put("/api/settings/autofill-options", json={"low_stakes": False}).json() == {"low_stakes": False}


def test_the_options_endpoint_refuses_a_non_boolean_or_extra_key(client):
    assert client.put("/api/settings/autofill-options", json={"low_stakes": "maybe"}).status_code == 422
    assert client.put("/api/settings/autofill-options", json={}).status_code == 422
    assert client.put("/api/settings/autofill-options",
                      json={"low_stakes": True, "engine": "jev"}).status_code == 422
