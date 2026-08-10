from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.autofill_field_observation import AutofillFieldObservation
from app.schemas.autofill_telemetry import ObservationKind, ObservationOutcome
from app.services.autofill_telemetry import (
    FAILURE_OUTCOMES,
    NEUTRAL_OUTCOMES,
    NON_FORM_KINDS,
    RECOMMEND_KEEP,
    RECOMMEND_STOP,
    SUCCESS_OUTCOMES,
    summarize_rows,
)


def test_every_declared_outcome_lands_in_exactly_one_bucket():
    """The rate is only meaningful if the partition is total and disjoint.

    An outcome in neither set is invisible to every figure the Analytics card
    shows, and one in both would be counted twice. Deriving NEUTRAL_OUTCOMES
    makes totality automatic; this pins disjointness and guards the derivation
    itself. It would also have caught `eeo_disabled`, which the extension
    emitted for a whole round without the contract ever declaring it.
    """
    declared = set(get_args(ObservationOutcome))
    assert SUCCESS_OUTCOMES | FAILURE_OUTCOMES | NEUTRAL_OUTCOMES == declared
    assert not (SUCCESS_OUTCOMES & FAILURE_OUTCOMES)


def test_every_excluded_kind_is_a_declared_kind():
    """A typo in NON_FORM_KINDS excludes nothing and fails silently.

    `"signals"` for `"signal"` would leave every detection row in the summary
    while the module's docstring, this test's neighbours and the schema comment
    all said otherwise — the exact shape of bug the derived NEUTRAL_OUTCOMES
    partition exists to prevent on the outcome axis.
    """
    assert NON_FORM_KINDS <= set(get_args(ObservationKind))


def _row(
    label="Field",
    kind="text",
    host="h.io",
    outcomes=None,
    seen_count=None,
    marks=None,
    rule_id=None,
    options=None,
    sig=None,
):
    outcomes = outcomes or {"filled": 1}
    return AutofillFieldObservation(
        signature_hash=sig or f"sig-{label}-{kind}-{host}",
        host=host,
        label=label,
        kind=kind,
        options=options,
        rule_id=rule_id,
        outcomes=outcomes,
        seen_count=seen_count if seen_count is not None else sum(outcomes.values()),
        session_marks=marks or [],
    )


def _marks_for_batches(shares, row_index, rows_per_batch=10):
    """Build per-row marks so batch i has novelty share shares[i]:
    row_index < shares[i]*rows_per_batch → this row was new in that batch."""
    return [
        {
            "at": f"2026-07-{10 + i:02d}T00:00:00+00:00",
            "new": row_index < round(s * rows_per_batch),
        }
        for i, s in enumerate(shares)
    ]


def test_empty_summary():
    s = summarize_rows([])
    assert s["totals"] == {"signatures": 0, "observations": 0, "hosts": 0}
    assert s["by_kind"] == []
    assert s["top_failures"] == []
    assert s["novelty"] == []
    assert s["saturated"] is False
    assert s["recommendation"] == RECOMMEND_KEEP


def test_totals_and_per_kind_success_rates():
    rows = [
        _row(
            label="A",
            kind="text",
            host="a.io",
            outcomes={"filled": 3, "not_stuck": 1},
        ),
        _row(label="B", kind="text", host="b.io", outcomes={"corrected": 2}),
        # Neutral outcomes (skip_rule/skipped_checkbox/hidden/ai_answered) are
        # excluded from both sides of the rate per the frozen definition.
        _row(
            label="C",
            kind="checkbox",
            host="a.io",
            outcomes={"skipped_checkbox": 5},
        ),
        _row(label="D", kind="select", host="a.io", outcomes={"no_rule": 4}),
    ]
    s = summarize_rows(rows)
    assert s["totals"] == {"signatures": 4, "observations": 15, "hosts": 2}
    by_kind = {k["kind"]: k for k in s["by_kind"]}
    assert by_kind["text"]["success"] == 5
    assert by_kind["text"]["failure"] == 1
    assert by_kind["text"]["success_rate"] == pytest.approx(5 / 6)
    assert by_kind["checkbox"]["success_rate"] is None  # all-neutral → no denominator
    assert by_kind["select"]["success_rate"] == 0.0


def test_filled_normalized_counts_as_a_success():
    """The value landed; the site just reformatted it.

    A phone field that renders "5551234567" as "(555) 123-4567" is a fill that
    worked. It only stopped reading byte-equal when the readback started
    requiring the value to survive two animation frames, and counting that as a
    failure would make every well-behaved formatting site look broken.
    """
    s = summarize_rows(
        [
            _row(
                label="Phone",
                kind="text",
                outcomes={"filled_normalized": 3, "not_stuck": 1},
            )
        ]
    )
    by_kind = {k["kind"]: k for k in s["by_kind"]}
    assert by_kind["text"]["success"] == 3
    assert by_kind["text"]["failure"] == 1


def test_missing_source_and_policy_blocked_are_neutral():
    """Neither is a failure of the rules, so neither may move the rate.

    missing_source means the profile has no answer; policy_blocked means we
    recognised the field and correctly declined to write it. Scoring either as
    a failure would tell the user to go fix rules that are working.
    """
    s = summarize_rows(
        [
            _row(
                label="Desired salary",
                kind="text",
                outcomes={"missing_source": 4, "policy_blocked": 2},
            )
        ]
    )
    by_kind = {k["kind"]: k for k in s["by_kind"]}
    assert by_kind["text"]["success"] == 0
    assert by_kind["text"]["failure"] == 0
    assert by_kind["text"]["success_rate"] is None
    # And a signature made only of them must not be reported as a top failure.
    assert s["top_failures"] == []


def test_top_failures_ranked_by_seen_count_times_failure_share():
    rows = [
        # dominant outcome is a SUCCESS → excluded even though failures exist
        _row(label="Mostly fine", outcomes={"filled": 8, "no_rule": 2}),
        # score = 10 * 1.0 = 10
        _row(
            label="Big offender",
            kind="combobox",
            rule_id="school",
            options=["MIT", "Stanford"],
            outcomes={"combobox_snap_failed": 10},
        ),
        # score = 4 * 1.0 = 4
        _row(label="Small offender", outcomes={"not_stuck": 4}),
        # dominant=no_rule, share 3/4, seen 4 → score 3.0
        _row(label="Mixed", outcomes={"no_rule": 3, "filled": 1}),
    ]
    s = summarize_rows(rows)
    assert [f["label"] for f in s["top_failures"]] == [
        "Big offender",
        "Small offender",
        "Mixed",
    ]
    top = s["top_failures"][0]
    assert top["kind"] == "combobox"
    assert top["host"] == "h.io"
    # Stable per-signature identity so the web card can key rows uniquely even
    # when host+label+kind collide across signatures differing only by options.
    assert top["signature_hash"] == "sig-Big offender-combobox-h.io"
    assert top["rule_id"] == "school"
    assert top["options_sample"] == ["MIT", "Stanford"]
    assert top["seen_count"] == 10
    assert top["outcomes"] == {"combobox_snap_failed": 10}
    assert s["top_failures"][2]["failure_share"] == pytest.approx(0.75)


def test_top_failures_limited_to_ten():
    rows = [
        _row(label=f"F{i:02d}", sig=f"s{i}", outcomes={"no_rule": i + 1})
        for i in range(12)
    ]
    s = summarize_rows(rows)
    assert len(s["top_failures"]) == 10
    assert s["top_failures"][0]["label"] == "F11"


def test_novelty_series_groups_marks_by_batch_and_keeps_last_ten():
    shares = [1.0, 0.5, 0.4, 0.3, 0.2, 0.2, 0.2, 0.2, 0.1, 0.1, 0.3]
    rows = [
        _row(label=f"R{i}", sig=f"r{i}", marks=_marks_for_batches(shares, i))
        for i in range(10)
    ]
    s = summarize_rows(rows)
    assert len(s["novelty"]) == 10  # last 10 of 11
    assert s["novelty"][0]["share"] == pytest.approx(0.5)  # first batch trimmed off
    assert s["novelty"][-1] == {
        "at": "2026-07-20T00:00:00+00:00",
        "new": 3,
        "total": 10,
        "share": pytest.approx(0.3),
    }
    assert s["saturated"] is False


def _summary_for_tail(shares):
    # 20 rows @ rows_per_batch=20: a 0.05 share is 1 new row of 20 — genuinely
    # below the 10% saturation threshold (10 rows can't express that).
    rows = [
        _row(
            label=f"R{i}",
            sig=f"r{i}",
            marks=_marks_for_batches(shares, i, rows_per_batch=20),
        )
        for i in range(20)
    ]
    return summarize_rows(rows)


def test_saturated_exactly_three_consecutive_low_sessions():
    s = _summary_for_tail([1.0, 0.05, 0.05, 0.0])
    assert s["saturated"] is True
    assert s["recommendation"] == RECOMMEND_STOP


def test_high_session_resets_the_streak():
    # low, low, HIGH as the last three → not saturated
    assert _summary_for_tail([0.05, 0.05, 0.5])["saturated"] is False
    # HIGH inside the tail: last three are 0.5, 0.05, 0.05 → only 2 consecutive
    assert _summary_for_tail([0.05, 0.05, 0.5, 0.05, 0.05])["saturated"] is False
    # streak re-forms after the high session
    assert _summary_for_tail([0.5, 0.05, 0.05, 0.05])["saturated"] is True


def test_saturation_boundaries():
    # only 2 sessions, both low → not enough evidence
    assert _summary_for_tail([0.05, 0.05])["saturated"] is False
    # share exactly 0.10 is NOT "< 10%"
    assert _summary_for_tail([0.10, 0.05, 0.05])["saturated"] is False


def test_a_detection_row_leaves_every_figure_exactly_where_it_was():
    """The applied-detection watcher's row is not a form field, and this whole
    module answers questions about form fields.

    Asserted as WHOLE-SUMMARY EQUALITY rather than field by field, because the
    ways a non-form row leaks in are not all obvious: it would add a signature,
    an observation and a host to `totals`; a `signal` entry to `by_kind` with no
    success, no failure and a null rate; nothing to `top_failures` (its outcome
    is neutral) — and, least visibly and most damagingly, a novelty mark, which
    is what `saturated` is computed from and `saturated` is what tells the user
    "coverage saturated, you can turn capture off". One page event per
    application would drag that signal around while saying nothing about any
    form on any page.

    The rows below are built so every block has something to lose: two hosts,
    three kinds, a real success rate, a ranked failure, and a three-session
    low-novelty tail that puts `saturated` at True right on its boundary.
    """
    shares = [1.0, 0.05, 0.05, 0.0]
    form_rows = [
        _row(label=f"R{i}", sig=f"r{i}", marks=_marks_for_batches(shares, i, 20))
        for i in range(20)
    ]
    form_rows += [
        _row(label="Phone", kind="text", host="a.io", outcomes={"filled": 3, "not_stuck": 1}),
        _row(label="School", kind="combobox", host="b.io",
             outcomes={"combobox_snap_failed": 6}),
        _row(label="Consent", kind="checkbox", host="b.io", outcomes={"policy_blocked": 2}),
    ]
    baseline = summarize_rows(form_rows)
    assert baseline["saturated"] is True  # the signal that must not move

    detection = _row(
        label="applied detection",
        kind="signal",
        host="c.io",  # a host no form row uses: `totals.hosts` would notice
        sig="sig-applied",
        outcomes={"applied_detected": 4, "applied_dismissed": 1},
        marks=[{"at": at, "new": True} for at in
               sorted({mark["at"] for row in form_rows for mark in row.session_marks})],
    )

    assert summarize_rows([*form_rows, detection]) == baseline


def test_summary_endpoint_returns_contract(db_session):
    db_session.add(
        _row(
            label="Endpoint",
            outcomes={"no_rule": 2},
            marks=[{"at": "2026-07-20T00:00:00+00:00", "new": True}],
        )
    )
    db_session.commit()

    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        resp = TestClient(app).get("/api/autofill/telemetry/summary")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "totals",
        "by_kind",
        "top_failures",
        "novelty",
        "saturated",
        "recommendation",
    }
    assert body["totals"]["signatures"] == 1
    assert body["top_failures"][0]["label"] == "Endpoint"
    assert body["top_failures"][0]["signature_hash"] == "sig-Endpoint-text-h.io"
    assert body["novelty"] == [
        {
            "at": "2026-07-20T00:00:00+00:00",
            "new": 1,
            "total": 1,
            "share": 1.0,
        }
    ]
