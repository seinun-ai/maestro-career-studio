import pytest

from app.services import model_settings


def test_defaults_point_at_openrouter_and_the_fast_engine(db_session):
    assert model_settings.get_jev_api_key(db_session) is None
    assert model_settings.get_jev_base_url(db_session) == "https://openrouter.ai/api"
    assert model_settings.get_jev_model(db_session) == "typesafe/jev-1.13"
    assert model_settings.get_autofill_engine(db_session) == "fast"


def test_jev_settings_round_trip(db_session):
    # Endpoint first: a host change forgets the key (the next test).
    model_settings.set_jev_base_url(db_session, "https://api.typesafe.ai")
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_jev_model(db_session, "jev-latest")
    model_settings.set_autofill_engine(db_session, "jev")
    assert model_settings.get_jev_api_key(db_session) == "sk-or-test"
    assert model_settings.get_jev_base_url(db_session) == "https://api.typesafe.ai"
    assert model_settings.get_jev_model(db_session) == "jev-latest"
    assert model_settings.get_autofill_engine(db_session) == "jev"


def test_a_host_change_forgets_the_key_and_the_engine(db_session):
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    model_settings.set_jev_base_url(db_session, "https://openrouter.ai/api/")  # same host
    assert model_settings.get_jev_api_key(db_session) == "sk-or-test"
    model_settings.set_jev_base_url(db_session, "https://api.typesafe.ai")
    assert model_settings.get_jev_api_key(db_session) is None
    assert model_settings.get_autofill_engine(db_session) == "fast"


def test_the_jev_base_url_must_be_http(db_session):
    """It decides where the key is sent — the set_base_url rule (§6)."""
    with pytest.raises(ValueError):
        model_settings.set_jev_base_url(db_session, "file:///etc/passwd")


def test_jev_cannot_be_the_engine_without_a_key(db_session):
    with pytest.raises(ValueError, match="key"):
        model_settings.set_autofill_engine(db_session, "jev")


def test_an_unknown_engine_is_refused(db_session):
    with pytest.raises(ValueError):
        model_settings.set_autofill_engine(db_session, "gpt")


def test_clearing_the_key_falls_back_to_the_fast_engine(db_session):
    """A stored `jev` engine with no key would fail every fill; the read says fast."""
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    model_settings.set_jev_api_key(db_session, None)
    assert model_settings.get_autofill_engine(db_session) == "fast"
