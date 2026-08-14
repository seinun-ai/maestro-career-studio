"""Usable model catalog: seeds ∪ extras, add/remove, set_models validation."""

import json

import pytest

from app.models.setting import Setting
from app.services import llm_capabilities, model_settings


def test_usable_options_start_as_seeds(db_session):
    options = model_settings.get_usable_options(db_session)
    assert {opt.id for opt in options} == model_settings.VALID_MODEL_IDS
    dicts = model_settings.usable_option_dicts(db_session)
    assert all(row["source"] == "seed" for row in dicts)


def test_add_extra_model_merges_into_usable_catalog(db_session):
    model_settings.add_extra_model(
        db_session, "gpt-4.5-preview", "openai", label="GPT-4.5 Preview"
    )
    ids = model_settings.usable_ids(db_session)
    assert "gpt-4.5-preview" in ids
    assert "gpt-5.6-luna" in ids
    extras = model_settings.get_extra_models(db_session)
    assert extras == [
        model_settings.ModelOption(
            "gpt-4.5-preview", "GPT-4.5 Preview", "openai", "extra"
        )
    ]
    raw = db_session.get(Setting, model_settings.EXTRA_MODELS_KEY).value
    assert json.loads(raw)[0]["id"] == "gpt-4.5-preview"


def test_add_rejects_seed_and_duplicate(db_session):
    with pytest.raises(ValueError, match="built-in seed"):
        model_settings.add_extra_model(db_session, "gpt-5.6-luna", "openai")
    model_settings.add_extra_model(db_session, "my-local-gpt", "openai")
    with pytest.raises(ValueError, match="already in the catalog"):
        model_settings.add_extra_model(db_session, "my-local-gpt", "openai")


def test_set_models_accepts_extra(db_session):
    model_settings.add_extra_model(db_session, "gpt-custom", "openai")
    model_settings.set_models(
        "gpt-custom",
        "gpt-5.6-luna",
        db_session,
        chat_model="gpt-custom",
    )
    assert model_settings.get_fast_model(db_session) == "gpt-custom"
    assert model_settings.get_chat_model(db_session) == "gpt-custom"


def test_set_models_rejects_unknown_without_custom_endpoint(db_session):
    with pytest.raises(ValueError, match="Unsupported model"):
        model_settings.set_models("nope", "gpt-5.6-luna", db_session)


def test_chat_accepts_unprobed_gemini_extra(db_session):
    model_settings.add_extra_model(db_session, "gemini-exp-1206", "gemini")
    model_settings.set_models(
        "gemini-3.5-flash-lite",
        "gpt-5.6-luna",
        db_session,
        chat_model="gemini-exp-1206",
    )
    assert model_settings.get_chat_model(db_session) == "gemini-exp-1206"


def test_chat_rejects_tools_false_row(db_session):
    model_settings.add_extra_model(db_session, "gemini-exp-1206", "gemini")
    llm_capabilities.save(
        db_session,
        llm_capabilities.CapabilityReport(
            model="gemini-exp-1206",
            text=True,
            json=True,
            tools=False,
            errors={"tools": "model streamed no tool call"},
        ),
    )
    with pytest.raises(ValueError, match="streaming tool-call test"):
        model_settings.set_models(
            "gemini-3.5-flash-lite",
            "gpt-5.6-luna",
            db_session,
            chat_model="gemini-exp-1206",
        )


def test_remove_extra_rejects_when_in_use(db_session):
    model_settings.add_extra_model(db_session, "gpt-custom", "openai")
    model_settings.set_models("gpt-custom", "gpt-5.6-luna", db_session)
    with pytest.raises(ValueError, match="in use"):
        model_settings.remove_extra_model(db_session, "gpt-custom")
    model_settings.set_models("gemini-3.5-flash-lite", "gpt-5.6-luna", db_session)
    model_settings.remove_extra_model(db_session, "gpt-custom")
    assert "gpt-custom" not in model_settings.usable_ids(db_session)


def test_remove_seed_rejected(db_session):
    with pytest.raises(ValueError, match="Built-in"):
        model_settings.remove_extra_model(db_session, "gpt-5.6-luna")


def test_seed_catalog_is_exactly_the_three_in_use():
    assert model_settings.VALID_MODEL_IDS == {
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gpt-5.6-luna",
    }
    assert not hasattr(model_settings, "OPENAI_MODEL_IDS")
