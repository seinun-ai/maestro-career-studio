from datetime import date

from app.services.ats import score_resume
from scripts.ats_calibration import diff_snapshots, pair_from_result, summarize
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _pair(composite: float, rows: dict | None = None) -> dict:
    return {"composite": composite, "subscores": {}, "rows": rows or {}}


def _row(matched: bool, contribution: float, fix_hint: str | None = None) -> dict:
    return {
        "matched": matched,
        "match_form": "exact" if matched else None,
        "placement": "experience_only" if matched else None,
        "fix_hint": fix_hint,
        "contribution": contribution,
    }


def test_diff_reports_composite_delta_per_pair():
    before = {"pairs": {"job1|base1": _pair(60.0)}}
    after = {"pairs": {"job1|base1": _pair(72.5)}}

    report = diff_snapshots(before, after)

    assert report.pairs_compared == 1
    assert report.composite_deltas == [("job1|base1", 12.5)]


def test_diff_reports_only_pairs_present_on_both_sides():
    before = {"pairs": {"shared": _pair(50.0), "gone": _pair(10.0)}}
    after = {"pairs": {"shared": _pair(50.0), "new": _pair(90.0)}}

    report = diff_snapshots(before, after)

    assert report.pairs_compared == 1
    assert report.composite_deltas == []


def test_diff_flags_a_skill_that_became_matched():
    before = {"pairs": {"p": _pair(50.0, {"AWS Cert": _row(False, 0.0, "absent")})}}
    after = {"pairs": {"p": _pair(60.0, {"AWS Cert": _row(True, 1.0)})}}

    report = diff_snapshots(before, after)

    assert report.newly_matched == [("p", "AWS Cert")]
    assert report.newly_absent == []


def test_diff_flags_a_skill_that_stopped_matching():
    before = {"pairs": {"p": _pair(60.0, {"Spark": _row(True, 1.0)})}}
    after = {"pairs": {"p": _pair(50.0, {"Spark": _row(False, 0.0, "absent")})}}

    report = diff_snapshots(before, after)

    assert report.newly_absent == [("p", "Spark")]
    assert report.newly_matched == []


def test_diff_flags_a_row_whose_contribution_dropped():
    """The non-regression gate: turning a new evidence channel ON must never
    LOWER an existing row's contribution (e.g. semantic-stage argmax theft)."""
    before = {"pairs": {"p": _pair(60.0, {"Python": _row(True, 2.0)})}}
    after = {"pairs": {"p": _pair(60.0, {"Python": _row(True, 1.0)})}}

    report = diff_snapshots(before, after)

    assert report.contribution_regressions == [("p", "Python", 2.0, 1.0)]


def test_diff_does_not_flag_a_row_whose_contribution_rose():
    before = {"pairs": {"p": _pair(60.0, {"Python": _row(True, 1.0)})}}
    after = {"pairs": {"p": _pair(60.0, {"Python": _row(True, 2.0)})}}

    report = diff_snapshots(before, after)

    assert report.contribution_regressions == []


def test_pair_from_result_captures_composite_and_behavioral_row_fields():
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=date(2026, 7, 6))

    pair = pair_from_result(result)

    assert pair["composite"] == result.composite
    assert pair["subscores"] == result.subscores
    # keyed by jd_skill so a reordered skill_table is not a spurious diff
    first = result.skill_table[0]
    row = pair["rows"][first["jd_skill"]]
    assert set(row) == {"matched", "match_form", "placement", "fix_hint", "contribution"}
    assert row["matched"] == first["matched"]
    assert row["contribution"] == first["contribution"]


def test_summarize_counts_movement_and_flags_regressions():
    report = diff_snapshots(
        {"pairs": {"a": _pair(50.0, {"X": _row(True, 2.0)}), "b": _pair(50.0)}},
        {"pairs": {"a": _pair(55.0, {"X": _row(True, 1.0)}), "b": _pair(50.0)}},
    )

    text = summarize(report)

    assert "2 pairs compared" in text
    assert "1 moved" in text
    assert "REGRESSION" in text


def test_summarize_reports_a_clean_run_without_regression_wording():
    report = diff_snapshots(
        {"pairs": {"a": _pair(50.0, {"X": _row(False, 0.0, "absent")})}},
        {"pairs": {"a": _pair(60.0, {"X": _row(True, 1.0)})}},
    )

    text = summarize(report)

    assert "REGRESSION" not in text
    assert "newly matched" in text


def test_diff_groups_drops_by_match_form_transition():
    """A deliberate reclassification (fuzzy -> broader) and a same-form loss are
    both contribution drops, but only the second is a suspected regression. The
    summary must separate them, or an intended downgrade buries a real bug."""
    before = {"pairs": {"p": _pair(60.0, {
        "Oracle SQL": {**_row(True, 0.8), "match_form": "fuzzy"},
        "Python": {**_row(True, 2.0), "match_form": "semantic"},
    })}}
    after = {"pairs": {"p": _pair(58.0, {
        "Oracle SQL": {**_row(True, 0.4), "match_form": "broader"},
        "Python": {**_row(True, 1.0), "match_form": "semantic"},
    })}}

    report = diff_snapshots(before, after)

    assert report.drops_by_transition == {"fuzzy->broader": 1, "semantic->semantic": 1}
    text = summarize(report)
    assert "fuzzy->broader" in text
