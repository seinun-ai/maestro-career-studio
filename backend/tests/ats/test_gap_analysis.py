from datetime import date

from app.services.ats import score_resume
from app.services.ats.engine import AtsResult
from app.services.gap_analysis import build_gaps
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _result(
    *,
    title_tier: str = "direct",
    skill_table: list | None = None,
    gate_warnings: list | None = None,
    format_flags: list | None = None,
    requirement_coverage: list | None = None,
) -> AtsResult:
    """A minimal AtsResult with fully-controlled title/gate/format inputs, so a
    test can assert build_gaps behaviour in isolation from the scoring engine."""
    return AtsResult(
        composite=90.0,
        subscores={"keyword": 1.0, "placement_recency": 1.0, "semantic_fit": 1.0,
                   "title": 1.0, "format": 1.0},
        title_tier=title_tier,
        gate_warnings=gate_warnings or [],
        format_flags=format_flags or [],
        skill_table=skill_table or [],
        requirement_coverage=requirement_coverage or [],
        engine_version="test",
        config_version="test",
    )


def test_build_gaps_categorizes_and_orders():
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=date(2026, 7, 6))
    gaps = build_gaps(result)
    keys = [c["key"] for c in gaps["categories"]]
    # only categories with content appear, in fixed priority order
    assert keys == [k for k in (
        "missing_skills", "mirror_wording", "dual_place",
        "resurface_recent", "adjacent", "weak_coverage", "title_structure",
    ) if k in keys]
    missing = next(c for c in gaps["categories"] if c["key"] == "missing_skills")
    assert missing["gaps"][0]["jd_skill"] == "Salesforce"          # required before preferred
    assert missing["gaps"][0]["gap_id"] == "skill:salesforce"
    assert set(missing["gaps"][0]["actions"]) == {
        "add_keyword", "user_input", "attach_project", "skip",
        "enable_entry", "port_kb_point", "cannot_confirm",
    }

    wording = next(c for c in gaps["categories"] if c["key"] == "mirror_wording")
    assert wording["gaps"][0]["jd_skill"] == "AWS"
    assert "add_keyword" in wording["gaps"][0]["actions"]


def test_missing_skills_offers_add_keyword_for_unverified_add():
    # missing skills may now be added straight to the skills list (unverified).
    from app.services.gap_analysis import _ACTIONS
    assert "add_keyword" in _ACTIONS["missing_skills"]
    # the honest alternatives remain
    assert {"user_input", "attach_project", "skip"} <= set(_ACTIONS["missing_skills"])


def test_missing_skills_gaps_allow_library_actions():
    result = _result(
        skill_table=[
            _skill_row(
                jd_skill="Kafka",
                contribution=0.0,
                fix_hint="absent",
                placement=None,
                match_credit=0.0,
            )
        ]
    )

    gaps = build_gaps(result)

    missing = next(c for c in gaps["categories"] if c["key"] == "missing_skills")
    assert set(missing["gaps"][0]["actions"]) == {
        "add_keyword",
        "user_input",
        "attach_project",
        "skip",
        "enable_entry",
        "port_kb_point",
        "cannot_confirm",
    }


def test_gap_ids_unique_and_stable():
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=date(2026, 7, 6))
    a = [g["gap_id"] for c in build_gaps(result)["categories"] for g in c["gaps"]]
    b = [g["gap_id"] for c in build_gaps(result)["categories"] for g in c["gaps"]]
    assert a == b and len(a) == len(set(a))


def test_title_and_format_gaps_included():
    import copy
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["summary"] = None  # trigger a format flag
    result = score_resume(resume, SAMPLE_JD, as_of=date(2026, 7, 6))
    gaps = build_gaps(result)
    ts = next((c for c in gaps["categories"] if c["key"] == "title_structure"), None)
    assert ts is not None and any(g["kind"] == "format" for g in ts["gaps"])


def test_summary_gap_always_present_for_direct_title():
    # A perfectly-matched resume (direct title, no skill/gate/format gaps) still
    # gets exactly one gap: the always-present summary value-prop refresh.
    gaps = build_gaps(_result(title_tier="direct"))
    assert [c["key"] for c in gaps["categories"]] == ["title_structure"]
    ts_gaps = gaps["categories"][0]["gaps"]
    assert len(ts_gaps) == 1
    summary = ts_gaps[0]
    assert summary["gap_id"] == "summary:value_prop"
    assert summary["kind"] == "summary"
    assert summary["actions"] == ["user_input", "skip"]
    assert summary["detail"] == "Refresh the summary as a JD-aligned value proposition"
    assert summary["diagnostic"] == {}
    assert summary["enrichment"] is None


def test_weak_coverage_gap_emitted_below_threshold_only():
    # A requirement line whose best cosine is below the coverage threshold becomes
    # a weak_coverage/requirement gap; a well-covered line (0.9) yields nothing.
    from app.services.gap_analysis import _COVERAGE_THRESHOLD

    assert _COVERAGE_THRESHOLD == 0.55
    result = _result(requirement_coverage=[
        {"line": "Own the data platform roadmap", "score": 0.2},
        {"line": "Mentor junior engineers", "score": 0.9},
    ])
    gaps = build_gaps(result)
    wc = next((c for c in gaps["categories"] if c["key"] == "weak_coverage"), None)
    assert wc is not None
    assert wc["title"] == "Uncovered responsibilities"
    assert len(wc["gaps"]) == 1
    assert wc["gaps"][0] == {
        "gap_id": "coverage:0",
        "kind": "requirement",
        "jd_skill": "Own the data platform roadmap",
        "requirement_level": "preferred",
        "detail": "Resume prose does not clearly cover this responsibility",
        "diagnostic": {"coverage_score": 0.2},
        "actions": ["user_input", "skip", "cannot_confirm"],
        "enrichment": None,
    }


def test_weak_coverage_gap_id_uses_enumerate_index_over_coverage():
    # gap_id index is the enumerate index over requirement_coverage, not the
    # position among below-threshold lines: a skipped covered line at index 0
    # still leaves the uncovered line at index 1 as coverage:1.
    result = _result(requirement_coverage=[
        {"line": "covered line", "score": 0.9},
        {"line": "uncovered line", "score": 0.2},
    ])
    wc = next(c for c in build_gaps(result)["categories"] if c["key"] == "weak_coverage")
    assert [g["gap_id"] for g in wc["gaps"]] == ["coverage:1"]


def test_weak_coverage_category_placed_after_adjacent_before_title():
    # Category ordering: weak_coverage sits between adjacent and title_structure.
    from app.services.gap_analysis import _CATEGORIES

    keys = [k for k, _, _ in _CATEGORIES]
    assert keys.index("adjacent") < keys.index("weak_coverage") < keys.index("title_structure")


def test_no_weak_coverage_category_when_all_lines_covered():
    result = _result(requirement_coverage=[{"line": "well covered", "score": 0.8}])
    keys = [c["key"] for c in build_gaps(result)["categories"]]
    assert "weak_coverage" not in keys


def test_summary_gap_follows_title_gap_when_title_not_direct():
    # When the title doesn't directly match, the title gap AND the summary gap
    # are both present, with the summary gap after the title gap.
    ts_gaps = build_gaps(_result(title_tier="adjacent"))["categories"][0]["gaps"]
    kinds = [g["kind"] for g in ts_gaps]
    assert kinds == ["title", "summary"]
    assert [g["gap_id"] for g in ts_gaps] == ["title:alignment", "summary:value_prop"]


# --- potential_points (finding U4) -----------------------------------------
#
# A skill row feeds the placement_recency subscore through
#   contribution = requirement_weight * match_credit * placement_multiplier * recency
# (app/services/ats/layers.py resolve_evidence). potential_points estimates the
# 0-100 composite headroom recovering that row to its dual-placement ceiling
# would yield; it is a monotonic ordering signal, not an exact predictor.

def _skill_row(
    *,
    jd_skill: str = "Kafka",
    requirement_level: str = "required",
    placement: str = "skills_list_only",
    match_credit: float = 1.0,
    contribution: float,
    recency_weight: float | None = 1.0,
    fix_hint: str = "dual_place",
) -> dict:
    """A skill_table row (asdict(SkillEvidence) shape) with just enough fields for
    the gap builder + potential_points math."""
    return {
        "jd_skill": jd_skill,
        "canonical": jd_skill.lower(),
        "requirement_level": requirement_level,
        "matched": contribution > 0,
        "match_form": "exact",
        "match_credit": match_credit,
        "matched_term": jd_skill.lower(),
        "placement": placement,
        "last_used": "2025-01-01",
        "recency_weight": recency_weight,
        "contribution": contribution,
        "fix_hint": fix_hint,
        "evidence_entries": [],
    }


def test_skill_gap_has_nonnegative_potential_points():
    from app.services.gap_analysis import _skill_gap

    # required skills_list_only: contribution = 2.0*1.0*0.4*1.0 = 0.8
    gap = _skill_gap(_skill_row(contribution=0.8), "dual_place")
    assert isinstance(gap["potential_points"], float)
    assert gap["potential_points"] >= 0.0


def test_dual_place_headroom_beats_dual_ceiling():
    # A row with real placement headroom (skills_list_only) must score STRICTLY
    # higher than an otherwise-identical row already at the dual ceiling.
    from app.services.gap_analysis import _skill_gap

    headroom = _skill_gap(
        _skill_row(placement="skills_list_only", contribution=0.8), "dual_place"
    )
    # already dual: contribution = 2.0*1.0*1.5*1.0 = 3.0 -> zero headroom
    ceiling = _skill_gap(_skill_row(placement="dual", contribution=3.0), "dual_place")
    assert headroom["potential_points"] > ceiling["potential_points"]
    assert ceiling["potential_points"] == 0.0


def test_required_potential_at_least_preferred_all_else_equal():
    from app.services.gap_analysis import _skill_gap

    # required: contribution = 2.0*1.0*0.4*1.0 = 0.8
    req = _skill_gap(
        _skill_row(requirement_level="required", contribution=0.8), "dual_place"
    )
    # preferred, same credit/placement/recency: contribution = 1.0*1.0*0.4*1.0 = 0.4
    pref = _skill_gap(
        _skill_row(requirement_level="preferred", contribution=0.4), "dual_place"
    )
    assert req["potential_points"] >= pref["potential_points"]


def test_missing_required_skill_recovers_full_placement_weight():
    # An absent required skill (contribution 0) has the most headroom: recovering
    # it to the required dual ceiling is the whole placement_recency subscore.
    #   best_case = 2.0(required) * 1.5(dual) = 3.0
    #   headroom  = 3.0 - 0.0 = 3.0
    #   max_row   = 2.0 * 1.5 = 3.0
    #   points    = 3.0/3.0 * 0.20(composite placement_recency) * 100 = 20.0
    from app.services.gap_analysis import _skill_gap

    absent_req = _skill_gap(
        _skill_row(requirement_level="required", contribution=0.0, fix_hint="absent"),
        "missing_skills",
    )
    absent_pref = _skill_gap(
        _skill_row(requirement_level="preferred", contribution=0.0, fix_hint="absent"),
        "missing_skills",
    )
    assert absent_req["potential_points"] == 20.0
    assert absent_req["potential_points"] > absent_pref["potential_points"]


def test_potential_points_pinned_arithmetic():
    # required skills_list_only, full credit & recency:
    #   contribution = 2.0 * 1.0 * 0.4 * 1.0 = 0.8   (present placement)
    #   best_case    = 2.0 * 1.5             = 3.0   (dual ceiling for required)
    #   headroom     = 3.0 - 0.8             = 2.2
    #   max_row      = 2.0 * 1.5             = 3.0   (largest single-row contribution)
    #   points = 2.2/3.0 * 0.20 * 100 = 14.666... -> 14.7
    from app.services.gap_analysis import _skill_gap

    gap = _skill_gap(
        _skill_row(
            requirement_level="required", placement="skills_list_only", contribution=0.8
        ),
        "dual_place",
    )
    assert gap["potential_points"] == 14.7


def test_build_gaps_attaches_potential_points_to_skill_gaps_only():
    # Every skill gap carries a numeric potential_points; non-skill gaps
    # (title/summary/gate/format/requirement-coverage) never do.
    result = _result(
        skill_table=[
            _skill_row(jd_skill="Kafka", contribution=0.8, fix_hint="dual_place"),
            _skill_row(
                jd_skill="Airflow", contribution=0.0, fix_hint="absent",
                placement=None, match_credit=0.0,
            ),
        ],
        title_tier="adjacent",
        format_flags=["Contact block missing name, email, or phone"],
        requirement_coverage=[{"line": "Own the roadmap", "score": 0.1}],
    )
    gaps = build_gaps(result)
    for category in gaps["categories"]:
        for gap in category["gaps"]:
            if gap["kind"] == "skill":
                assert isinstance(gap["potential_points"], float)
                assert gap["potential_points"] >= 0.0
            else:
                assert "potential_points" not in gap


def test_format_flag_actionable_classification():
    """Pins each real l5_format flag string to its routing (guards the substring
    coupling to app/services/ats/layers.py)."""
    from app.services.gap_analysis import _format_flag_actionable

    # fix-at-source: no edit op can address these
    assert _format_flag_actionable(
        "Some experience dates failed to parse (use 'Jul 2022' format)"
    ) is False
    assert _format_flag_actionable("Contact block missing name, email, or phone") is False
    assert _format_flag_actionable("Section missing or empty: experience") is False
    assert _format_flag_actionable("Section missing or empty: education") is False
    # actionable: an op can add/prune
    assert _format_flag_actionable("Section missing or empty: summary") is True
    assert _format_flag_actionable("Section missing or empty: skills") is True
    assert _format_flag_actionable(
        "40% of skills-section items have no supporting evidence in any entry"
    ) is True


def test_fix_at_source_format_gap_is_skip_only_with_edit_hint():
    result = _result(format_flags=["Contact block missing name, email, or phone"])
    gaps = build_gaps(result)
    ts = next(c for c in gaps["categories"] if c["key"] == "title_structure")
    fmt = next(g for g in ts["gaps"] if g["kind"] == "format")
    assert fmt["actions"] == ["skip"]
    assert "base resume" in fmt["detail"]


def test_actionable_format_gap_keeps_user_input():
    result = _result(format_flags=["Section missing or empty: summary"])
    gaps = build_gaps(result)
    ts = next(c for c in gaps["categories"] if c["key"] == "title_structure")
    fmt = next(g for g in ts["gaps"] if g["kind"] == "format")
    assert fmt["actions"] == ["user_input", "skip"]
    assert "base resume" not in fmt["detail"]


def test_mirror_wording_score_effect_hygiene_vs_adds_credit():
    from app.services.gap_analysis import _skill_gap

    # lexical alias/fuzzy already at full keyword credit -> hygiene
    hygiene = _skill_gap(
        _skill_row(fix_hint="mirror_wording", match_credit=1.0, contribution=0.8),
        "mirror_wording",
    )
    assert hygiene["score_effect"] == "hygiene"
    # semantic match (credit < 1.0) -> literal token adds credit
    adds = _skill_gap(
        _skill_row(fix_hint="mirror_wording", match_credit=0.6, contribution=0.48),
        "mirror_wording",
    )
    assert adds["score_effect"] == "adds_credit"


def test_non_mirror_wording_gap_has_no_score_effect():
    from app.services.gap_analysis import _skill_gap

    gap = _skill_gap(_skill_row(fix_hint="dual_place", contribution=0.8), "dual_place")
    assert "score_effect" not in gap
