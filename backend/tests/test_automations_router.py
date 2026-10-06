import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.main import app
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings, automations

client = TestClient(app)


def test_catalog_endpoint_shape():
    r = client.get("/api/automations")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"cards", "apps"}
    card = data["cards"][0]
    assert set(card) == {"id", "title", "summary", "kind", "needs", "never", "body"}
    app_ = data["apps"][0]
    assert set(app_) == {"id", "label", "reachable", "preamble", "attended_preamble", "note"}


def test_catalog_endpoint_serializes_needs_as_a_list():
    assert isinstance(client.get("/api/automations").json()["cards"][0]["needs"], list)


@pytest.mark.parametrize(("full_automation", "expected_kind"), [
    (False, "attended"),
    (True, "scheduled"),
])
def test_catalog_apply_kind_tracks_full_automation(
    db_session, tmp_path, monkeypatch, full_automation, expected_kind
):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    auto_apply_settings.set_settings(
        AutoApplySettings(full_automation=full_automation), db_session
    )

    response = client.get("/api/automations")

    assert response.status_code == 200
    apply = next(card for card in response.json()["cards"] if card["id"] == "apply-session")
    assert apply["kind"] == expected_kind


def test_a_broken_skill_file_fails_startup(tmp_path, monkeypatch):
    bad = tmp_path / "broken" / "SKILL.md"
    bad.parent.mkdir()
    bad.write_text("---\nname: broken\ndescription: x\nmetadata:\n  title: Broken\n---\nb\n")
    monkeypatch.setattr(main.seeding, "run_startup", lambda: None)
    monkeypatch.setattr(main, "_log_llm_config", lambda: None)
    monkeypatch.setattr(automations, "SKILLS_DIR", tmp_path)
    automations.load_cards.cache_clear()
    try:
        with pytest.raises(ValueError):
            with TestClient(main.app):
                pass
    finally:
        monkeypatch.undo()
        automations.load_cards.cache_clear()
