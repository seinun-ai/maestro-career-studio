import json
import re

import pytest

from mcp_server import profiles, workflow


def _score(slug, composite, subscores=None, coverage=None):
    return {
        "target_type": "base_resume",
        "target_id": slug,
        "composite": composite,
        "subscores_json": subscores or {},
        "coverage_warning": coverage,
    }


def test_ranks_by_composite_descending():
    out = workflow.rank_bases([_score("a", 61.0), _score("b", 74.5), _score("c", 70.0)])
    assert out["order"] == ["b", "c", "a"]
    assert out["recommended"] == "b"


def test_close_call_is_flagged_when_the_margin_is_thin():
    out = workflow.rank_bases([_score("a", 70.0), _score("b", 71.0)])
    assert out["close_call"] is True
    assert out["margin"] == pytest.approx(1.0)


def test_a_clear_win_is_not_a_close_call():
    out = workflow.rank_bases([_score("a", 82.0), _score("b", 61.0)])
    assert out["close_call"] is False


def test_reasons_name_the_layers_carrying_the_lead():
    out = workflow.rank_bases([
        _score("a", 80.0, {"keyword": 30.0, "title": 10.0}),
        _score("b", 70.0, {"keyword": 22.0, "title": 9.5}),
    ])
    assert out["reasons"][0] == {"layer": "keyword", "delta": pytest.approx(8.0)}


def test_ties_break_on_slug_so_the_pick_is_stable():
    first = workflow.rank_bases([_score("zeta", 70.0), _score("alpha", 70.0)])
    second = workflow.rank_bases([_score("alpha", 70.0), _score("zeta", 70.0)])
    assert first["recommended"] == second["recommended"] == "alpha"


def test_coverage_warning_is_a_table_level_caveat():
    out = workflow.rank_bases([
        _score("a", 40.0, coverage="Your resume shows only 1 of this job's 8 skills (13%)."),
        _score("b", 38.0, coverage="Your resume shows only 1 of this job's 8 skills (13%)."),
    ])
    assert out["coverage_warning"] == "Your resume shows only 1 of this job's 8 skills (13%)."


def test_application_rows_are_ignored():
    out = workflow.rank_bases([
        {"target_type": "application", "target_id": "app1", "composite": 99.0},
        _score("a", 50.0),
    ])
    assert out["order"] == ["a"]


def test_single_base_has_no_margin_and_is_not_close():
    out = workflow.rank_bases([_score("only", 55.0)])
    assert out["recommended"] == "only"
    assert out["margin"] is None
    assert out["close_call"] is False


def test_empty_input_recommends_nothing():
    assert workflow.rank_bases([])["recommended"] is None


def test_malformed_composite_sorts_last_instead_of_raising():
    out = workflow.rank_bases([
        _score("good", 65.0),
        {
            "target_type": "base_resume",
            "target_id": "corrupt",
            "composite": "not-a-number",
            "subscores_json": {},
            "coverage_warning": None,
        },
    ])
    assert out["order"] == ["good", "corrupt"]
    assert out["recommended"] == "good"


def test_reasons_are_capped_even_when_every_layer_favors_the_winner():
    # All five REAL layers, all favouring the winner — five candidates against a
    # cap of three. Synthetic layer names would be filtered out by SCORE_LAYERS
    # before the cap could ever be reached, so this has to use the real set.
    out = workflow.rank_bases([
        _score("a", 90.0, {layer: 10.0 for layer in workflow.SCORE_LAYERS}),
        _score("b", 50.0, {layer: 1.0 for layer in workflow.SCORE_LAYERS}),
    ])
    assert len(workflow.SCORE_LAYERS) > workflow.MAX_REASONS, "cap would be untestable"
    assert len(out["reasons"]) == workflow.MAX_REASONS


def test_a_layer_the_runner_up_was_never_scored_on_is_not_a_reason():
    out = workflow.rank_bases([
        _score("a", 80.0, {"keyword": 30.0, "only_on_winner": 99.0}),
        _score("b", 70.0, {"keyword": 22.0}),
    ])
    layers_named = [r["layer"] for r in out["reasons"]]
    assert "only_on_winner" not in layers_named


def test_a_layer_where_the_winner_trails_is_not_a_reason():
    out = workflow.rank_bases([
        _score("a", 80.0, {"keyword": 30.0, "format": 2.0}),
        _score("b", 70.0, {"keyword": 22.0, "format": 9.0}),
    ])
    layers_named = [r["layer"] for r in out["reasons"]]
    assert "format" not in layers_named
    assert layers_named == ["keyword"]


def test_coverage_warning_can_differ_across_bases_and_only_the_winner_counts():
    # The threshold in _calc_coverage_signal compares each resume's OWN
    # matched-skill ratio against the same job, so two bases can legitimately
    # disagree on coverage even though they were scored against one JD.
    out = workflow.rank_bases([
        _score("a", 80.0, coverage=None),
        _score("b", 50.0, coverage="Your resume shows only 1 of this job's 8 skills (13%)."),
    ])
    assert out["recommended"] == "a"
    assert out["coverage_warning"] is None


# ---- next-step hint envelope ------------------------------------------------


def _ranking():
    return workflow.rank_bases([_score("alpha", 80.0), _score("beta", 60.0)])


def _gap(gap_id):
    return {"gap_id": gap_id, "category": "missing_skill"}


def _session(session_id="s1", gap_ids=(), resolved_ids=()):
    return {
        "id": session_id,
        "gaps_json": {"categories": [{"name": "missing_skill", "gaps": [_gap(g) for g in gap_ids]}]},
        "resolutions_json": [{"gap_id": g, "action": "skip", "payload": {}} for g in resolved_ids],
    }


def _autofill_setup_status(*, ready):
    # Real shape from app/schemas/setup_status.py: SetupStatus.autofill is an
    # AutofillStep {done, readiness, groups: {name: {answered, answerable}}, blocking}.
    if ready:
        groups = {
            "personal": {"answered": 9, "answerable": 9},
            "work_auth": {"answered": 4, "answerable": 4},
            "preferences": {"answered": 5, "answerable": 5},
        }
        return {"autofill": {"done": True, "readiness": 1.0, "groups": groups, "blocking": []}}
    groups = {
        "personal": {"answered": 9, "answerable": 9},
        "work_auth": {"answered": 0, "answerable": 4},
        "preferences": {"answered": 5, "answerable": 5},
    }
    return {
        "autofill": {"done": False, "readiness": 0.85, "groups": groups, "blocking": ["work_auth"]}
    }


def test_scoring_hint_offers_and_never_asks():
    hint = workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={"mirror_wording": True},
        allowed_tools=None, hints_enabled=True, brief=False,
    )
    assert hint["blocking"] is False
    assert hint["ask_user"] is None
    assert hint["offer"]


def test_scoring_hint_carries_the_quick_tailor_profile():
    hint = workflow.next_after_scores(
        _ranking(), job_id="j1",
        quick_profile={"mirror_wording": True, "keywords_into_skills": False},
        allowed_tools=None, hints_enabled=True, brief=False,
    )
    presets = [o for o in hint["options"] if o["args"].get("use_presets")][0]
    assert presets["detail"]["mirror_wording"] is True
    assert presets["detail"]["keywords_into_skills"] is False


def test_scoring_hint_offers_the_presets_as_a_switch_on_create_tailoring_session():
    hint = workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={},
        allowed_tools=None, hints_enabled=True, brief=False,
    )
    presets, custom = hint["options"]
    top = _ranking()["recommended"]
    assert presets["tool"] == custom["tool"] == "create_tailoring_session"
    assert presets["args"] == {"job_id": "j1", "base_resume": top, "use_presets": True}
    assert presets["label"] == f"Tailor {top} with the saved presets"
    assert custom["args"] == {"job_id": "j1", "base_resume": top, "enrich": False}
    assert "quick_tailor" not in json.dumps(hint)
    assert hint["offer"].count("create_tailoring_session") == 1
    assert "use_presets" in hint["offer"]


def test_hunt_profile_never_names_a_tool_it_does_not_register():
    from mcp_server.profiles import HUNT_TOOLS

    # If this ever stops being true, the test below is vacuous — the whole
    # point is that the unfiltered options contain a tool HUNT_TOOLS excludes.
    unfiltered = workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={},
        allowed_tools=None, hints_enabled=True, brief=False,
    )
    assert any(o["tool"] not in HUNT_TOOLS for o in unfiltered["options"])

    hint = workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={},
        allowed_tools=HUNT_TOOLS, hints_enabled=True, brief=False,
    )
    assert all(o["tool"] in HUNT_TOOLS for o in (hint or {}).get("options", []))


def test_brief_suppresses_the_hint():
    assert workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={},
        allowed_tools=None, hints_enabled=True, brief=True,
    ) is None


def test_the_user_switch_beats_everything():
    assert workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={},
        allowed_tools=None, hints_enabled=False, brief=False,
    ) is None


def test_no_recommendation_means_no_hint():
    empty_ranking = workflow.rank_bases([])
    assert workflow.next_after_scores(
        empty_ranking, job_id="j1", quick_profile={},
        allowed_tools=None, hints_enabled=True, brief=False,
    ) is None


def test_session_hint_asks_when_gaps_remain():
    hint = workflow.next_after_session(
        _session(gap_ids=["g1", "g2"], resolved_ids=["g1"]),
        allowed_tools=None, hints_enabled=True,
    )
    assert hint["state"] == "gaps_pending"
    assert hint["ask_user"]
    assert hint["call"] is None
    tools = {o["tool"] for o in hint["options"]}
    assert tools == {"resolve_gaps", "tailor_session"}


def test_session_hint_calls_tailor_when_nothing_is_left_unresolved():
    hint = workflow.next_after_session(
        _session(gap_ids=["g1", "g2"], resolved_ids=["g1", "g2"]),
        allowed_tools=None, hints_enabled=True,
    )
    assert hint["state"] == "gaps_resolved"
    assert hint["ask_user"] is None
    assert hint["call"] == "tailor_session"


def test_session_hint_with_no_gaps_at_all_goes_straight_to_tailor():
    hint = workflow.next_after_session(
        _session(gap_ids=[], resolved_ids=[]), allowed_tools=None, hints_enabled=True,
    )
    assert hint["call"] == "tailor_session"


def test_apply_profile_tools_never_name_resolve_gaps_outside_apply_profile():
    from mcp_server.profiles import HUNT_TOOLS

    unfiltered = workflow.next_after_session(
        _session(gap_ids=["g1"], resolved_ids=[]), allowed_tools=None, hints_enabled=True,
    )
    assert any(o["tool"] not in HUNT_TOOLS for o in unfiltered["options"])

    hint = workflow.next_after_session(
        _session(gap_ids=["g1"], resolved_ids=[]), allowed_tools=HUNT_TOOLS, hints_enabled=True,
    )
    assert hint["options"] == []


def test_session_hint_threads_the_instruction_when_the_session_has_no_note():
    session = _session(gap_ids=["g1"], resolved_ids=["g1"])
    assert session.get("user_prompt") is None
    hint = workflow.next_after_session(
        session, allowed_tools=None, hints_enabled=True,
        instruction="Keep it concise and metrics-forward.",
    )
    tailor_option = hint["options"][0]
    assert tailor_option["tool"] == "tailor_session"
    assert tailor_option["args"]["user_prompt"] == "Keep it concise and metrics-forward."


def test_session_hint_never_overrides_the_sessions_own_note():
    session = _session(gap_ids=["g1"], resolved_ids=["g1"])
    session["user_prompt"] = "Already told it what I want."
    hint = workflow.next_after_session(
        session, allowed_tools=None, hints_enabled=True,
        instruction="A different, profile-sourced instruction.",
    )
    tailor_option = hint["options"][0]
    assert "user_prompt" not in tailor_option["args"]


def test_session_hint_with_no_instruction_carries_no_user_prompt_arg():
    hint = workflow.next_after_session(
        _session(gap_ids=["g1"], resolved_ids=["g1"]),
        allowed_tools=None, hints_enabled=True,
    )
    tailor_option = hint["options"][0]
    assert "user_prompt" not in tailor_option["args"]


def _tailor_option(*, writer=None, gap_ids=("g1",), resolved_ids=("g1",)):
    kw = {} if writer is None else {"writer": writer}
    hint = workflow.next_after_session(
        _session(gap_ids=gap_ids, resolved_ids=resolved_ids),
        allowed_tools=None, hints_enabled=True, **kw,
    )
    return next(o for o in hint["options"] if o["tool"] == "tailor_session")


def test_session_hint_says_the_agent_app_writes_the_edits_by_default():
    assert _tailor_option() == _tailor_option(writer="agent")
    option = _tailor_option(writer="agent")
    assert option["detail"]["writer"] == "agent"
    assert "ops" in option["label"] and "no_new_text" in option["label"]
    note = option["detail"]["note"]
    assert "ops=[...]" in note and "no_new_text=true" in note
    assert "answers_left_to_ops" in note
    assert option["args"] == {"tailoring_session_id": "s1"}


def test_session_hint_says_maestros_ai_writes_the_edits_when_it_is_the_writer():
    option = _tailor_option(writer="maestro")
    assert option["detail"]["writer"] == "maestro"
    assert "Maestro's AI writes the edits" in option["label"]
    note = option["detail"]["note"]
    assert "ops omitted" in note and "user's key" in note
    assert "no_new_text" not in json.dumps(option)
    assert option["args"] == {"tailoring_session_id": "s1"}


def test_session_hint_names_who_writes_while_gaps_remain_too():
    for writer in ("agent", "maestro"):
        option = _tailor_option(writer=writer, gap_ids=("g1", "g2"), resolved_ids=("g1",))
        assert option["detail"]["writer"] == writer


def test_session_hint_writer_takes_the_settings_two_values():
    import typing

    from app.schemas.mcp_workflow import Writer

    assert typing.get_type_hints(workflow.next_after_session)["writer"] == workflow.Writer
    assert typing.get_args(workflow.Writer) == typing.get_args(Writer) == ("agent", "maestro")


def test_session_hint_brief_and_switch_suppress():
    assert workflow.next_after_session(
        _session(), allowed_tools=None, hints_enabled=True, brief=True,
    ) is None
    assert workflow.next_after_session(
        _session(), allowed_tools=None, hints_enabled=False,
    ) is None


def test_mid_arc_hints_may_ask():
    hint = workflow.next_after_tailor(application_id="a1", allowed_tools=None, hints_enabled=True)
    assert hint["call"] == "render_pdf"


def test_tailor_hint_names_render_pdf_with_the_application_id():
    hint = workflow.next_after_tailor(application_id="a1", allowed_tools=None, hints_enabled=True)
    option = hint["options"][0]
    assert option["tool"] == "render_pdf"
    assert option["args"] == {"target_type": "application", "target_id": "a1"}


_LEFT = [
    {"gap_id": "coverage:0", "action": "user_input", "skill": "Build ML models"},
    {"gap_id": "wording:1", "action": "add_keyword", "skill": "forecasting"},
]


def test_tailor_hint_lists_the_answers_no_new_text_left_before_the_render_and_calls_neither():
    """With no_new_text the list is what was left: writing those answers clears the PDF, so
    the render comes after them; writing them may need the user, so nothing is the one call."""
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True, no_new_text=True,
        keywords_added=["Snowflake"], answers_left_to_ops=_LEFT,
    )
    carry, render = hint["options"]
    assert hint["call"] is None
    assert hint["blocking"] is True
    assert carry["tool"] == "edit_application"
    assert carry["args"] == {"application_id": "a1"}
    assert carry["detail"]["answers_left_to_ops"] == _LEFT
    assert render["tool"] == "render_pdf"
    assert render["detail"]["keywords_added"] == ["Snowflake"]
    # The decision is the user's; the question names no tool.
    assert hint["ask_user"].startswith("2 saved answer(s)") and hint["ask_user"].endswith("?")
    assert _named_tools({"q": hint["ask_user"]}) == set()
    note = carry["detail"]["note"]
    assert "need wording" in note
    assert "add_keyword" in note and "rewritten" in note


_OPS_LEFT = [{"gap_id": "coverage:0", "action": "user_input", "skill": "Build ML models"}]


def test_tailor_hint_after_the_callers_ops_calls_the_render_and_asks_nothing():
    """With ops the list is every user_input/attach_project answer, written by the ops or
    not, so the edit is a conditional option: no question, and the render is the call."""
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True,
        keywords_added=["Snowflake"], answers_left_to_ops=_OPS_LEFT,
    )
    assert hint["call"] == "render_pdf"
    assert hint["blocking"] is True
    assert hint["ask_user"] is None
    assert {option["tool"] for option in hint["options"]} == {"edit_application", "render_pdf"}
    carry = next(o for o in hint["options"] if o["tool"] == "edit_application")
    assert carry["detail"]["answers_left_to_ops"] == _OPS_LEFT
    note = carry["detail"]["note"]
    assert "need wording" not in note
    assert "ops are given" in note and "where the ops wrote it" in note
    render = next(o for o in hint["options"] if o["tool"] == "render_pdf")
    assert render["detail"]["keywords_added"] == ["Snowflake"]


def test_tailor_hint_after_the_callers_ops_with_its_pdf_made_ends_on_apply_readiness():
    status = _autofill_setup_status(ready=True)
    render = workflow.next_after_render(setup_status=status, allowed_tools=None, hints_enabled=True)
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True,
        pdf_ready=True, setup_status=status, answers_left_to_ops=_OPS_LEFT,
    )
    assert [option["tool"] for option in hint["options"]] == ["edit_application"]
    assert hint["call"] is None and hint["blocking"] is False and hint["ask_user"] is None
    assert hint["state"] == "rendered"
    assert hint["readiness"] == render["readiness"]
    assert hint["offer"] == render["offer"]
    assert "render_pdf" not in json.dumps(hint)


def test_tailor_hint_calls_nothing_when_only_the_answers_can_be_written():
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=frozenset({"edit_application"}), hints_enabled=True,
        no_new_text=True, answers_left_to_ops=_LEFT,
    )
    assert [option["tool"] for option in hint["options"]] == ["edit_application"]
    assert hint["call"] is None


def test_tailor_hint_without_edit_application_offers_the_render_and_still_calls_nothing():
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=frozenset({"render_pdf"}), hints_enabled=True,
        no_new_text=True, answers_left_to_ops=_LEFT,
    )
    assert [option["tool"] for option in hint["options"]] == ["render_pdf"]
    assert hint["call"] is None


def test_tailor_hint_offers_render_pdf_only_when_the_tailor_made_no_pdf():
    """tailor_session renders the PDF itself; render_pdf is the step only when that failed."""
    made = workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True, pdf_ready=True,
        setup_status=_autofill_setup_status(ready=True),
    )
    assert "render_pdf" not in json.dumps(made)
    assert made["call"] is None and made["options"] == []
    assert made["blocking"] is False
    failed = workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True, pdf_ready=False,
    )
    assert failed["call"] == "render_pdf"
    assert [option["tool"] for option in failed["options"]] == ["render_pdf"]
    assert "readiness" not in failed


@pytest.mark.parametrize("ready", [True, False])
@pytest.mark.parametrize("profile", ["full", "tailor"])
@pytest.mark.parametrize("no_new_text", [True, False])
def test_a_clean_tailor_with_its_pdf_made_ends_on_apply_readiness(ready, profile, no_new_text):
    """The arc's last step: with the PDF made and nothing left, the hint is render_pdf's."""
    allow = profiles.allowed_tools(profile)
    status = _autofill_setup_status(ready=ready)
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=allow, hints_enabled=True,
        pdf_ready=True, setup_status=status, no_new_text=no_new_text,
    )
    assert hint == workflow.next_after_render(setup_status=status, allowed_tools=allow, hints_enabled=True)
    assert hint["readiness"]["autofill_ready"] is ready


def test_a_no_new_text_tailor_with_its_pdf_made_and_answers_left_carries_both():
    status = _autofill_setup_status(ready=False)
    render = workflow.next_after_render(setup_status=status, allowed_tools=None, hints_enabled=True)
    hint = workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True, no_new_text=True,
        pdf_ready=True, setup_status=status, answers_left_to_ops=_LEFT,
    )
    assert [option["tool"] for option in hint["options"]] == ["edit_application"]
    assert hint["call"] is None and hint["blocking"] is True
    assert hint["ask_user"].endswith("?")
    assert hint["readiness"] == render["readiness"]
    assert hint["offer"] == render["offer"]
    assert "render_pdf" not in json.dumps(hint)


def test_tailor_hint_brief_and_switch_suppress():
    assert workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=True, brief=True
    ) is None
    assert workflow.next_after_tailor(
        application_id="a1", allowed_tools=None, hints_enabled=False
    ) is None


def test_apply_hint_reports_readiness_and_conditions_the_offer():
    hint = workflow.next_after_render(
        setup_status=_autofill_setup_status(ready=False),
        allowed_tools=None, hints_enabled=True,
    )
    assert hint["readiness"]["autofill_ready"] is False
    assert "browser tools" in hint["offer"]


def test_apply_hint_names_upload_and_consent_tools_not_the_playbook():
    hint = workflow.next_after_render(
        setup_status=_autofill_setup_status(ready=True),
        allowed_tools=None, hints_enabled=True,
    )
    offer = hint["offer"]
    assert "prepare_application_pdf_upload" in offer
    assert "record_consent" in offer
    assert "mark_submitted" in offer
    assert "agent-apply.md" not in offer
    # Consent semantics survive the rewording: the tools RECORD the user's
    # decisions; the prose says so as a statement of what they do.
    assert "record_consent records the user's" in offer
    assert "mark_submitted records the user's" in offer


def test_apply_hint_reports_ready_when_setup_is_complete():
    hint = workflow.next_after_render(
        setup_status=_autofill_setup_status(ready=True),
        allowed_tools=None, hints_enabled=True,
    )
    assert hint["readiness"]["autofill_ready"] is True
    assert hint["readiness"]["blocking_groups"] == []


def test_apply_hint_names_the_blocking_group():
    hint = workflow.next_after_render(
        setup_status=_autofill_setup_status(ready=False),
        allowed_tools=None, hints_enabled=True,
    )
    assert "work_auth" in hint["readiness"]["blocking_groups"]
    assert "work_auth" in hint["readiness"]["incomplete_groups"]


def test_render_hint_brief_and_switch_suppress():
    status = _autofill_setup_status(ready=True)
    assert workflow.next_after_render(
        setup_status=status, allowed_tools=None, hints_enabled=True, brief=True
    ) is None
    assert workflow.next_after_render(
        setup_status=status, allowed_tools=None, hints_enabled=False
    ) is None


def test_score_layers_match_the_engines_composite_weights():
    """SCORE_LAYERS must equal the layers the composite is actually built from.

    Hardcoding the set keeps workflow.py pure, so this is the drift guard: add a
    layer to weights.yaml without adding it here and the winner's real lead goes
    unreported. Reads the engine's own config rather than restating it.
    """
    from app.services.ats.config import load_config

    assert workflow.SCORE_LAYERS == frozenset(load_config().weights["composite_weights"])


def test_diagnostics_in_subscores_are_never_reported_as_reasons():
    """subscores_json carries numeric DIAGNOSTICS alongside score layers.

    Shape copied from a real scored row. A live run reported
    "jd_skills_matched_count +4.0" as a reason one base beat another — a count
    difference presented to the user as a scoring margin. Unit fixtures used
    invented layer names like l1_keyword, so nothing caught it until a real
    score ran through.
    """
    real = {
        "keyword": 0.9091, "placement_recency": 0.2424, "semantic_fit": 0.8385,
        "title": 1.0, "format": 0.7143,
        "coverage_ratio": 0.8333, "jd_skills_matched_count": 5,
        "jd_skills_extracted_count": 6, "title_tier": "direct",
        "format_flags": [], "gate_warnings": [], "coverage_warning": None,
    }
    weaker = {
        "keyword": 0.18, "placement_recency": 0.2424, "semantic_fit": 0.55,
        "title": 0.4, "format": 0.7143,
        "coverage_ratio": 0.1667, "jd_skills_matched_count": 1,
        "jd_skills_extracted_count": 6, "title_tier": "none",
        "format_flags": [], "gate_warnings": [], "coverage_warning": None,
    }
    out = workflow.rank_bases([_score("win", 75.9, real), _score("lose", 46.2, weaker)])

    layers = [r["layer"] for r in out["reasons"]]
    assert layers, "a clear winner should report at least one reason"
    assert set(layers) <= workflow.SCORE_LAYERS
    for diagnostic in ("jd_skills_matched_count", "jd_skills_extracted_count", "coverage_ratio"):
        assert diagnostic not in layers


# ---- onboarding hints -------------------------------------------------------
# Fixture captured verbatim from POST /api/kb/ingest-parsed on a two-section
# resume (Acme Engineer + Orbit project) — 2026-08-12, cs_test_grok_onboard.

_INGEST_REPORT = {
    "entities": [
        {"id": "00a6d654-35de-44f9-9d9e-74f8145ffc2a", "kind": "experience",
         "title": "Engineer", "org": "Acme", "created": True},
        {"id": "9927db8d-510d-4eab-ab96-6464b3729f0a", "kind": "project",
         "title": "Orbit", "org": None, "created": True},
    ],
    "points": [
        {"id": "e8b0b6c6-1057-469b-b191-7ca0d7568b69",
         "entity_id": "00a6d654-35de-44f9-9d9e-74f8145ffc2a", "text": "Shipped the pipeline"},
        {"id": "fbf3e77d-6bc7-472f-a1da-b194d62e1f68",
         "entity_id": "9927db8d-510d-4eab-ab96-6464b3729f0a", "text": "Built Orbit"},
    ],
    "entities_created": 2,
    "entities_matched": 0,
    "points_created": 2,
    "duplicates_skipped": 0,
    "skills_merged": [],
    "warnings": [],
}

_INGEST_POINT_IDS = [p["id"] for p in _INGEST_REPORT["points"]]


def _by_tool(hint):
    return {o["tool"]: o for o in hint["options"]}


def test_ingest_hint_is_offer_only_and_never_asks():
    hint = workflow.next_after_kb_ingest(
        _INGEST_REPORT, allowed_tools=None, hints_enabled=True,
    )
    assert hint["state"] == "kb_ingested"
    assert hint["blocking"] is False
    assert hint["ask_user"] is None
    assert hint["call"] is None
    assert set(_by_tool(hint)) == {
        "kb_approve_points", "kb_ingest_resume", "kb_list_entities", "kb_list_points",
    }


def test_ingest_hint_leads_with_approval_carrying_the_new_point_ids():
    """Ingest writes DRAFTS. The next step is the approval gate, and its args
    have to be callable verbatim — the ids this very report returned."""
    hint = workflow.next_after_kb_ingest(
        _INGEST_REPORT, allowed_tools=None, hints_enabled=True,
    )
    assert hint["options"][0]["tool"] == "kb_approve_points"
    assert hint["options"][0]["args"] == {"point_ids": _INGEST_POINT_IDS}
    # Composition is NOT offered here: nothing is approved yet.
    assert "create_base_resume_from_kb" not in _by_tool(hint)
    assert "approve" in hint["offer"]


def test_ingest_hint_omits_approval_when_no_points_landed():
    rerun = {**_INGEST_REPORT, "points": [], "points_created": 0,
             "entities_created": 0, "entities_matched": 2}
    hint = workflow.next_after_kb_ingest(rerun, allowed_tools=None, hints_enabled=True)
    assert "kb_approve_points" not in _by_tool(hint)
    assert "kb_ingest_resume" in _by_tool(hint)
    # The prose must not advertise the step that was just suppressed.
    assert "approve" not in hint["offer"]


def test_ingest_hint_prose_drops_tools_the_profile_filtered_out():
    hint = workflow.next_after_kb_ingest(
        _INGEST_REPORT,
        allowed_tools=frozenset({"kb_ingest_resume"}),
        hints_enabled=True,
    )
    assert set(_by_tool(hint)) == {"kb_ingest_resume"}
    assert "kb_approve_points" not in hint["offer"]
    assert "kb_ingest_resume" in hint["offer"]


def test_ingest_hint_says_nothing_when_every_option_is_filtered_out():
    hint = workflow.next_after_kb_ingest(
        _INGEST_REPORT, allowed_tools=frozenset({"score_ats"}), hints_enabled=True,
    )
    assert hint["options"] == []
    assert hint["offer"] is None


def test_ingest_hint_is_callable_under_the_career_profile():
    from mcp_server.profiles import CAREER_TOOLS

    hint = workflow.next_after_kb_ingest(
        _INGEST_REPORT, allowed_tools=CAREER_TOOLS, hints_enabled=True,
    )
    assert set(_by_tool(hint)) <= CAREER_TOOLS
    assert "kb_approve_points" in _by_tool(hint)


def test_bulk_state_hint_offers_create_after_approvals():
    hint = workflow.next_after_bulk_state(
        [{"id": "p1", "ok": True, "state": "approved", "detail": None}],
        requested_state="approved", allowed_tools=None, hints_enabled=True,
    )
    assert hint["state"] == "kb_points_updated"
    assert hint["blocking"] is False
    assert hint["ask_user"] is None
    assert hint["call"] is None
    option = _by_tool(hint)["create_base_resume_from_kb"]
    # entity_ids=[] is a documented 422; a composer that cannot know the ids
    # must emit no args at all rather than an illegal one.
    assert "args" not in option
    assert "entity_ids" in option["detail"]
    assert "1 point(s) approved" in hint["offer"]


def test_bulk_state_hint_drops_create_when_the_profile_lacks_it():
    hint = workflow.next_after_bulk_state(
        [{"id": "p1", "ok": True, "state": "approved", "detail": None}],
        requested_state="approved",
        allowed_tools=frozenset({"kb_list_points"}),
        hints_enabled=True,
    )
    assert hint["options"] == []
    assert "create_base_resume_from_kb" not in hint["offer"]


def test_bulk_state_hint_is_neutral_after_retires():
    hint = workflow.next_after_bulk_state(
        [{"id": "p1", "ok": True, "state": "retired", "detail": None}],
        requested_state="retired", allowed_tools=None, hints_enabled=True,
    )
    assert hint["ask_user"] is None
    assert hint["options"] == []
    assert "retired" in hint["offer"]


def test_bulk_state_hint_is_honest_when_every_id_failed():
    """The old composer read intent out of the RESULTS, so an approval where
    every id was unknown reported 'Points retired. Nothing else required.'"""
    hint = workflow.next_after_bulk_state(
        [
            {"id": "p1", "ok": False, "state": None, "detail": "not found"},
            {"id": "p2", "ok": False, "state": None, "detail": "not found"},
        ],
        requested_state="approved", allowed_tools=None, hints_enabled=True,
    )
    assert hint["options"] == []
    assert "2 of 2" in hint["offer"]
    assert "not found" in hint["offer"]
    assert "retired" not in hint["offer"]
    assert "Nothing else required" not in hint["offer"]


def test_bulk_state_hint_reports_partial_failures():
    hint = workflow.next_after_bulk_state(
        [
            {"id": "p1", "ok": True, "state": "approved", "detail": None},
            {"id": "p2", "ok": False, "state": None, "detail": "not found"},
        ],
        requested_state="approved", allowed_tools=None, hints_enabled=True,
    )
    assert "1 point(s) approved" in hint["offer"]
    assert "1 id(s) failed" in hint["offer"]


def test_bulk_state_hint_on_an_empty_result_list_does_not_claim_success():
    hint = workflow.next_after_bulk_state(
        [], requested_state="approved", allowed_tools=None, hints_enabled=True,
    )
    assert hint["options"] == []
    assert "No point changed state" in hint["offer"]


def test_base_from_kb_hint_offers_render_only():
    hint = workflow.next_after_base_from_kb(
        {"slug": "data_scientist"}, allowed_tools=None, hints_enabled=True,
    )
    assert hint["state"] == "base_from_kb"
    assert hint["blocking"] is False
    assert hint["ask_user"] is None
    assert hint["call"] is None
    # score_ats needs a job_id this composer cannot know — prose, not an option.
    assert set(_by_tool(hint)) == {"render_pdf"}
    assert _by_tool(hint)["render_pdf"]["args"] == {
        "target_type": "base_resume", "target_id": "data_scientist"
    }
    assert "score_ats" in hint["offer"]


def test_base_from_kb_hint_names_a_failed_pdf_instead_of_calling_the_base_ready():
    """A base created with a render_error is not "ready": the hint names the first
    line of the error and offers no render that would fail the same way."""
    hint = workflow.next_after_base_from_kb(
        {"slug": "data_scientist", "render_error": "pdflatex failed\n! LaTeX Error: Something's wrong"},
        allowed_tools=None, hints_enabled=True,
    )
    assert hint["state"] == "base_render_failed"
    assert "is ready" not in hint["offer"]
    assert "pdflatex failed" in hint["offer"]
    assert "LaTeX Error" not in hint["offer"]
    assert "render_pdf" not in _by_tool(hint)
    assert "edit_base_resume" in hint["offer"]


def test_base_from_kb_hint_keeps_render_under_the_career_profile():
    from mcp_server.profiles import CAREER_TOOLS

    hint = workflow.next_after_base_from_kb(
        {"slug": "data_scientist"}, allowed_tools=CAREER_TOOLS, hints_enabled=True,
    )
    assert set(_by_tool(hint)) == {"render_pdf"}


def test_base_from_kb_hint_drops_render_when_the_profile_lacks_it():
    hint = workflow.next_after_base_from_kb(
        {"slug": "data_scientist"},
        allowed_tools=frozenset({"kb_list_points"}),
        hints_enabled=True,
    )
    assert hint["options"] == []
    assert "no render tool; the profile set has one" in hint["offer"]
    assert "apply" not in hint["offer"]


def test_base_from_kb_hint_names_the_form_answers_while_setup_reads_them_open():
    hint = workflow.next_after_base_from_kb(
        {"slug": "ds"}, allowed_tools=None, hints_enabled=True,
        setup_status=_autofill_setup_status(ready=False),
    )
    assert "set_autofill_profile" in hint["offer"]
    # Prose only: an option's args are callable verbatim, and the answers are the user's to give.
    assert set(_by_tool(hint)) == {"render_pdf"}


@pytest.mark.parametrize("status", [None, {}, {"autofill": None}, "ready"])
def test_base_from_kb_hint_leaves_out_the_form_answers_unless_setup_reads_them_open(status):
    status = _autofill_setup_status(ready=True) if status == "ready" else status
    hint = workflow.next_after_base_from_kb(
        {"slug": "ds"}, allowed_tools=None, hints_enabled=True, setup_status=status,
    )
    assert "set_autofill_profile" not in hint["offer"]


def test_base_from_kb_hint_leaves_out_the_form_answers_where_the_write_is_unregistered():
    hint = workflow.next_after_base_from_kb(
        {"slug": "ds"}, allowed_tools=frozenset({"render_pdf"}), hints_enabled=True,
        setup_status=_autofill_setup_status(ready=False),
    )
    assert "set_autofill_profile" not in hint["offer"]


def test_base_from_kb_hint_says_nothing_without_a_slug():
    # The server degrades a non-dict body to {}; target_id: "" is a footgun.
    assert workflow.next_after_base_from_kb(
        {}, allowed_tools=None, hints_enabled=True,
    ) is None


def test_onboarding_hints_suppress_when_the_switch_is_off():
    assert workflow.next_after_kb_ingest(
        _INGEST_REPORT, allowed_tools=None, hints_enabled=False) is None
    assert workflow.next_after_bulk_state(
        [], requested_state="approved", allowed_tools=None, hints_enabled=False) is None
    assert workflow.next_after_base_from_kb(
        {"slug": "x"}, allowed_tools=None, hints_enabled=False) is None


# ---- hint prose: profile invariant and neutral wording ----------------------
#
# SYSTEM.md §7: "A hint never names a tool the active profile did not register."
# The options were always filtered; the PROSE (offer / ask_user / label /
# detail) was not, so render hints under templates/career advertised the apply
# handoff tools and the career base-from-KB hint advertised score_ats.

_ALL_TOOL_NAMES = frozenset().union(
    *(a for a in profiles.PROFILE_ALLOWLISTS.values() if a is not None)
)

_PROFILES = sorted(profiles.PROFILE_ALLOWLISTS)  # every set, so a new one is covered by default


def _every_hint(allow):
    """Every composer, every branch that changes which tools get named."""
    kw = {"allowed_tools": allow, "hints_enabled": True}
    ok = {"id": "p1", "ok": True, "state": "approved", "detail": None}
    bad = {"id": "p2", "ok": False, "state": None, "detail": "not found"}
    no_points = {**_INGEST_REPORT, "points": []}
    hints = {
        "scores": workflow.next_after_scores(
            _ranking(), job_id="j1", quick_profile={"mirror_wording": True}, **kw),
        "session_pending": workflow.next_after_session(
            _session(gap_ids=["g1", "g2"], resolved_ids=["g1"]), **kw),
        "session_resolved": workflow.next_after_session(
            _session(gap_ids=["g1"], resolved_ids=["g1"]), **kw),
        "session_pending_maestro": workflow.next_after_session(
            _session(gap_ids=["g1", "g2"], resolved_ids=["g1"]), writer="maestro", **kw),
        "session_resolved_maestro": workflow.next_after_session(
            _session(gap_ids=["g1"], resolved_ids=["g1"]), writer="maestro", **kw),
        "tailor": workflow.next_after_tailor(application_id="a1", **kw),
        "tailor_left": workflow.next_after_tailor(
            application_id="a1", keywords_added=["Snowflake"], no_new_text=True,
            answers_left_to_ops=[{"gap_id": "g1", "action": "user_input", "skill": "x"}], **kw),
        "tailor_ops_left": workflow.next_after_tailor(
            application_id="a1", keywords_added=["Snowflake"],
            answers_left_to_ops=[{"gap_id": "g1", "action": "user_input", "skill": "x"}], **kw),
        "tailor_pdf_made": workflow.next_after_tailor(
            application_id="a1", pdf_ready=True,
            setup_status=_autofill_setup_status(ready=False), **kw),
        "tailor_pdf_made_left": workflow.next_after_tailor(
            application_id="a1", pdf_ready=True, setup_status=_autofill_setup_status(ready=True),
            no_new_text=True,
            answers_left_to_ops=[{"gap_id": "g1", "action": "add_keyword", "skill": "x"}], **kw),
        "tailor_pdf_made_ops_left": workflow.next_after_tailor(
            application_id="a1", pdf_ready=True, setup_status=_autofill_setup_status(ready=True),
            answers_left_to_ops=[{"gap_id": "g1", "action": "attach_project", "skill": "x"}], **kw),
        "render_ready": workflow.next_after_render(
            setup_status=_autofill_setup_status(ready=True), **kw),
        "render_blocked": workflow.next_after_render(
            setup_status=_autofill_setup_status(ready=False), **kw),
        "ingest": workflow.next_after_kb_ingest(_INGEST_REPORT, **kw),
        "ingest_no_points": workflow.next_after_kb_ingest(no_points, **kw),
        "bulk_approved": workflow.next_after_bulk_state(
            [ok], requested_state="approved", **kw),
        "bulk_retired": workflow.next_after_bulk_state(
            [{**ok, "state": "retired"}], requested_state="retired", **kw),
        "bulk_failed": workflow.next_after_bulk_state(
            [bad], requested_state="approved", **kw),
        "bulk_partial": workflow.next_after_bulk_state(
            [ok, bad], requested_state="approved", **kw),
        "base_from_kb": workflow.next_after_base_from_kb({"slug": "ds"}, **kw),
        "base_render_failed": workflow.next_after_base_from_kb(
            {"slug": "ds", "render_error": "pdflatex failed"}, **kw),
        "base_from_kb_answers_open": workflow.next_after_base_from_kb(
            {"slug": "ds"}, setup_status=_autofill_setup_status(ready=False), **kw),
    }
    return {name: h for name, h in hints.items() if h is not None}


def _strings(node):
    """Every string VALUE in a hint (offer, ask_user, labels, details, notes)."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _strings(v)


def _named_tools(hint):
    text = json.dumps(hint)
    return {n for n in _ALL_TOOL_NAMES if re.search(rf"\b{re.escape(n)}\b", text)}


@pytest.mark.parametrize("profile", _PROFILES)
def test_no_hint_names_a_removed_tool(profile):
    for name, hint in _every_hint(profiles.allowed_tools(profile)).items():
        text = json.dumps(hint)
        for removed in ("quick_tailor", "tailor_application"):
            assert not re.search(rf"\b{removed}\b", text), (profile, name, removed)


@pytest.mark.parametrize("profile", _PROFILES)
def test_no_hint_prose_or_option_names_a_tool_outside_the_profile(profile):
    allow = profiles.allowed_tools(profile)
    permitted = _ALL_TOOL_NAMES if allow is None else allow
    for name, hint in _every_hint(allow).items():
        outside = _named_tools(hint) - permitted
        assert not outside, f"{profile}/{name} names unregistered {sorted(outside)}: {hint}"


def test_render_hint_names_the_apply_handoff_only_where_it_is_registered():
    for profile in ("templates", "career"):
        hint = workflow.next_after_render(
            setup_status=_autofill_setup_status(ready=True),
            allowed_tools=profiles.allowed_tools(profile), hints_enabled=True,
        )
        assert hint["offer"] is None
        assert hint["readiness"]["autofill_ready"] is True  # facts still ride along
    apply_hint = workflow.next_after_render(
        setup_status=_autofill_setup_status(ready=True),
        allowed_tools=profiles.allowed_tools("apply"), hints_enabled=True,
    )
    assert _named_tools(apply_hint) == {
        "prepare_application_pdf_upload", "record_consent", "mark_submitted",
    }


def test_career_base_from_kb_hint_does_not_mention_scoring():
    hint = workflow.next_after_base_from_kb(
        {"slug": "ds"}, allowed_tools=profiles.allowed_tools("career"),
        hints_enabled=True,
    )
    assert "score_ats" not in hint["offer"]
    assert "render_pdf" in hint["offer"]


def test_scoring_hint_prose_follows_the_visible_options():
    no_tailoring = workflow.next_after_scores(
        _ranking(), job_id="j1", quick_profile={},
        allowed_tools=frozenset({"score_ats"}), hints_enabled=True,
    )
    assert no_tailoring["options"] == []
    assert no_tailoring["offer"] is None


# Phrases that address the calling model or issue it a command. Hints describe
# state and the next steps that exist; the server does not instruct the model.
# `ask_user` KEYS are fine (the question is data the client may show the user);
# this scans string VALUES only.
_STEERING = re.compile(
    r"tell the user|report (them|it) to the user|show the user|"
    r"with the user\b|safe to ignore|ignore (it|this)|"
    r"check before|rather than|\bnever\b|\bmust\b|only if|"
    r"\bsupply\b|\bpass\b|nothing else required|nothing here requires|"
    r"\bswitch to\b|\bauthor\b.*\bthen call\b|\bread resolutions_json\b|"
    r"\bmake sure\b|\bdo not\b|\bdon't\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("profile", _PROFILES)
def test_hint_prose_describes_state_and_never_instructs_the_model(profile):
    allow = profiles.allowed_tools(profile)
    for name, hint in _every_hint(allow).items():
        for text in _strings(hint):
            match = _STEERING.search(text)
            assert not match, f"{profile}/{name}: {match.group(0)!r} in {text!r}"


def test_consent_tools_are_described_as_recording_the_users_decisions():
    hint = workflow.next_after_render(
        setup_status={}, allowed_tools=profiles.allowed_tools("apply"),
        hints_enabled=True,
    )
    assert "user's" in hint["offer"]
    approve = workflow.next_after_kb_ingest(
        _INGEST_REPORT, allowed_tools=None, hints_enabled=True,
    )
    assert "user" in approve["offer"]


def test_pending_gaps_question_states_the_decision_without_naming_tools():
    hint = workflow.next_after_session(
        _session(gap_ids=["g1", "g2"], resolved_ids=["g1"]),
        allowed_tools=None, hints_enabled=True,
    )
    assert hint["ask_user"].startswith("1 gap(s)")
    assert hint["ask_user"].endswith("?")
    assert _named_tools({"q": hint["ask_user"]}) == set()


# --- setup_next_step: the first setup step an agent can do --------------------

def _setup(**done):
    """A setup-status body; each step done only when named True."""
    status = {
        "model_key": {"done": done.get("model_key", False), "detail": {}},
        "import_resumes": {"done": done.get("import_resumes", False),
                           "detail": {"kb_entities": 0, "base_resumes": done.get("bases", 0)}},
        "autofill": {"done": done.get("autofill", False), "readiness": 0.0, "groups": {},
                     "blocking": []},
        "job_preferences": {"done": done.get("job_preferences", False), "detail": {}},
        "persona": {"done": done.get("persona", False), "detail": {}},
        "template": {"done": False, "detail": {}},
        "demo_bases": done.get("demo_bases", []),
    }
    return status


def test_setup_next_step_starts_with_career_history():
    step = workflow.setup_next_step(_setup())
    assert (step["step"], step["tool_set"]) == ("career_history", "profile")


def test_setup_next_step_asks_for_a_base_before_form_answers_and_ignores_the_demo():
    step = workflow.setup_next_step(_setup(import_resumes=True, bases=1, demo_bases=["example"]))
    assert step["step"] == "base_resume"
    # Setup counts career history done once it has an item, but an import's bullets are drafts and a
    # base resume takes approved ones only, so this step names the approval.
    assert "start as drafts" in step["says"]
    step = workflow.setup_next_step(_setup(import_resumes=True, bases=2, demo_bases=["example"]))
    assert step["step"] == "form_answers"


def test_setup_next_step_walks_preferences_then_persona_then_nothing():
    base = {"import_resumes": True, "bases": 1, "autofill": True}
    assert workflow.setup_next_step(_setup(**base))["step"] == "job_preferences"
    assert workflow.setup_next_step(_setup(**base, job_preferences=True))["step"] == "persona"
    assert workflow.setup_next_step(_setup(**base, job_preferences=True, persona=True)) is None


def test_setup_next_step_leaves_the_diversity_answers_to_the_user():
    """set_autofill_profile refuses `eeo`: only the user gives those, in the app. Once every other
    form answer is saved, an agent's next step moves on instead of waiting on what it cannot save."""
    status = _setup(import_resumes=True, bases=1)
    status["autofill"]["groups"] = {
        "personal": {"answered": 12, "answerable": 12}, "work_auth": {"answered": 4, "answerable": 4},
        "preferences": {"answered": 5, "answerable": 5}, "eeo": {"answered": 0, "answerable": 4}}
    assert workflow.setup_next_step(status)["step"] == "job_preferences"
    status["autofill"]["groups"]["personal"]["answered"] = 7
    step = workflow.setup_next_step(status)
    assert step["step"] == "form_answers"
    assert "diversity answers are the user's" in step["says"]


def test_setup_next_step_never_asks_an_agent_for_the_key_or_the_template():
    """Both are the user's, in the app: reported by get_setup_status, never a next step."""
    seen = set()
    for flags in ({}, {"import_resumes": True, "bases": 1}, {"import_resumes": True, "bases": 1,
                  "autofill": True, "job_preferences": True, "persona": True}):
        step = workflow.setup_next_step(_setup(**flags))
        seen.add(step and step["step"])
    assert not seen & {"model_key", "template"}


def test_setup_next_step_names_no_tool():
    """It is read from every set, so it describes the step and names only the set."""
    import re

    from mcp_server.server import list_registered_tool_names

    tools = set(list_registered_tool_names("full"))
    for flags in ({}, {"import_resumes": True}, {"import_resumes": True, "bases": 1},
                  {"import_resumes": True, "bases": 1, "autofill": True},
                  {"import_resumes": True, "bases": 1, "autofill": True, "job_preferences": True}):
        says = workflow.setup_next_step(_setup(**flags))["says"]
        assert not set(re.findall(r"[a-z_]+", says)) & tools, says
