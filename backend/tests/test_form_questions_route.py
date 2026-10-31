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
    assert [c["market"] for c in body["countries"]] == ["UK", "US"]
    assert body["countries"][1]["permits"][0]["key"] == "status"
    assert "permits" not in body  # Phase 1's market-keyed copy is cut: each country carries its own
    assert body["offers_eeo"] is True


def test_each_country_is_served_with_what_your_citizenship_settles(client):
    """The route reads the stored citizenships: an Indian citizen applying in India and Germany has
    India's three permit answers settled and none of Germany's."""
    client.put("/api/settings/market", json={"value": {"home": "IN", "apply_in": ["IN", "DE"]}})
    saved = client.put("/api/settings/autofill", json={"value": {"personal": {"citizenships": ["IN"]}}})
    assert saved.status_code == 200, saved.text
    body = client.get("/api/settings/autofill/questions").json()
    assert body["chosen"] is True
    india, germany = body["countries"]
    assert (india["market"], india["label"]) == ("IN", "India")
    assert [f["key"] for f in india["answers"]] == ["expected_pay", "current_ctc"]
    assert india["derived"] == {
        "authorized_now": {"value": True, "via": "IN"},
        "sponsorship_now": {"value": False, "via": "IN"},
        "sponsorship_future": {"value": False, "via": "IN"},
    }
    assert germany["market"] == "DE" and "derived" not in germany  # served without defaults
    assert [f["key"] for f in body["language_fields"]] == ["cefr"]


def test_a_given_answer_that_differs_is_served_with_nothing_derived(client):
    client.put("/api/settings/market", json={"value": {"home": "IN", "apply_in": ["DE"]}})
    client.put("/api/settings/autofill", json={"value": {
        "personal": {"citizenships": ["FR"]}, "work_auth_by_country": {"DE": {"authorized_now": False}},
    }})
    (germany,) = client.get("/api/settings/autofill/questions").json()["countries"]
    assert "derived" not in germany


def test_with_no_market_chosen_the_set_is_the_generic_one(client):
    """No country chosen: no country's work permits or diversity set, and no address rule, so the
    state line keeps its own label and is optional (Decision 1 of the country form-questions plan)."""
    body = client.get("/api/settings/autofill/questions").json()
    assert body["chosen"] is False and body["offers_eeo"] is False
    assert body["countries"] == [] and "language_fields" not in body
    personal = next(g for g in body["groups"] if g["key"] == "personal")
    state = next(f for f in personal["fields"] if f["key"] == "state")
    assert state["label"] == "State" and state["optional"] is True


def test_the_set_is_served_without_defaults(client):
    client.put("/api/settings/market", json={"value": {"home": "US", "apply_in": ["US"]}})
    body = client.get("/api/settings/autofill/questions").json()
    assert body["chosen"] is True and [c["market"] for c in body["countries"]] == ["US"]
    personal = next(g for g in body["groups"] if g["key"] == "personal")
    state = next(f for f in personal["fields"] if f["key"] == "state")
    # Served without defaults, as the frontend's FieldDef reads them: a required field has no
    # `optional`, and `byHome` appears only on the address lines it names.
    assert state["label"] == "State" and "optional" not in state and state["byHome"] == "state"
    assert next(f for f in personal["fields"] if f["key"] == "postal_code")["byHome"] == "postcode"
    assert "byHome" not in personal["fields"][0]


def test_reading_the_set_seeds_no_form_answers(client, db_session, settings_dir):
    """The set is derived: the route peeks the form answers, so a read leaves no row or mirror."""
    from app.models.setting import Setting

    client.get("/api/settings/autofill/questions")
    assert db_session.get(Setting, "autofill_profile") is None
    assert not (settings_dir / "autofill.json").exists()
