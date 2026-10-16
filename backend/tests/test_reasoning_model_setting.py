"""Settings › AI & models › Models: the Reasoning model the Companion's reasoning step calls (design 2026-10-14)."""

import pytest

from app.services import model_settings


def _smart(db, model):
    model_settings._set_value(db, model_settings.SMART_MODEL_KEY, model)


@pytest.mark.parametrize("smart, expected", [
    ("claude-haiku-5-5", "claude-sonnet-5-5"),   # not a strong model: the provider's strong one
    ("claude-opus-5-5", "claude-opus-5-5"),      # already a strong model: itself
    ("gpt-5.6-luna", "gpt-6.1-sol"),             # the small OpenAI model (tier says "smart"): the strong OpenAI model
    ("gpt-6.1-sol", "gpt-6.1-sol"),              # already the strong OpenAI model: itself
    ("gemini-3.7-flash", "gemini-3.7-flash"),    # no strong Gemini in the catalog: the smart model
])
def test_the_default_is_the_strong_model_of_the_smart_models_provider(db_session, smart, expected):
    _smart(db_session, smart)
    assert model_settings.get_reasoning_model(db_session) == expected


def test_a_custom_endpoint_reasons_with_the_smart_model(db_session):
    model_settings.set_base_url(db_session, "http://127.0.0.1:11434/v1")
    _smart(db_session, "llama-local")
    assert model_settings.get_reasoning_model(db_session) == "llama-local"


def test_the_reasoning_model_round_trips_and_null_goes_back_to_the_default(client, db_session):
    put = client.put("/api/settings/openai", json={"reasoning_model": "claude-opus-5-5"})
    assert put.status_code == 200 and put.json()["reasoning_model"] == "claude-opus-5-5"
    back = client.put("/api/settings/openai", json={"reasoning_model": None})
    assert back.json()["reasoning_model"] == model_settings.default_reasoning_model(db_session)


def test_an_unknown_reasoning_model_is_refused_and_no_key_is_saved(client, db_session):
    r = client.put("/api/settings/openai", json={"reasoning_model": "not-a-model", "anthropic_api_key": "sk-ant-test"})
    assert r.status_code == 400
    assert model_settings.get_api_key("anthropic", db_session) is None


def test_a_put_that_leaves_the_field_out_keeps_the_stored_reasoning_model(client, db_session):
    client.put("/api/settings/openai", json={"reasoning_model": "claude-opus-5-5"})
    after = client.put("/api/settings/openai", json={"json_mode": "auto"})
    assert after.json()["reasoning_model"] == "claude-opus-5-5"


@pytest.mark.parametrize("cheap", ["gpt-6-luna", "claude-haiku-5-5"])
def test_any_catalog_model_can_be_the_reasoning_model_and_the_default_rule_is_unchanged(client, db_session, cheap):
    """Addendum 2026-10-14: the cheap models work for the reasoning role; the default stays the strong one."""
    assert cheap in {o["id"] for o in client.get("/api/settings/openai").json()["model_options"]}
    default = model_settings.default_reasoning_model(db_session)
    assert default in model_settings.STRONG_MODELS or default == model_settings.get_smart_model(db_session)
    put = client.put("/api/settings/openai", json={"reasoning_model": cheap})
    assert put.status_code == 200 and put.json()["reasoning_model"] == cheap
    assert model_settings.get_reasoning_model(db_session) == cheap
    assert {model_settings.get_fast_model(db_session), model_settings.get_smart_model(db_session),
            model_settings.get_chat_model(db_session)}.isdisjoint({"gpt-6-luna", "gpt-6.1-sol"})


@pytest.mark.parametrize("model, provider", [("claude-sonnet-6-0", "anthropic"), ("gpt-7-sol", "openai")])
def test_a_user_added_smart_model_is_kept_not_swapped_for_a_seeded_one(db_session, model, provider):
    """The strong-model lookup reads the seeded catalog only: an id the user added is the user's own choice."""
    model_settings.add_extra_model(db_session, model, provider)
    _smart(db_session, model)
    assert model_settings.get_reasoning_model(db_session) == model


def test_an_unregistered_smart_model_is_kept(db_session):
    _smart(db_session, "some-unregistered-id")
    assert model_settings.get_reasoning_model(db_session) == "some-unregistered-id"


def test_a_reasoning_model_with_stray_spaces_is_trimmed_before_it_is_checked(client, db_session):
    put = client.put("/api/settings/openai", json={"reasoning_model": "  claude-opus-5-5 "})
    assert put.status_code == 200 and put.json()["reasoning_model"] == "claude-opus-5-5"
    assert client.put("/api/settings/openai", json={"reasoning_model": "   "}).status_code == 200
