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
