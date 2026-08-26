# backend/app/services/health_score.py
"""Deterministic scoring core for the resume health check (framework v2).

The LLM classifies; this module does ALL arithmetic. Score is the plain mean
of evidence levels — attention zones are deliberately NOT weights here (they
drive severity, ordering, C1, and UI only). Gate caps sit one point below the
band edges so a capped resume actually reads as the named grade.

See SYSTEM.md §4 (ResumeLintReport) for how this fits the wider check.
"""

from typing import Literal

LEVEL_VALUES: dict[str, float] = {
    "direct": 1.0,
    "analogue": 0.8,
    "adjacent": 0.5,
    "implied": 0.3,
    "unaddressed": 0.0,
}

GRADE_BANDS: tuple[tuple[int, str], ...] = ((85, "A"), (70, "B"), (55, "C"), (40, "D"))

FATAL_CAP = 54
SERIOUS_CAP = 69


def grade_for(score: int) -> str:
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return "F"


def compute_score(levels: list[float]) -> int:
    if not levels:
        return 0
    return round(100 * sum(levels) / len(levels))


def gate_cap_tier(gates: list[dict]) -> Literal["fatal", "serious"] | None:
    """The cap tier imposed by failed gates, using the scorer's exact rules."""
    failed = [g for g in gates if g.get("status") == "fail"]
    if any(g.get("tier") == "fatal" for g in failed):
        return "fatal"
    serious = [g for g in failed if g.get("tier") == "serious"]
    if len(serious) >= 2:
        return "fatal"
    if len(serious) == 1:
        return "serious"
    return None


def apply_gates(score: int, gates: list[dict]) -> int:
    """Cap `score` by failed gates. Waived / passed / not_assessed gates never cap."""
    cap_tier = gate_cap_tier(gates)
    if cap_tier == "fatal":
        return min(score, FATAL_CAP)
    if cap_tier == "serious":
        return min(score, SERIOUS_CAP)
    return score
