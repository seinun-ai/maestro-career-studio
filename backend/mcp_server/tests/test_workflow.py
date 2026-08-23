import pytest

from mcp_server import workflow


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
        _score("a", 40.0, coverage="I could not read this posting"),
        _score("b", 38.0, coverage="I could not read this posting"),
    ])
    assert out["coverage_warning"] == "I could not read this posting"


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
        _score("b", 50.0, coverage="I could not read this posting"),
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
            "personal": {"answered": 12, "answerable": 12},
            "work_auth": {"answered": 4, "answerable": 4},
            "preferences": {"answered": 5, "answerable": 5},
        }
        return {"autofill": {"done": True, "readiness": 1.0, "groups": groups, "blocking": []}}
    groups = {
        "personal": {"answered": 12, "answerable": 12},
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
    quick = [o for o in hint["options"] if o["tool"] == "quick_tailor"][0]
    assert quick["detail"]["mirror_wording"] is True
    assert quick["detail"]["keywords_into_skills"] is False


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
    assert "headless" in offer.lower()
    assert "stealth" in offer.lower()
    assert "captcha" in offer.lower()


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
    assert "ingest another resume" in hint["offer"]


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
    assert "switch to apply or full" in hint["offer"]


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
