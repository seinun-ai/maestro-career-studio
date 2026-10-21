"""Use recommended models (GET/PUT /api/settings/models/recommended): one set per provider in
services/data/recommended_models.yaml, taken from the built-in catalog. While it is on, the four role
getters (the ONE place a role's model id is read) answer the set of the provider whose key is saved;
off, they answer your own picks, which it never overwrites."""

from pathlib import Path

import pytest
import yaml

from app.config import settings as app_settings
from app.services import model_settings
from app.services.llm_providers import registry

ROLES = ("fast", "smart", "assistant", "reasoning")
YAML_FILE = Path(model_settings.__file__).parent / "data" / "recommended_models.yaml"


def _roles(db) -> dict[str, str]:
    return {
        "fast": model_settings.get_fast_model(db),
        "smart": model_settings.get_smart_model(db),
        "assistant": model_settings.get_chat_model(db),
        "reasoning": model_settings.get_reasoning_model(db),
    }


def _problems(sets: dict) -> list[str]:
    """What would make a set name a model the app cannot call: an id not in the catalog, an id of
    another provider's (it would route there), a provider the app has no key for, a role missing."""
    catalog = {opt.id: opt.provider for opt in model_settings.MODEL_OPTIONS}
    out = []
    for provider, roles in sets.items():
        if provider not in model_settings.API_KEY_SETTINGS:
            out.append(f"{provider}: not a provider")
        if roles is None:
            continue
        if set(roles) != set(ROLES):
            out.append(f"{provider}: roles {sorted(roles)}")
        for role, model in roles.items():
            if model not in catalog:
                out.append(f"{provider}.{role}: {model} is not in the catalog")
            elif catalog[model] != provider:
                out.append(f"{provider}.{role}: {model} is a {catalog[model]} model")
    return out


# ---------------------------------------------------------------------------- the data file


def test_every_recommended_id_is_a_catalog_model_of_its_own_provider():
    sets = yaml.safe_load(YAML_FILE.read_text(encoding="utf-8"))["providers"]
    assert _problems(sets) == []
    assert set(sets) == set(model_settings.API_KEY_SETTINGS)  # every provider is named, set or not
    assert model_settings.recommended_sets() == {p: r for p, r in sets.items() if r}
    # The guard itself: a set naming an id the catalog lacks, or another provider's, fails.
    doctored = {"anthropic": {**sets["anthropic"], "smart": "claude-imaginary-9"},
                "gemini": {**sets["gemini"], "fast": "gpt-5.6-luna"}}
    assert len(_problems(doctored)) == 2


def test_openrouter_has_no_set_while_the_catalog_lists_none_of_its_models():
    seeded = {opt.provider for opt in model_settings.MODEL_OPTIONS}
    assert set(model_settings.recommended_sets()) == seeded - {"openrouter"}


# ---------------------------------------------------------------------------- the resolver


def test_with_only_a_claude_key_and_recommended_on_the_four_roles_are_claudes(db_session, client):
    model_settings.set_api_keys(db_session, {"anthropic": "sk-ant-test"})
    put = client.put("/api/settings/models/recommended", json={"on": True})
    assert put.status_code == 200

    claude = model_settings.recommended_sets()["anthropic"]
    roles = _roles(db_session)
    assert roles == claude
    assert all(model_settings.catalog_provider(m) == "anthropic" for m in roles.values())
    assert {registry.resolve(m).provider for m in roles.values()} == {"anthropic"}
    info = client.get("/api/settings/openai").json()
    assert (info["fast_model"], info["smart_model"], info["chat_model"], info["reasoning_model"]) == (
        claude["fast"], claude["smart"], claude["assistant"], claude["reasoning"])

    body = put.json()
    assert body["on"] is True and body["provider"] is None and body["active_provider"] == "anthropic"
    assert body["models"] == claude
    assert body["sets"] == model_settings.recommended_sets()


def test_turning_it_off_keeps_your_own_picks(db_session, client):
    model_settings.set_api_keys(db_session, {"anthropic": "sk-ant-test"})
    model_settings.set_models("gpt-6-luna", "gpt-6.1-sol", db_session, chat_model="gpt-5.6-luna")
    model_settings.set_reasoning_model(db_session, "claude-opus-5-5")
    mine = {"fast": "gpt-6-luna", "smart": "gpt-6.1-sol", "assistant": "gpt-5.6-luna",
            "reasoning": "claude-opus-5-5"}
    assert _roles(db_session) == mine

    on = client.put("/api/settings/models/recommended", json={"on": True}).json()
    assert _roles(db_session) == model_settings.recommended_sets()["anthropic"]
    assert on["own"] == mine
    # A key-only save while it is on writes the role rows back as they were, not as the set.
    assert client.put("/api/settings/openai", json={"gemini_api_key": "AIza-test"}).status_code == 200

    off = client.put("/api/settings/models/recommended", json={"on": False}).json()
    assert off["on"] is False and off["active_provider"] is None and off["models"] is None
    assert _roles(db_session) == mine
    assert client.get("/api/settings/models/recommended").json()["own"] == mine


def test_a_model_your_pick_uses_cannot_be_removed_while_the_set_is_on(db_session, client):
    model_settings.set_api_keys(db_session, {"anthropic": "sk-ant-test"})
    model_settings.add_extra_model(db_session, "claude-custom-1", "anthropic")
    model_settings.set_models("claude-custom-1", "gpt-5.6-luna", db_session)
    client.put("/api/settings/models/recommended", json={"on": True})
    with pytest.raises(ValueError, match="Fast, Smart or Assistant"):
        model_settings.remove_extra_model(db_session, "claude-custom-1")


def test_the_first_provider_with_a_key_unless_you_chose_one(db_session, client):
    model_settings.set_api_keys(db_session, {"openai": "sk-test", "anthropic": "sk-ant-test"})
    client.put("/api/settings/models/recommended", json={"on": True})
    assert _roles(db_session) == model_settings.recommended_sets()["openai"]  # the screen's order

    chose = client.put("/api/settings/models/recommended", json={"on": True, "provider": "anthropic"})
    assert chose.json()["provider"] == "anthropic"
    assert _roles(db_session) == model_settings.recommended_sets()["anthropic"]
    # Leaving provider out keeps the choice; null goes back to the first with a key.
    assert client.put("/api/settings/models/recommended", json={"on": True}).json()["provider"] == "anthropic"

    # The chosen provider's key went: the next provider with a key and a set answers.
    model_settings.set_api_keys(db_session, {"anthropic": None})
    assert _roles(db_session) == model_settings.recommended_sets()["openai"]
    auto = client.put("/api/settings/models/recommended", json={"on": True, "provider": None}).json()
    assert auto["provider"] is None and auto["active_provider"] == "openai"


def test_a_provider_without_a_set_is_refused(client):
    r = client.put("/api/settings/models/recommended", json={"on": True, "provider": "openrouter"})
    assert r.status_code == 400
    assert client.put("/api/settings/models/recommended", json={"on": True, "provider": "x"}).status_code == 422
    assert client.get("/api/settings/models/recommended").json()["on"] is False


def test_your_own_server_and_openrouter_keep_your_picks(db_session, client):
    client.put("/api/settings/models/recommended", json={"on": True})
    model_settings.set_api_keys(db_session, {"openrouter": "sk-or-test"})
    assert _roles(db_session)["fast"] == app_settings.fast_model
    assert client.get("/api/settings/models/recommended").json()["active_provider"] is None

    # An OpenAI key that goes to your own server is not OpenAI's: its set does not apply.
    model_settings.set_api_keys(db_session, {"openai": "sk-local"})
    model_settings.set_base_url(db_session, "http://127.0.0.1:11434/v1")
    model_settings._set_value(db_session, model_settings.FAST_MODEL_KEY, "llama-local")
    assert _roles(db_session)["fast"] == "llama-local"


def test_a_key_from_the_environment_counts(db_session, monkeypatch):
    monkeypatch.setattr(app_settings, "gemini_api_key", "AIza-env")
    model_settings.set_recommended(db_session, on=True)
    assert _roles(db_session) == model_settings.recommended_sets()["gemini"]


def test_off_is_the_default(db_session, client):
    body = client.get("/api/settings/models/recommended").json()
    assert body == {
        "on": False,
        "provider": None,
        "active_provider": None,
        "models": None,
        "own": {"fast": app_settings.fast_model, "smart": app_settings.smart_model,
                "assistant": app_settings.chat_model,
                "reasoning": model_settings.default_reasoning_model(db_session)},
        "sets": model_settings.recommended_sets(),
    }
