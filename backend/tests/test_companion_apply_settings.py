"""The Companion's Apply switches (Settings > AI & models > Form filling): whether the panel picks the
base resume for the user, and whether Apply stops after each step. Stored as `companion_apply`."""

import json

from app.schemas.companion_apply import CompanionApplySettings
from app.services import companion_apply, text_settings
from app.services.sync import profile_bundle


def test_the_defaults_pick_the_resume_run_every_step_and_think_when_stuck(db_session, tmp_path, monkeypatch, client):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    body = client.get("/api/settings/companion-apply").json()
    assert body["key"] == "companion_apply"
    assert body["value"] == {"auto_pick": True, "stop_each_step": False, "think_when_stuck": True}


def test_each_switch_round_trips_and_is_mirrored_to_a_file(db_session, tmp_path, monkeypatch, client):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    put = client.put("/api/settings/companion-apply",
                     json={"value": {"auto_pick": False, "stop_each_step": True}})
    assert put.status_code == 200 and put.json()["value"] == {
        "auto_pick": False, "stop_each_step": True, "think_when_stuck": True}
    assert client.get("/api/settings/companion-apply").json()["value"] == {
        "auto_pick": False, "stop_each_step": True, "think_when_stuck": True}
    assert json.loads((tmp_path / "companion_apply.json").read_text(encoding="utf-8")) == {
        "auto_pick": False, "stop_each_step": True, "think_when_stuck": True}
    # A body that names only one switch leaves the others at their defaults.
    client.put("/api/settings/companion-apply", json={"value": {"stop_each_step": True}})
    assert client.get("/api/settings/companion-apply").json()["value"] == {
        "auto_pick": True, "stop_each_step": True, "think_when_stuck": True}


def test_think_when_stuck_round_trips_and_is_mirrored_to_the_file(db_session, tmp_path, monkeypatch, client):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    put = client.put("/api/settings/companion-apply", json={"value": {"think_when_stuck": False}})
    assert put.json()["value"] == {"auto_pick": True, "stop_each_step": False, "think_when_stuck": False}
    assert json.loads((tmp_path / "companion_apply.json").read_text(encoding="utf-8"))["think_when_stuck"] is False
    assert client.put("/api/settings/companion-apply", json={"value": {"think_when_stuck": "yes"}}).status_code == 422


def test_a_value_that_is_not_a_yes_or_no_is_refused(db_session, tmp_path, monkeypatch, client):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    assert client.put("/api/settings/companion-apply",
                      json={"value": {"auto_pick": "sometimes"}}).status_code == 422
    assert client.put("/api/settings/companion-apply",
                      json={"value": {"stop_each_step": 1}}).status_code == 422
    assert client.get("/api/settings/companion-apply").json()["value"] == CompanionApplySettings().model_dump()


def test_a_stored_blob_that_will_not_parse_reads_as_the_defaults(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    text_settings.set_text(companion_apply.COMPANION_APPLY_KEY, companion_apply.COMPANION_APPLY_FILE,
                           "{not json", db_session)
    assert companion_apply.get_settings(db_session) == CompanionApplySettings()


def test_the_setting_travels_with_the_profile(db_session):
    assert profile_bundle.MIRRORS[companion_apply.COMPANION_APPLY_KEY] == companion_apply.COMPANION_APPLY_FILE
