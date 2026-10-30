"""GET /api/settings/autofill/questions: the form questions resolved for the stored market
(services/form_questions), the one set Profile, Setup and readiness read."""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The market setting's file mirror goes to a throwaway folder (SYSTEM.md §12, 2026-10-21)."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    return tmp_path


def test_the_questions_follow_the_market(client):
    saved = client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK", "US"]}})
    assert saved.status_code == 200, saved.text
    body = client.get("/api/settings/autofill/questions").json()
    personal = next(g for g in body["groups"] if g["key"] == "personal")
    state = next(f for f in personal["fields"] if f["key"] == "state")
    assert state["label"] == "County" and state["optional"] is True
    assert set(body["permits"]) == {"UK", "US"}
    assert body["permits"]["US"][0]["key"] == "status"
    assert body["offers_eeo"] is True


def test_with_no_market_chosen_the_set_is_the_generic_one(client):
    """No country chosen: no country's work permits or diversity set, and no address rule, so the
    state line keeps its own label and is optional (Decision 1 of the country form-questions plan)."""
    body = client.get("/api/settings/autofill/questions").json()
    assert body["chosen"] is False and body["permits"] == {} and body["offers_eeo"] is False
    personal = next(g for g in body["groups"] if g["key"] == "personal")
    state = next(f for f in personal["fields"] if f["key"] == "state")
    assert state["label"] == "State" and state["optional"] is True


def test_the_set_is_served_without_defaults(client):
    client.put("/api/settings/market", json={"value": {"home": "US", "apply_in": ["US"]}})
    body = client.get("/api/settings/autofill/questions").json()
    assert body["chosen"] is True and list(body["permits"]) == ["US"]
    personal = next(g for g in body["groups"] if g["key"] == "personal")
    state = next(f for f in personal["fields"] if f["key"] == "state")
    # Served without defaults, as the frontend's FieldDef reads them: a required field has no
    # `optional`, and `byHome` appears only where it is true.
    assert state["label"] == "State" and "optional" not in state and state["byHome"] is True
    assert "byHome" not in personal["fields"][0]
