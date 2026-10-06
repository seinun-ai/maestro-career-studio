"""The full-automation switch (docs/plans/2026-10-05-full-automation-design.md, Part 1)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.setting import Setting
from app.services import job_search_brief

client = TestClient(app)


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch, db_session):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def test_full_automation_is_off_by_default_and_round_trips():
    assert client.get("/api/settings/auto-apply").json()["value"]["full_automation"] is False
    enabled = client.put("/api/settings/full-automation", json={"value": True})
    assert enabled.status_code == 200
    assert enabled.json()["value"]["full_automation"] is True
    disabled = client.put("/api/settings/full-automation", json={"value": False})
    assert disabled.status_code == 200
    assert disabled.json()["value"]["full_automation"] is False


@pytest.mark.parametrize("current", [False, True])
def test_auto_apply_limits_write_cannot_change_full_automation(current):
    assert client.put("/api/settings/full-automation", json={"value": current}).status_code == 200
    value = client.get("/api/settings/auto-apply").json()["value"]
    value["full_automation"] = not current

    response = client.put("/api/settings/auto-apply", json={"value": value})

    assert response.status_code == 200
    assert response.json()["value"]["full_automation"] is current
    assert client.get("/api/settings/auto-apply").json()["value"]["full_automation"] is current


def test_the_brief_tells_agents_whether_full_automation_is_on(db_session):
    assert job_search_brief.build_brief(db_session)["auto_apply"]["full_automation"] is False


def test_turning_full_automation_off_updates_the_brief(db_session):
    value = client.get("/api/settings/auto-apply").json()["value"]
    for enabled in (True, False):
        assert client.put("/api/settings/full-automation", json={"value": enabled}).status_code == 200
        assert client.get("/api/settings/auto-apply").json()["value"]["full_automation"] is enabled
        assert job_search_brief.build_brief(db_session)["auto_apply"]["full_automation"] is enabled


@pytest.mark.parametrize("source", ["database", "file"])
def test_older_settings_stay_off_and_keep_their_guardrails(db_session, tmp_path, source):
    legacy = json.dumps({
        "max_proposals_per_run": 4,
        "max_submissions_per_day": 3,
        "cooldown_days": 30,
        "company_blocklist": ["Acme"],
        "proposal_expiry_days": 7,
        "auto_pick_margin": 5.0,
        "auto_pick_floor": 71.0,
    })
    if source == "database":
        db_session.add(Setting(key="auto_apply", value=legacy))
        db_session.commit()
    else:
        (tmp_path / "auto_apply.json").write_text(legacy, encoding="utf-8")

    response = client.get("/api/settings/auto-apply")
    assert response.status_code == 200
    value = response.json()["value"]
    assert value == {**json.loads(legacy), "full_automation": False}


@pytest.mark.parametrize("value", ["yes", "on", "1", 1])
def test_full_automation_rejects_non_boolean_values(value):
    response = client.put("/api/settings/full-automation", json={"value": value})
    assert response.status_code == 422


@pytest.mark.parametrize("source", ["database", "file"])
def test_invalid_stored_full_automation_degrades_to_off(db_session, tmp_path, source):
    invalid = json.dumps({"full_automation": "yes"})
    if source == "database":
        db_session.add(Setting(key="auto_apply", value=invalid))
        db_session.commit()
    else:
        (tmp_path / "auto_apply.json").write_text(invalid, encoding="utf-8")

    response = client.get("/api/settings/auto-apply")
    assert response.status_code == 200
    assert response.json()["value"]["full_automation"] is False
