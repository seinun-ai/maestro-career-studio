# backend/tests/test_health_score.py
"""Invariants for the framework-v2 scorer. These need no DB and no LLM.

They encode the design doc's validation table: advisories-free and
position-invariance are structural (the scorer never sees findings or
positions), size invariance, target sanity, ceiling, monotonicity.
"""
import random

from app.services.health_score import (
    FATAL_CAP,
    LEVEL_VALUES,
    SERIOUS_CAP,
    apply_gates,
    compute_score,
    grade_for,
)


def gate(gate_id, status="fail", tier="serious"):
    return {"id": gate_id, "status": status, "tier": tier}


def test_score_is_mean_of_levels():
    assert compute_score([1.0, 0.5]) == 75
    assert compute_score([1.0, 1.0, 1.0]) == 100
    assert compute_score([0.0]) == 0


def test_empty_resume_scores_zero():
    assert compute_score([]) == 0


def test_size_invariance():
    levels = [1.0, 0.8, 0.5, 0.3]
    assert compute_score(levels) == compute_score(levels * 2)


def test_position_invariance():
    levels = [1.0, 0.8, 0.5, 0.3, 0.0, 0.8]
    shuffled = levels[:]
    random.Random(7).shuffle(shuffled)
    assert compute_score(levels) == compute_score(shuffled)


def test_target_sanity_recommended_resume_scores_at_least_75():
    # 60% quantified outcomes, rest specific-but-unnumbered
    levels = [1.0] * 6 + [0.5] * 4
    assert compute_score(levels) >= 75


def test_ceiling_reachable():
    assert compute_score([1.0] * 12) >= 90


def test_monotonicity_raising_a_level_never_lowers_score():
    ladder = [0.0, 0.3, 0.5, 0.8, 1.0]
    levels = [0.3, 0.5, 0.8]
    base = compute_score(levels)
    for i, lv in enumerate(levels):
        for higher in [v for v in ladder if v > lv]:
            bumped = levels[:]
            bumped[i] = higher
            assert compute_score(bumped) >= base


def test_grade_bands():
    assert grade_for(85) == "A"
    assert grade_for(70) == "B"
    assert grade_for(69) == "C"
    assert grade_for(55) == "C"
    assert grade_for(54) == "D"
    assert grade_for(40) == "D"
    assert grade_for(39) == "F"


def test_fatal_gate_caps_at_54():
    assert apply_gates(100, [gate("S1", tier="fatal")]) == FATAL_CAP
    assert grade_for(FATAL_CAP) == "D"


def test_one_serious_gate_caps_at_69():
    assert apply_gates(100, [gate("S3")]) == SERIOUS_CAP
    assert grade_for(SERIOUS_CAP) == "C"


def test_two_serious_gates_cap_at_54():
    assert apply_gates(100, [gate("S3"), gate("C1")]) == FATAL_CAP


def test_waived_and_not_assessed_and_passed_gates_do_not_cap():
    gates = [
        gate("S1", status="waived", tier="fatal"),
        gate("S3", status="not_assessed"),
        gate("S4", status="pass"),
    ]
    assert apply_gates(93, gates) == 93


def test_caps_never_raise_a_score():
    assert apply_gates(30, [gate("S1", tier="fatal")]) == 30


def test_level_values_match_design():
    assert LEVEL_VALUES == {
        "direct": 1.0,
        "analogue": 0.8,
        "adjacent": 0.5,
        "implied": 0.3,
        "unaddressed": 0.0,
    }
