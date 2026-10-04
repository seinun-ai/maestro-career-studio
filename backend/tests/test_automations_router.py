import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.services import automations

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
