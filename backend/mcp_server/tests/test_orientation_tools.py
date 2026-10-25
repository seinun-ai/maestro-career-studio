"""get_setup_status and get_tailoring_options: what a fresh agent reads first."""

import mcp_server.server as srv
from mcp_server import orientation

_STATUS = {
    "model_key": {"done": False, "detail": {}},
    "import_resumes": {"done": True, "detail": {"kb_entities": 4, "base_resumes": 1}},
    "autofill": {"done": False, "readiness": 0.4, "groups": {}, "blocking": ["work_auth"]},
    "job_preferences": {"done": False, "detail": {}},
    "persona": {"done": False, "detail": {}},
    "template": {"done": False, "detail": {}},
    "suggested_bases": [],
    "demo_bases": ["example"],
    "complete": False,
}


def test_setup_status_says_where_setup_stands_and_which_set_is_next(monkeypatch):
    monkeypatch.setattr(srv._client, "get_setup_status", lambda: _STATUS)
    out = srv.get_setup_status()
    assert out["ai_key"] is False
    assert out["demo_bases"] == ["example"]
    assert out["next_step"]["step"] == "base_resume"  # the one base is the demo
    assert out["next_step"]["tool_set"] == "profile"
    assert [s["name"] for s in out["tool_sets"]] == list(orientation.SET_NAMES)
    assert out["steps"] is _STATUS


def _tailoring_options(monkeypatch):
    stored = {"keywords_into_skills": False, "mirror_wording": True, "instruction": "Keep it short."}
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: stored)
    monkeypatch.setattr(srv._client, "get_persona", lambda: "Plain-spoken analyst.")
    return srv.get_tailoring_options()


def test_tailoring_options_give_each_preset_its_saved_setting(monkeypatch):
    from app.schemas.quick_tailor import QuickTailorProfile

    out = _tailoring_options(monkeypatch)
    switches = [k for k in QuickTailorProfile.model_fields if k != "instruction"]
    assert [p["key"] for p in out["presets"]] == switches
    by_key = {p["key"]: p for p in out["presets"]}
    assert by_key["keywords_into_skills"]["on"] is False
    assert by_key["summary_rename"]["on"] is False  # unset: the schema's default
    assert out["instruction"] == "Keep it short."
    assert out["persona"] == "Plain-spoken analyst."


def test_tailoring_options_explain_each_preset_in_plain_words(monkeypatch):
    from app.schemas.quick_tailor import QuickTailorProfile

    for preset in _tailoring_options(monkeypatch)["presets"]:  # one source: the schema's own description
        assert preset["means"] == QuickTailorProfile.model_fields[preset["key"]].description
        assert preset["means"]
