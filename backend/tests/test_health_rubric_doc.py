from pathlib import Path
import json
from collections import Counter

from app.services import health_gates, health_score

ROOT = Path(__file__).resolve().parents[2]


def test_levels_gates_and_flags_are_documented():
    path = ROOT / "docs/health-check-rubric.md"
    assert path.exists()
    doc = path.read_text()
    for name in (*health_score.LEVEL_VALUES, *health_gates.GATE_LABELS, "evidence.no_numbers", "language.slip"):
        assert f"`{name}`" in doc


def test_golden_set_covers_roles_splits_and_disputes():
    path = ROOT / "backend/tests/fixtures/health_golden.json"
    assert path.exists()
    data = json.loads(path.read_text())
    cases = data["bullets"]
    assert len(cases) == 80
    assert len({c["text"] for c in cases}) == 80
    counts = Counter((c["role"], c["split"]) for c in cases)
    assert len(counts) == 16 and set(counts.values()) == {5}
    assert len(data["disputes"]) == 12
    assert all(c["expected_level"] in health_score.LEVEL_VALUES for c in cases)
    assert all(isinstance(c["number_natural"], bool) for c in cases)


def test_golden_metrics_enforce_each_role_not_only_overall():
    from scripts.health_golden import summarize
    cases = [dict(role="nursing", expected_level="direct", number_natural=False),
             dict(role="software", expected_level="direct", number_natural=True)]
    runs = [[dict(level="unaddressed", ask_kind="measure"), dict(level="direct", ask_kind=None)],
            [dict(level="adjacent", ask_kind="detail"), dict(level="direct", ask_kind=None)]]
    disputes = [dict(max_level="adjacent", metric_unavailable=True)]
    report = summarize(cases, runs, disputes, [[dict(level="direct", ask_kind="measure")]])
    assert report["overall"]["exact"] == 0.5
    assert report["roles"]["nursing"]["within_one"] == 0
    assert report["unnatural_number_asks"] == 1
    assert report["level_flips"] == 1
    assert report["disputes"]["above_max"] == 1
    assert report["disputes"]["measure_survived"] == 1
    assert report["passed"] is False


def test_golden_gate_accepts_agreement_and_rejects_missing_results():
    from scripts.health_golden import summarize
    cases = [dict(role="data", expected_level="direct", number_natural=False)]
    good = [[dict(level="direct", ask_kind=None)]] * 3
    assert summarize(cases, good, [], [[], [], []])["passed"] is True
    assert summarize(cases, [[{}]], [], [[]])["passed"] is False
