import json

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.setting import Setting
from app.routers import settings
from app.services import text_settings


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def test_the_memory_endpoint_is_gone(db_session, tmp_path, monkeypatch):
    # SYSTEM.md §13 memory-get-endpoint (cut 2026-08-02) and memory-blob-store
    # (cut 2026-08-03): context is composed from the KB
    # (career_kb.compose_context), and the legacy blob it replaced is gone, so
    # the whole /memory route is unregistered.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        get_response = client.get("/api/settings/memory")
        put_response = client.put("/api/settings/memory", json={"value": "New."})
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 404
    assert put_response.status_code == 404


def test_persona_endpoints_read_and_write(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        put_response = client.put(
            "/api/settings/persona", json={"value": "Vision: ship."}
        )
        get_response = client.get("/api/settings/persona")
    finally:
        app.dependency_overrides.clear()

    assert put_response.status_code == 200
    assert put_response.json() == {"key": "persona", "value": "Vision: ship."}
    assert get_response.json() == {"key": "persona", "value": "Vision: ship."}
    assert (tmp_path / "persona.md").read_text(encoding="utf-8") == "Vision: ship."


def test_autofill_endpoints_round_trip_json(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    profile = {
        "personal": {"first_name": "Sample", "email": "a@example.com"},
        "work_auth": {"authorized_to_work": "yes", "requires_sponsorship": "yes"},
        "custom": [{"question": "Notice period?", "answer": "2 weeks"}],
    }
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        empty = client.get("/api/settings/autofill")
        put_response = client.put("/api/settings/autofill", json={"value": profile})
        get_response = client.get("/api/settings/autofill")
    finally:
        app.dependency_overrides.clear()

    assert empty.json() == {"key": "autofill_profile", "value": {}}
    assert put_response.status_code == 200
    assert get_response.json()["value"] == profile
    import json

    assert json.loads((tmp_path / "autofill.json").read_text(encoding="utf-8")) == profile


def test_prompt_endpoints_list_update_and_reset(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings.prompts, "PROMPT_DIR", tmp_path)
    for key in settings.prompts.VALID_PROMPTS:
        (tmp_path / f"{key}.txt").write_text(f"default {key}", encoding="utf-8")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        list_response = client.get("/api/settings/prompts")
        put_response = client.put("/api/settings/prompts/qa", json={"value": "custom qa"})
        reset_response = client.post("/api/settings/prompts/qa/reset")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert {item["key"] for item in list_response.json()} == settings.prompts.VALID_PROMPTS
    assert put_response.json() == {"key": "qa", "value": "custom qa"}
    assert reset_response.json() == {"key": "qa", "value": "default qa"}
    assert db_session.get(Setting, "prompt.qa").value == "default qa"


def test_openai_endpoint_returns_config(db_session, monkeypatch):
    monkeypatch.setattr(settings.app_settings, "fast_model", "gpt-fast")
    monkeypatch.setattr(settings.app_settings, "smart_model", "gpt-smart")
    monkeypatch.setattr(settings.app_settings, "openai_api_key", "sk-abc")
    monkeypatch.setattr(settings.app_settings, "gemini_api_key", "gemini-abc")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/settings/openai")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["fast_model"] == "gpt-fast"
    assert body["smart_model"] == "gpt-smart"
    assert body["api_key_configured"] is True
    assert body["gemini_api_key_configured"] is True
    # No key stored in the app yet, so the env keys are the effective ones.
    assert body["openai_key_source"] == "env"
    assert body["gemini_key_source"] == "env"
    assert {option["id"] for option in body["model_options"]} >= {
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gpt-5.6-luna",
    }


def test_openai_endpoint_reports_missing_key(db_session, monkeypatch):
    monkeypatch.setattr(settings.app_settings, "openai_api_key", "")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/settings/openai")
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert body["api_key_configured"] is False
    assert body["openai_key_source"] == "none"


def test_key_source_settings_beats_env(db_session, monkeypatch):
    # The confusing production state this field exists for: a key saved in the
    # app is in charge even when .env carries one (or carries none) — the
    # response must attribute the effective key to "settings", not "env".
    monkeypatch.setattr(settings.app_settings, "openai_api_key", "sk-env")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        put = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gpt-5.6-luna",
                "smart_model": "gpt-5.6-luna",
                "openai_api_key": "sk-stored-in-app",
            },
        )
        assert put.status_code == 200
        response = TestClient(app).get("/api/settings/openai")
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert body["api_key_configured"] is True
    assert body["openai_key_source"] == "settings"


def test_openai_endpoint_updates_models(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gemini-3.7-flash",
                "openai_api_key": "sk-custom-openai-key",
                "gemini_api_key": "custom-gemini-key",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["fast_model"] == "gemini-3.5-flash-lite"
    assert body["smart_model"] == "gemini-3.7-flash"
    # Key material must never come back over this unauthenticated API — only
    # the booleans. Persisted values are asserted against the DB instead.
    assert "openai_api_key" not in body
    assert "gemini_api_key" not in body
    assert body["api_key_configured"] is True
    assert body["gemini_api_key_configured"] is True
    assert db_session.get(Setting, "llm.fast_model").value == "gemini-3.5-flash-lite"
    assert db_session.get(Setting, "llm.smart_model").value == "gemini-3.7-flash"
    assert db_session.get(Setting, "llm.openai_api_key").value == "sk-custom-openai-key"
    assert db_session.get(Setting, "llm.gemini_api_key").value == "custom-gemini-key"


def test_get_openai_never_returns_key_material(db_session, monkeypatch):
    monkeypatch.setattr(settings.app_settings, "openai_api_key", "sk-from-env")
    db_session.add(Setting(key="llm.openai_api_key", value="sk-stored-in-db"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/settings/openai").json()
    finally:
        app.dependency_overrides.clear()

    assert body["api_key_configured"] is True
    assert "openai_api_key" not in body
    assert "gemini_api_key" not in body
    assert "sk-stored-in-db" not in json.dumps(body)
    assert "sk-from-env" not in json.dumps(body)


def test_model_only_update_preserves_stored_keys(db_session):
    """Omitting a key field must not clear it.

    The settings page PUTs this payload on every model-dropdown change. Since
    `set_models` deletes the Setting row on a None key, an absent field has to
    be re-supplied from storage or changing a model would wipe the key.
    """
    db_session.add(Setting(key="llm.openai_api_key", value="sk-keep-me"))
    db_session.add(Setting(key="llm.gemini_api_key", value="gem-keep-me"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gemini-3.7-flash",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["api_key_configured"] is True
    assert db_session.get(Setting, "llm.openai_api_key").value == "sk-keep-me"
    assert db_session.get(Setting, "llm.gemini_api_key").value == "gem-keep-me"


def test_explicit_null_clears_stored_key(db_session):
    db_session.add(Setting(key="llm.openai_api_key", value="sk-remove-me"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gemini-3.7-flash",
                "openai_api_key": None,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert db_session.get(Setting, "llm.openai_api_key") is None


def test_key_only_put_leaves_every_model_untouched(db_session):
    """The API keys card sends ONLY the key it edited.

    The role fields used to be required, so saving a key meant echoing all
    three models back — a client re-sending state it did not edit, which is how
    a stale copy overwrites a fresh one. Absent now means "leave it alone" for
    the models exactly as it already did for the keys.
    """
    db_session.add(Setting(key="llm.fast_model", value="gemini-3.7-flash"))
    db_session.add(Setting(key="llm.smart_model", value="gpt-5.6-luna"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={"openai_api_key": "sk-new"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["fast_model"] == "gemini-3.7-flash"
    assert body["smart_model"] == "gpt-5.6-luna"
    assert db_session.get(Setting, "llm.openai_api_key").value == "sk-new"


def test_single_model_put_leaves_the_other_roles_and_keys_untouched(db_session):
    """And symmetrically: the Models card sends one dropdown, not all of them."""
    db_session.add(Setting(key="llm.fast_model", value="gemini-3.7-flash"))
    db_session.add(Setting(key="llm.smart_model", value="gpt-5.6-luna"))
    db_session.add(Setting(key="llm.openai_api_key", value="sk-keep-me"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={"fast_model": "gemini-3.5-flash-lite"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["fast_model"] == "gemini-3.5-flash-lite"
    assert body["smart_model"] == "gpt-5.6-luna"  # untouched
    assert db_session.get(Setting, "llm.openai_api_key").value == "sk-keep-me"


def test_openai_endpoint_rejects_unknown_model(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={"fast_model": "bogus", "smart_model": "gpt-5.6-luna"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_unknown_prompt_returns_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/prompts/not_real",
            json={"value": "x"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_chat_model_defaults_and_roundtrip(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)

        body = client.get("/api/settings/openai").json()
        assert body["chat_model"] == "gpt-5.6-luna"  # config default until set

        resp = client.put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gemini-3.7-flash",
                "chat_model": "gpt-5.6-luna",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chat_model"] == "gpt-5.6-luna"
        assert body["smart_model"] == "gemini-3.7-flash"
        assert db_session.get(Setting, "llm.chat_model").value == "gpt-5.6-luna"

        # Omitting chat_model leaves the stored value untouched (older clients).
        resp = client.put(
            "/api/settings/openai",
            json={"fast_model": "gemini-3.5-flash-lite", "smart_model": "gpt-5.6-luna"},
        )
        assert resp.json()["chat_model"] == "gpt-5.6-luna"
    finally:
        app.dependency_overrides.clear()


def test_chat_model_rejects_tools_false_row(db_session):
    from app.services import llm_capabilities

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        llm_capabilities.save(
            db_session,
            llm_capabilities.CapabilityReport(
                model="gemini-3.7-flash",
                text=True,
                json=True,
                tools=False,
                errors={"tools": "model streamed no tool call"},
            ),
        )
        resp = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gpt-5.6-luna",
                "chat_model": "gemini-3.7-flash",
            },
        )
        assert resp.status_code == 400
        assert "streaming tool-call test" in resp.json()["detail"]

        # No capability row → allowed through (require() doctrine).
        db_session.delete(db_session.get(Setting, "llm.capabilities.gemini-3.7-flash"))
        db_session.commit()
        resp = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gpt-5.6-luna",
                "chat_model": "gemini-3.7-flash",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["chat_model"] == "gemini-3.7-flash"
    finally:
        app.dependency_overrides.clear()


def test_quick_tailor_defaults_when_unset(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/settings/quick-tailor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "key": "quick_tailor_profile",
        "value": {
            "keywords_into_skills": True,
            "mirror_wording": True,
            "summary_rename": False,
            "project_keyword_injection": False,
            "instruction": "",
        },
    }
    assert "default_base_resume" not in response.json()["value"]


def test_quick_tailor_round_trip_merges_defaults(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        put_response = client.put(
            "/api/settings/quick-tailor",
            json={"value": {"keywords_into_skills": False, "instruction": "keep bullets terse"}},
        )
        get_response = client.get("/api/settings/quick-tailor")
    finally:
        app.dependency_overrides.clear()

    assert put_response.status_code == 200
    value = get_response.json()["value"]
    assert value["keywords_into_skills"] is False           # stored override
    assert value["mirror_wording"] is True                  # default shows through
    assert value["instruction"] == "keep bullets terse"
    assert "default_base_resume" not in value
    import json
    mirrored = json.loads((tmp_path / "quick_tailor.json").read_text(encoding="utf-8"))
    assert mirrored["instruction"] == "keep bullets terse"


def test_quick_tailor_loads_when_stored_profile_still_has_removed_key(
    db_session, tmp_path, monkeypatch
):
    """Hand-edited profiles that still carry default_base_resume must load.

    The field is consulted by nothing and is gone from DEFAULTS; dropping it
    from an extra=forbid model would 422 those files. get_profile is a dict
    merge, so the stored key is dropped on read rather than rejected.
    """
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    (tmp_path / "quick_tailor.json").write_text(
        json.dumps(
            {
                "keywords_into_skills": False,
                "default_base_resume": "data_scientist",
                "instruction": "keep it short",
            }
        ),
        encoding="utf-8",
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/settings/quick-tailor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    value = response.json()["value"]
    assert value["keywords_into_skills"] is False
    assert value["instruction"] == "keep it short"
    assert "default_base_resume" not in value


def test_mcp_workflow_defaults_to_hints_on(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/settings/mcp-workflow")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "mcp_workflow"
    assert body["value"] == {"hints": True}


def test_mcp_workflow_put_roundtrips(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        client.put("/api/settings/mcp-workflow", json={"value": {"hints": False}})
        get_response = client.get("/api/settings/mcp-workflow")
    finally:
        app.dependency_overrides.clear()

    assert get_response.json()["value"]["hints"] is False


def test_mcp_workflow_round_trip_merges_defaults(db_session, tmp_path, monkeypatch):
    # A PUT that omits "hints" proves the defaults behaviour, not just that a
    # stored value round-trips: if the service ever stored/returned the raw
    # payload, "hints" would be missing from the response entirely.
    #
    # CHANGED 2026-08-26: mcp_workflow became a typed `JsonSetting`
    # (`McpWorkflowSettings`) instead of a raw dict merged over a DEFAULTS map.
    # Defaults still fill in — that was and is the point of this test — but an
    # unknown key is now DROPPED rather than preserved through the round trip,
    # and the file mirror holds the validated model rather than the raw body.
    # That matches every other typed setting here (auto_apply is stricter
    # still: extra="forbid" resets the whole file). The cost is forward
    # compatibility: a newer key written by a future build does not survive a
    # read/write cycle on this one.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        put_response = client.put(
            "/api/settings/mcp-workflow",
            json={"value": {"unknown_key": "ignored"}},
        )
        get_response = client.get("/api/settings/mcp-workflow")
    finally:
        app.dependency_overrides.clear()

    assert put_response.status_code == 200
    value = get_response.json()["value"]
    assert value["hints"] is True  # default filled in — stored payload had no "hints" key
    assert "unknown_key" not in value  # dropped by the model, not carried through
    mirrored = json.loads((tmp_path / "mcp_workflow.json").read_text(encoding="utf-8"))
    assert mirrored == {"hints": True}  # the validated model, not the raw payload


def test_gemini_35_flash_lite_is_a_valid_fast_model(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={"fast_model": "gemini-3.5-flash-lite", "smart_model": "gpt-5.6-luna"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["fast_model"] == "gemini-3.5-flash-lite"
    assert db_session.get(Setting, "llm.fast_model").value == "gemini-3.5-flash-lite"


def test_a_trimmed_out_stored_id_survives_a_round_trip_and_is_never_remapped(db_session):
    """A trimmed-out stored id is visible on GET and saves back unchanged.

    Was `test_stale_stored_role_put_returns_400_carrying_the_id`, written by the
    seed trim (2d61352) to pin NEVER REMAPPED — the app must not silently swap a
    model behind the user's back. That principle is what this still asserts: the
    id comes back verbatim, not rewritten to a seed.

    What changed is the 400. It was the consequence of that principle, not the
    goal, and it was a dead end: on any install predating the trim (`.env.example`
    shipped FAST_MODEL=gpt-4o-mini) the first action a user takes — saving an API
    key — failed, naming a model they had not touched, with no in-app way back.
    Admitting the configured id to the catalog keeps it verbatim AND lets the
    save through.
    """
    db_session.add(Setting(key="llm.fast_model", value="gpt-4o-mini"))
    db_session.add(Setting(key="llm.smart_model", value="gpt-5.6-luna"))
    db_session.add(Setting(key="llm.chat_model", value="gpt-5.6-luna"))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        body = client.get("/api/settings/openai").json()
        assert body["fast_model"] == "gpt-4o-mini"
        resp = client.put(
            "/api/settings/openai",
            json={
                "fast_model": body["fast_model"],
                "smart_model": body["smart_model"],
                "chat_model": body["chat_model"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    # Verbatim, not remapped onto a surviving seed.
    assert resp.json()["fast_model"] == "gpt-4o-mini"


def _configure(db_session, key: str, value: str) -> None:
    db_session.add(Setting(key=key, value=value))
    db_session.commit()


def test_a_model_the_seed_trim_orphaned_can_still_be_saved(db_session):
    """The catalog must admit what the install is ALREADY configured with.

    `.env.example` shipped FAST_MODEL=gpt-4o-mini until the seed trim cut
    MODEL_OPTIONS to three ids, so every install predating it names a model the
    catalog no longer lists. Rejecting that value bricked the first thing a new
    user does — save an API key — with no in-app way out.
    """
    _configure(db_session, "llm.fast_model", "gpt-4o-mini")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={"fast_model": "gpt-4o-mini", "smart_model": "gpt-5.6-luna"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["fast_model"] == "gpt-4o-mini"


def test_an_orphaned_configured_model_is_listed_so_the_dropdown_is_honest(db_session):
    # The select showed a value absent from its own option list. Surfacing it as
    # `configured` keeps the list truthful without pretending it is a seed.
    _configure(db_session, "llm.smart_model", "gpt-4o")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/settings/openai").json()
    finally:
        app.dependency_overrides.clear()

    row = next(o for o in body["model_options"] if o["id"] == "gpt-4o")
    assert row["source"] == "configured"
    assert row["provider"] == "openai"


def test_an_orphaned_gemini_id_is_attributed_to_gemini(db_session):
    _configure(db_session, "llm.fast_model", "gemini-2.0-flash")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/settings/openai").json()
    finally:
        app.dependency_overrides.clear()

    row = next(o for o in body["model_options"] if o["id"] == "gemini-2.0-flash")
    assert row["provider"] == "gemini"


def test_admitting_the_configured_id_does_not_admit_arbitrary_ones(db_session):
    # The escape hatch is scoped to what is already in use. Switching TO an
    # unknown id is still a 400 — otherwise the guard would be gone entirely.
    _configure(db_session, "llm.fast_model", "gpt-4o-mini")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={"fast_model": "bogus-not-configured", "smart_model": "gpt-5.6-luna"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
