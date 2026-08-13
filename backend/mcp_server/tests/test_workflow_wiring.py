"""Task 7: the workflow hint layer wired into the actual MCP tools.

mcp_server/tests/test_workflow.py covers workflow.py's pure composition
functions in isolation; this file covers the tool functions in server.py that
call the backend client, then hand the response to workflow.py and return the
wrapped envelope. Every _client method is monkeypatched — no httpx, no DB.
"""
import inspect

import mcp_server.server as srv

# ---------- score_ats ----------


def _score(slug, composite=70.0):
    return {
        "target_type": "base_resume",
        "target_id": slug,
        "composite": composite,
        "subscores_json": {},
        "coverage_warning": None,
    }


def test_score_ats_wraps_scores_recommendation_and_hint(monkeypatch):
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None: [
        _score("alpha", 80.0), _score("beta", 60.0),
    ])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: {"mirror_wording": True})

    out = srv.score_ats("job1")

    assert [s["target_id"] for s in out["scores"]] == ["alpha", "beta"]
    assert out["recommendation"]["recommended"] == "alpha"
    assert out["next"]["state"] == "bases_scored"
    quick = [o for o in out["next"]["options"] if o["tool"] == "quick_tailor"][0]
    assert quick["args"] == {"job_id": "job1", "base_resume": "alpha"}


def test_score_ats_brief_never_reads_settings_or_profile(monkeypatch):
    # The whole point of `brief` is a triage loop paying no extra HTTP round
    # trip. If either settings call fires, the mutation is invisible to a
    # test that only checks the return value — assert the calls never happen.
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None: [_score("alpha")])

    def _boom_settings():
        raise AssertionError("get_mcp_workflow_settings must not be called when brief=True")

    def _boom_profile():
        raise AssertionError("get_quick_tailor_profile must not be called when brief=True")

    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", _boom_settings)
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", _boom_profile)

    out = srv.score_ats("job1", brief=True)

    assert out["next"] is None
    # brief suppresses ONLY the hint — the deterministic ranking is free and
    # still useful mid-triage.
    assert out["recommendation"]["recommended"] == "alpha"


def test_score_ats_wraps_even_when_hints_are_off(monkeypatch):
    # The envelope must be the SAME SHAPE whether or not a hint was actually
    # composed — a bare dict here would mean an agent has to branch on
    # whether "next" exists at all, not just whether it's null.
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None: [_score("alpha")])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: {})

    out = srv.score_ats("job1")

    assert "next" in out
    assert out["next"] is None
    assert out["recommendation"]["recommended"] == "alpha"


# ---------- create_tailoring_session ----------


def test_create_tailoring_session_default_is_enrich_false():
    sig = inspect.signature(srv.create_tailoring_session)
    assert sig.parameters["enrich"].default is False


def test_create_tailoring_session_calls_client_with_enrich_false_by_default(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client, "create_tailoring_session",
        lambda job_id, base_resume, enrich=True: seen.update(enrich=enrich) or {"id": "s1"},
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    srv.create_tailoring_session("job1", "hybrid")

    assert seen["enrich"] is False


def test_create_tailoring_session_wraps_even_when_hints_are_off(monkeypatch):
    # Same envelope-consistency rule as score_ats: the key must always be
    # there, only its value changes with the switch.
    session = {"id": "s1", "gaps_json": {"categories": []}, "resolutions_json": []}
    monkeypatch.setattr(srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: session)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    out = srv.create_tailoring_session("job1", "hybrid")

    assert "next" in out
    assert out["next"] is None
    assert out["id"] == "s1"


def test_create_tailoring_session_wraps_with_next_hint(monkeypatch):
    session = {
        "id": "s1",
        "gaps_json": {"categories": [{"name": "missing_skill", "gaps": [{"gap_id": "g1"}]}]},
        "resolutions_json": [],
    }
    monkeypatch.setattr(srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: session)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})

    out = srv.create_tailoring_session("job1", "hybrid")

    assert out["id"] == "s1"
    assert out["next"]["state"] == "gaps_pending"


# ---------- resolve_gaps ----------


def test_resolve_gaps_wraps_with_next_hint(monkeypatch):
    session = {"id": "s1", "gaps_json": {"categories": []}, "resolutions_json": []}
    monkeypatch.setattr(srv._client, "resolve_gaps", lambda session_id, items: session)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})

    out = srv.resolve_gaps(tailoring_session_id="s1", resolutions=[])

    assert out["id"] == "s1"
    # no gaps at all -> straight to tailor, per workflow.next_after_session
    assert out["next"]["call"] == "tailor_session"


# ---------- tailor_session ----------


def test_tailor_session_wraps_with_render_hint(monkeypatch):
    monkeypatch.setattr(
        srv._client, "tailor_session",
        lambda sid, user_prompt=None, ops=None: {"session": {"id": sid, "application_id": "app1"}, "compare": None},
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})

    out = srv.tailor_session(tailoring_session_id="s1")

    assert out["next"]["call"] == "render_pdf"
    assert out["next"]["options"][0]["args"] == {"target_type": "application", "target_id": "app1"}


def test_tailor_session_next_is_null_without_an_application_id(monkeypatch):
    # If tailor() ever returns a session with no application_id, there is no
    # PDF to point render_pdf at — the hint must degrade to null, not crash.
    monkeypatch.setattr(
        srv._client, "tailor_session",
        lambda sid, user_prompt=None, ops=None: {"session": {"id": sid}, "compare": None},
    )

    out = srv.tailor_session(tailoring_session_id="s1")

    assert out["next"] is None


# ---------- quick_tailor ----------


def test_quick_tailor_creates_with_enrich_false_then_applies_profile(monkeypatch):
    calls = []
    monkeypatch.setattr(
        srv._client, "create_tailoring_session",
        lambda job_id, base_resume, enrich=True: (
            calls.append(("create", job_id, base_resume, enrich)), {"id": "s1"}
        )[1],
    )
    monkeypatch.setattr(
        srv._client, "apply_quick_tailor_profile",
        lambda session_id: (calls.append(("apply", session_id)), {"id": session_id, "gaps_json": {}, "resolutions_json": []})[1],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    out = srv.quick_tailor("job1", "hybrid")

    assert calls == [("create", "job1", "hybrid", False), ("apply", "s1")]
    assert out["id"] == "s1"


def test_quick_tailor_returns_the_filled_session_wrapped(monkeypatch):
    monkeypatch.setattr(srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: {"id": "s1"})
    filled = {"id": "s1", "gaps_json": {"categories": []}, "resolutions_json": []}
    monkeypatch.setattr(srv._client, "apply_quick_tailor_profile", lambda session_id: filled)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: {"instruction": ""})

    out = srv.quick_tailor("job1", "hybrid")

    assert out["id"] == "s1"
    assert "next" in out
    assert out["next"]["call"] == "tailor_session"


def test_quick_tailor_skips_profile_fetch_when_hints_disabled(monkeypatch):
    monkeypatch.setattr(srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: {"id": "s1"})
    monkeypatch.setattr(
        srv._client, "apply_quick_tailor_profile",
        lambda session_id: {"id": "s1", "gaps_json": {}, "resolutions_json": []},
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    def _boom():
        raise AssertionError("get_quick_tailor_profile must not be called when hints are off")

    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", _boom)

    out = srv.quick_tailor("job1", "hybrid")

    assert out["next"] is None


def test_quick_tailor_threads_the_instruction_when_the_session_has_no_note(monkeypatch):
    monkeypatch.setattr(srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: {"id": "s1"})
    filled = {
        "id": "s1",
        "gaps_json": {"categories": [{"name": "missing_skill", "gaps": [{"gap_id": "g1"}]}]},
        "resolutions_json": [{"gap_id": "g1", "action": "skip", "payload": {}}],
    }
    monkeypatch.setattr(srv._client, "apply_quick_tailor_profile", lambda session_id: filled)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: {"instruction": "Keep it punchy."})

    out = srv.quick_tailor("job1", "hybrid")

    tailor_option = [o for o in out["next"]["options"] if o["tool"] == "tailor_session"][0]
    assert tailor_option["args"]["user_prompt"] == "Keep it punchy."


def test_quick_tailor_does_not_override_the_sessions_own_note(monkeypatch):
    monkeypatch.setattr(srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: {"id": "s1"})
    filled = {
        "id": "s1",
        "user_prompt": "Already told it what I want.",
        "gaps_json": {"categories": [{"name": "missing_skill", "gaps": [{"gap_id": "g1"}]}]},
        "resolutions_json": [{"gap_id": "g1", "action": "skip", "payload": {}}],
    }
    monkeypatch.setattr(srv._client, "apply_quick_tailor_profile", lambda session_id: filled)
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: {"instruction": "A different instruction."})

    out = srv.quick_tailor("job1", "hybrid")

    tailor_option = [o for o in out["next"]["options"] if o["tool"] == "tailor_session"][0]
    assert "user_prompt" not in tailor_option["args"]


def test_quick_tailor_docstring_states_no_in_house_llm_call():
    doc = (srv.quick_tailor.__doc__ or "")
    assert "NO in-house LLM call" in doc
    assert "own model" in doc.lower()


def test_quick_tailor_docstring_carries_the_honesty_rule():
    doc = (srv.quick_tailor.__doc__ or "").lower()
    assert "fabricate" in doc
    assert "skills category" in doc
    assert "never as an experience or project" in doc


def test_quick_tailor_docstring_documents_the_409s():
    doc = (srv.quick_tailor.__doc__ or "").lower()
    assert "409" in doc
    assert "stale" in doc
    assert "fatal health gate" in doc


def test_quick_tailor_docstring_explains_zero_planned_resolutions():
    doc = (srv.quick_tailor.__doc__ or "").lower()
    assert "not an error" in doc
    assert "resolve_gaps" in doc


# ---------- profile registration ----------


def test_quick_tailor_is_registered():
    assert "quick_tailor" in set(srv.list_registered_tool_names())


def test_quick_tailor_is_apply_only_not_hunt():
    from mcp_server.profiles import APPLY_TOOLS, HUNT_TOOLS

    assert "quick_tailor" in APPLY_TOOLS
    assert "quick_tailor" not in HUNT_TOOLS


def test_score_ats_skips_the_profile_fetch_when_hints_are_off(monkeypatch):
    """The quick-tailor profile fills the quick_tailor option's `detail` and
    nothing else, so fetching it with hints off is a discarded round-trip.
    Passed as a keyword ARGUMENT it would be evaluated unconditionally — that
    is the trap this pins."""
    monkeypatch.setattr(
        srv._client, "score_ats",
        lambda job_id, target_type=None, target_id=None: [_score("alpha", 80.0)],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    calls = []
    monkeypatch.setattr(
        srv._client, "get_quick_tailor_profile", lambda: calls.append(1) or {},
    )

    out = srv.score_ats("job1")

    assert out["next"] is None
    assert calls == [], "fetched a quick-tailor profile it then discarded"


def test_score_ats_skips_the_profile_fetch_when_quick_tailor_is_unregistered(monkeypatch):
    """A hunt-profile triage loop never gets a quick_tailor option, so the
    profile behind it is pure waste — twenty postings, twenty discarded calls."""
    from mcp_server.profiles import HUNT_TOOLS

    monkeypatch.setattr(srv, "_active_allowed_tools", lambda: HUNT_TOOLS)
    monkeypatch.setattr(
        srv._client, "score_ats",
        lambda job_id, target_type=None, target_id=None: [_score("alpha", 80.0)],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    calls = []
    monkeypatch.setattr(
        srv._client, "get_quick_tailor_profile", lambda: calls.append(1) or {},
    )

    out = srv.score_ats("job1")

    assert calls == [], "fetched a profile no option could display"
    assert [o["tool"] for o in out["next"]["options"]] == []
