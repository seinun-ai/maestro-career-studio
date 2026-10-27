"""Task 7: the workflow hint layer wired into the actual MCP tools.

mcp_server/tests/test_workflow.py covers workflow.py's pure composition
functions in isolation; this file covers the tool functions in server.py that
call the backend client, then hand the response to workflow.py and return the
wrapped envelope. Every _client method is monkeypatched — no httpx, no DB.
"""
import inspect

import pytest

import mcp_server.server as srv

_COUNTRIES = {"job_country": "US", "fallback": False, "skipped": ["uk_base"]}


@pytest.fixture(autouse=True)
def _candidates(monkeypatch):
    """score_ats reads the country rule once after scoring; keep it off the network."""
    monkeypatch.setattr(srv._client, "ats_candidates", lambda job_id, include_other_countries=False: dict(_COUNTRIES))

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
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None, include_other_countries=False: [
        _score("alpha", 80.0), _score("beta", 60.0),
    ])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: {"mirror_wording": True})

    out = srv.score_ats("job1")

    assert [s["target_id"] for s in out["scores"]] == ["alpha", "beta"]
    assert out["recommendation"]["recommended"] == "alpha"
    assert out["next"]["state"] == "bases_scored"
    presets = [o for o in out["next"]["options"] if o["args"].get("use_presets")][0]
    assert presets["tool"] == "create_tailoring_session"
    assert presets["args"] == {"job_id": "job1", "base_resume": "alpha", "use_presets": True}
    assert presets["detail"] == {"mirror_wording": True}


def test_score_ats_reports_the_countries_block_between_recommendation_and_next(monkeypatch):
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha")])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    out = srv.score_ats("job1")

    assert out["countries"] == _COUNTRIES
    assert list(out) == ["scores", "recommendation", "countries", "next"]
    assert list(srv.score_ats("job1", brief=True)) == ["scores", "recommendation", "countries", "next"]


def test_score_ats_omits_countries_for_an_explicit_target(monkeypatch):
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha")])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    monkeypatch.setattr(
        srv._client, "ats_candidates",
        lambda job_id: pytest.fail("a target_id scores that target; the country rule is not consulted"),
    )

    out = srv.score_ats("job1", target_type="base_resume", target_id="alpha")

    assert "countries" not in out
    assert list(out) == ["scores", "recommendation", "next"]


def test_score_ats_forwards_include_other_countries(monkeypatch):
    seen = []
    monkeypatch.setattr(
        srv._client, "score_ats",
        lambda job_id, target_type=None, target_id=None, include_other_countries=False: seen.append(include_other_countries) or [_score("alpha")],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})

    srv.score_ats("job1", include_other_countries=True)
    srv.score_ats("job1")

    assert seen == [True, False]


def test_score_ats_countries_block_follows_include_other_countries(monkeypatch):
    monkeypatch.setattr(
        srv._client, "score_ats",
        lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha")],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    monkeypatch.setattr(
        srv._client, "ats_candidates",
        lambda job_id, include_other_countries=False: {
            "job_country": "US", "fallback": False,
            "skipped": [] if include_other_countries else ["uk_base"],
        },
    )

    assert srv.score_ats("job1")["countries"]["skipped"] == ["uk_base"]
    assert srv.score_ats("job1", include_other_countries=True)["countries"]["skipped"] == []


def test_score_ats_country_lookup_failing_after_the_scores_landed_is_null(monkeypatch):
    from mcp_server.client import BackendError

    def down(job_id, include_other_countries=False):
        raise BackendError("Backend returned 500", status_code=500)

    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha")])
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    monkeypatch.setattr(srv._client, "ats_candidates", down)

    out = srv.score_ats("job1")

    assert out["countries"] is None
    assert out["scores"] and out["recommendation"]["recommended"] == "alpha"


def test_set_base_resume_identity_tool_forwards_only_what_was_given(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client, "set_base_resume_identity", lambda slug, **kw: seen.update(slug=slug, **{k: v for k, v in kw.items() if v is not None}) or {"slug": slug}
    )

    srv.set_base_resume_identity("uk_ds", countries=["GB"], company="")

    assert seen == {"slug": "uk_ds", "countries": ["GB"], "company": ""}


def test_set_base_resume_identity_tool_forwards_color_hue(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client, "set_base_resume_identity", lambda slug, **kw: seen.update(slug=slug, **{k: v for k, v in kw.items() if v is not None}) or {"slug": slug}
    )

    srv.set_base_resume_identity("uk_ds", color_hue=230)

    assert seen == {"slug": "uk_ds", "color_hue": 230}


def test_score_ats_brief_never_reads_settings_or_profile(monkeypatch):
    # The whole point of `brief` is a triage loop paying no extra HTTP round
    # trip. If either settings call fires, the mutation is invisible to a
    # test that only checks the return value — assert the calls never happen.
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha")])

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
    monkeypatch.setattr(srv._client, "score_ats", lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha")])
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
    # no gaps at all -> the tailor; the agent app writes by default, so it is offered, not called
    assert [o["tool"] for o in out["next"]["options"]] == ["tailor_session"]
    assert out["next"]["call"] is None

    monkeypatch.setattr(
        srv._client, "get_mcp_workflow_settings", lambda: {"hints": True, "writer": "maestro"}
    )
    assert srv.resolve_gaps(tailoring_session_id="s1", resolutions=[])["next"]["call"] == (
        "tailor_session"
    )


def _settings_reads(monkeypatch, settings):
    reads = []
    monkeypatch.setattr(
        srv._client, "get_mcp_workflow_settings", lambda: reads.append(1) or dict(settings)
    )
    return reads


@pytest.mark.parametrize("settings, writer", [
    ({"hints": True, "writer": "maestro"}, "maestro"),
    ({"hints": True, "writer": "agent"}, "agent"),
    ({"hints": True}, "agent"),
    ({"hints": True, "writer": "someone else"}, "agent"),  # _writer is the one normalisation point
])
def test_session_hints_say_who_writes_from_one_settings_read(monkeypatch, settings, writer):
    session = {"id": "s1", "gaps_json": {"categories": []}, "resolutions_json": []}
    monkeypatch.setattr(srv._client, "resolve_gaps", lambda session_id, items: session)
    monkeypatch.setattr(
        srv._client, "create_tailoring_session", lambda job_id, base_resume, enrich=True: session
    )

    for call in (lambda: srv.resolve_gaps(tailoring_session_id="s1", resolutions=[]),
                 lambda: srv.create_tailoring_session("job1", "hybrid")):
        reads = _settings_reads(monkeypatch, settings)
        out = call()
        assert out["next"]["options"][0]["detail"]["writer"] == writer
        assert len(reads) == 1


# ---------- tailor_session ----------


def test_tailor_session_wraps_with_render_hint(monkeypatch):
    monkeypatch.setattr(
        srv._client, "tailor_session",
        lambda sid, user_prompt=None, ops=None, no_new_text=False: {"session": {"id": sid, "application_id": "app1"}, "compare": None},
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})

    out = srv.tailor_session(tailoring_session_id="s1")

    assert out["next"]["call"] == "render_pdf"
    assert out["next"]["options"][0]["args"] == {"target_type": "application", "target_id": "app1"}


_READY_STATUS = {"autofill": {"done": True, "readiness": 1.0, "groups": {}, "blocking": []}}


def _tailored(pdf_ready, **extra):
    return lambda sid, user_prompt=None, ops=None, no_new_text=False: {
        "session": {"id": sid, "application_id": "app1"}, "compare": None,
        "pdf_ready": pdf_ready, **extra,
    }


def test_tailor_session_with_its_pdf_made_ends_on_apply_readiness(monkeypatch):
    monkeypatch.setattr(srv._client, "tailor_session", _tailored(True))
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_setup_status", lambda: _READY_STATUS)

    out = srv.tailor_session(tailoring_session_id="s1", no_new_text=True)

    assert out["pdf_ready"] is True
    assert out["next"]["call"] is None
    assert out["next"]["state"] == "rendered"
    assert out["next"]["readiness"]["autofill_ready"] is True
    assert all(o["tool"] != "render_pdf" for o in out["next"]["options"])


def test_tailor_session_with_its_pdf_made_keeps_the_answers_left(monkeypatch):
    left = [{"gap_id": "g1", "action": "user_input", "skill": "Build ML models"}]
    monkeypatch.setattr(srv._client, "tailor_session", _tailored(True, answers_left_to_ops=left))
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_setup_status", lambda: _READY_STATUS)

    out = srv.tailor_session(tailoring_session_id="s1", no_new_text=True)

    assert [o["tool"] for o in out["next"]["options"]] == ["edit_application"]
    assert out["next"]["readiness"]["autofill_ready"] is True
    assert out["next"]["ask_user"] and out["next"]["blocking"] is True


@pytest.mark.parametrize("pdf_ready", [True, False])
def test_tailor_session_with_the_callers_ops_asks_no_question_about_the_answers(
    monkeypatch, pdf_ready
):
    """The ops may have written every listed answer, so the edit is an option, never a question."""
    left = [{"gap_id": "g1", "action": "user_input", "skill": "Build ML models"}]
    monkeypatch.setattr(srv._client, "tailor_session", _tailored(pdf_ready, answers_left_to_ops=left))
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    monkeypatch.setattr(srv._client, "get_setup_status", lambda: _READY_STATUS)
    ops = [{"op": "replace_summary", "text": "Builds forecasting models."}]

    out = srv.tailor_session(tailoring_session_id="s1", ops=ops)

    assert out["next"]["ask_user"] is None
    assert "edit_application" in [o["tool"] for o in out["next"]["options"]]
    if pdf_ready:
        assert out["next"]["call"] is None and out["next"]["blocking"] is False
        assert out["next"]["readiness"]["autofill_ready"] is True
    else:
        assert out["next"]["call"] == "render_pdf"


def test_tailor_session_reads_setup_status_only_for_a_made_pdf_with_hints_on(monkeypatch):
    """The readiness facts cost one more request: none when the hint cannot use them."""
    def _boom():
        raise AssertionError("get_setup_status read when no hint could use it")

    monkeypatch.setattr(srv._client, "get_setup_status", _boom)
    monkeypatch.setattr(srv._client, "tailor_session", _tailored(False))
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    assert srv.tailor_session(tailoring_session_id="s1")["next"]["call"] == "render_pdf"

    monkeypatch.setattr(srv._client, "tailor_session", _tailored(True))
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    assert srv.tailor_session(tailoring_session_id="s1")["next"] is None


def test_tailor_session_next_is_null_without_an_application_id(monkeypatch):
    # If tailor() ever returns a session with no application_id, there is no
    # PDF to point render_pdf at — the hint must degrade to null, not crash.
    monkeypatch.setattr(
        srv._client, "tailor_session",
        lambda sid, user_prompt=None, ops=None, no_new_text=False: {"session": {"id": sid}, "compare": None},
    )

    out = srv.tailor_session(tailoring_session_id="s1")

    assert out["next"] is None


# ---------- create_tailoring_session(use_presets=True) ----------


def _presets_session(monkeypatch, filled, *, hints=True, profile=None, calls=None):
    """create_tailoring_session(use_presets=True): create, then fill from the presets."""
    calls = [] if calls is None else calls
    monkeypatch.setattr(
        srv._client, "create_tailoring_session",
        lambda job_id, base_resume, enrich=True: (
            calls.append(("create", job_id, base_resume, enrich)), {"id": "s1"}
        )[1],
    )
    monkeypatch.setattr(
        srv._client, "apply_quick_tailor_profile",
        lambda session_id: (calls.append(("apply", session_id)), filled)[1],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": hints})
    if profile is not None:
        monkeypatch.setattr(srv._client, "get_quick_tailor_profile", lambda: profile)


def test_presets_create_without_enrich_then_fill(monkeypatch):
    calls = []
    _presets_session(monkeypatch, {"id": "s1", "gaps_json": {}, "resolutions_json": []},
                     hints=False, calls=calls)

    out = srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    assert calls == [("create", "job1", "hybrid", False), ("apply", "s1")]
    assert out["id"] == "s1"


def test_presets_keep_an_enrich_the_caller_asked_for(monkeypatch):
    calls = []
    _presets_session(monkeypatch, {"id": "s1", "gaps_json": {}, "resolutions_json": []},
                     hints=False, calls=calls)

    srv.create_tailoring_session("job1", "hybrid", enrich=True, use_presets=True)

    assert calls == [("create", "job1", "hybrid", True), ("apply", "s1")]


def test_without_presets_nothing_is_filled(monkeypatch):
    calls = []
    _presets_session(monkeypatch, {"id": "s1"}, hints=False, calls=calls)

    srv.create_tailoring_session("job1", "hybrid")

    assert calls == [("create", "job1", "hybrid", False)]


def test_presets_return_the_filled_session_wrapped(monkeypatch):
    filled = {"id": "s1", "gaps_json": {"categories": []}, "resolutions_json": []}
    _presets_session(monkeypatch, filled, profile={"instruction": ""})

    out = srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    assert out["id"] == "s1"
    assert "next" in out
    assert [o["tool"] for o in out["next"]["options"]] == ["tailor_session"]


def test_a_failed_presets_fill_names_the_session_it_started(monkeypatch):
    """The session exists once creation returned; a retry that loses its id strands it."""
    from mcp.server.mcpserver.exceptions import ToolError

    from mcp_server.client import BackendError

    def stale(session_id):
        raise BackendError("Backend returned 409: This gap analysis is out of date.", status_code=409)

    _presets_session(monkeypatch, {})
    monkeypatch.setattr(srv._client, "apply_quick_tailor_profile", stale)

    with pytest.raises(ToolError) as exc:
        srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    message = str(exc.value)
    assert "s1" in message
    assert "This gap analysis is out of date" in message
    assert ".." not in message
    assert "Call create_tailoring_session again (it replaces it)" in message
    # resolve_gaps gets the same 409 on a stale or closed session: no use here.
    assert "resolve_gaps" not in message


async def test_a_failed_presets_fill_reaches_the_agent_whole(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    from mcp_server.client import BackendError

    def stale(session_id):
        raise BackendError("Backend returned 409: This gap analysis is out of date.", status_code=409)

    _presets_session(monkeypatch, {})
    monkeypatch.setattr(srv._client, "apply_quick_tailor_profile", stale)

    with pytest.raises(ToolError) as exc:
        await srv.mcp.call_tool(
            "create_tailoring_session", {"job_id": "job1", "base_resume": "hybrid", "use_presets": True}
        )

    assert "The gap analysis s1 was started" in str(exc.value)


def test_presets_skip_the_profile_fetch_when_hints_are_off(monkeypatch):
    _presets_session(monkeypatch, {"id": "s1", "gaps_json": {}, "resolutions_json": []}, hints=False)

    def _boom():
        raise AssertionError("get_quick_tailor_profile must not be called when hints are off")

    monkeypatch.setattr(srv._client, "get_quick_tailor_profile", _boom)

    out = srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    assert out["next"] is None


def test_presets_thread_the_instruction_when_the_session_has_no_note(monkeypatch):
    filled = {
        "id": "s1",
        "gaps_json": {"categories": [{"name": "missing_skill", "gaps": [{"gap_id": "g1"}]}]},
        "resolutions_json": [{"gap_id": "g1", "action": "skip", "payload": {}}],
    }
    _presets_session(monkeypatch, filled, profile={"instruction": "Keep it punchy."})

    out = srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    tailor_option = [o for o in out["next"]["options"] if o["tool"] == "tailor_session"][0]
    assert tailor_option["args"]["user_prompt"] == "Keep it punchy."


def test_presets_hint_says_who_writes_from_one_settings_read(monkeypatch):
    filled = {"id": "s1", "gaps_json": {"categories": []}, "resolutions_json": []}
    _presets_session(monkeypatch, filled, profile={"instruction": ""})
    reads = _settings_reads(monkeypatch, {"hints": True, "writer": "maestro"})

    out = srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    assert out["next"]["options"][0]["detail"]["writer"] == "maestro"
    assert len(reads) == 1


def test_presets_do_not_override_the_sessions_own_note(monkeypatch):
    filled = {
        "id": "s1",
        "user_prompt": "Already told it what I want.",
        "gaps_json": {"categories": [{"name": "missing_skill", "gaps": [{"gap_id": "g1"}]}]},
        "resolutions_json": [{"gap_id": "g1", "action": "skip", "payload": {}}],
    }
    _presets_session(monkeypatch, filled, profile={"instruction": "A different instruction."})

    out = srv.create_tailoring_session("job1", "hybrid", use_presets=True)

    tailor_option = [o for o in out["next"]["options"] if o["tool"] == "tailor_session"][0]
    assert "user_prompt" not in tailor_option["args"]


def _presets_text():
    """The docstring plus the use_presets parameter's description, where the detail lives."""
    from mcp_server.server import _USE_PRESETS_FIELD

    return " ".join(((srv.create_tailoring_session.__doc__ or "") + " " + _USE_PRESETS_FIELD.description).split())


def test_presets_text_states_no_ai_writes_and_no_prose():
    text = _presets_text()
    assert "no AI" in text
    assert "does not write resume text" in text


def test_presets_text_carries_the_honesty_rule():
    text = _presets_text().lower()
    assert "fabricate" in text
    assert "skills category" in text
    assert "never as an experience or project" in text


def test_presets_text_documents_the_409s():
    text = _presets_text().lower()
    assert "409" in text
    assert "stale" in text
    assert "fatal health gate" in text


def test_presets_text_explains_zero_planned_resolutions():
    text = _presets_text().lower()
    assert "not an error" in text
    assert "resolve_gaps" in text


# ---------- profile registration ----------


def test_quick_tailor_is_registered_nowhere():
    """Its work is create_tailoring_session(use_presets=True) now."""
    from mcp_server.profiles import PROFILE_ALLOWLISTS

    assert "quick_tailor" not in set(srv.list_registered_tool_names("full"))
    assert all("quick_tailor" not in allow for allow in PROFILE_ALLOWLISTS.values() if allow)


def test_score_ats_skips_the_profile_fetch_when_hints_are_off(monkeypatch):
    """The quick-tailor profile fills the presets option's `detail` and
    nothing else, so fetching it with hints off is a discarded round-trip.
    Passed as a keyword ARGUMENT it would be evaluated unconditionally — that
    is the trap this pins."""
    monkeypatch.setattr(
        srv._client, "score_ats",
        lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha", 80.0)],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": False})
    calls = []
    monkeypatch.setattr(
        srv._client, "get_quick_tailor_profile", lambda: calls.append(1) or {},
    )

    out = srv.score_ats("job1")

    assert out["next"] is None
    assert calls == [], "fetched a quick-tailor profile it then discarded"


def test_score_ats_skips_the_profile_fetch_when_tailoring_is_unregistered(monkeypatch):
    """A hunt-profile triage loop never gets a presets option, so the
    profile behind it is pure waste — twenty postings, twenty discarded calls."""
    from mcp_server.profiles import HUNT_TOOLS

    monkeypatch.setattr(srv, "_active_allowed_tools", lambda: HUNT_TOOLS)
    monkeypatch.setattr(
        srv._client, "score_ats",
        lambda job_id, target_type=None, target_id=None, include_other_countries=False: [_score("alpha", 80.0)],
    )
    monkeypatch.setattr(srv._client, "get_mcp_workflow_settings", lambda: {"hints": True})
    calls = []
    monkeypatch.setattr(
        srv._client, "get_quick_tailor_profile", lambda: calls.append(1) or {},
    )

    out = srv.score_ats("job1")

    assert calls == [], "fetched a profile no option could display"
    assert [o["tool"] for o in out["next"]["options"]] == []
