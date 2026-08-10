import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from app.services.ats import score_resume
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME

GOLDEN = Path(__file__).parent / "golden" / "sample.json"


def _golden_dump() -> dict:
    # asdict() covers every AtsResult field, so a newly added field breaks the
    # golden loudly instead of silently escaping snapshot coverage.
    return asdict(score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=date(2026, 7, 6)))


_BEHAVIORAL_ROW_KEYS = ("match_form", "matched", "placement", "fix_hint")


@pytest.mark.real_model
def test_engine_output_matches_golden():
    """Real-model regression guard — the ONE test that touches the pinned model.

    Marked `real_model` so the hermetic fake-embedder autouse fixture in
    tests/conftest.py skips it: this snapshot must reflect actual
    BAAI/bge-small-en-v1.5 output, so the whole engine (semantic layers
    included) runs end-to-end. First run downloads ~100MB into fastembed's local
    cache, then reuses it (a few seconds thereafter).

    Tolerance (post-review I3): embedding floats drift with model/onnxruntime
    builds, so this asserts the BEHAVIORAL contract exactly (each skill row's
    match_form/matched/placement/fix_hint, engine/config versions) while allowing
    small numeric drift (composite +/-0.5; subscores and contributions within 1%).
    A behavioral diff still fails loudly. Regenerate with
    `python -m tests.ats.test_golden` from backend/ and eyeball the numbers."""
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = _golden_dump()

    # exact: the behavioral contract
    assert actual["engine_version"] == expected["engine_version"]
    assert actual["config_version"] == expected["config_version"]
    assert actual["title_tier"] == expected["title_tier"]
    assert actual["gate_warnings"] == expected["gate_warnings"]
    assert actual["format_flags"] == expected["format_flags"]

    exp_rows = {r["jd_skill"]: r for r in expected["skill_table"]}
    act_rows = {r["jd_skill"]: r for r in actual["skill_table"]}
    assert set(act_rows) == set(exp_rows)
    for name, exp in exp_rows.items():
        act = act_rows[name]
        for key in _BEHAVIORAL_ROW_KEYS:
            assert act[key] == exp[key], f"{name}.{key}: {act[key]!r} != {exp[key]!r}"
        assert act["matched_term"] == exp["matched_term"], f"{name}.matched_term"
        assert act["evidence_entries"] == exp["evidence_entries"], f"{name}.evidence_entries"
        assert act["contribution"] == pytest.approx(exp["contribution"], rel=1e-2, abs=1e-3)

    # numeric: allow small model drift
    assert actual["composite"] == pytest.approx(expected["composite"], abs=0.5)
    assert set(actual["subscores"]) == set(expected["subscores"])
    for key, exp_val in expected["subscores"].items():
        assert actual["subscores"][key] == pytest.approx(exp_val, rel=1e-2, abs=1e-3)


@pytest.mark.real_model
def test_unrelated_skills_stay_absent_under_real_model():
    """False-positive guard (post-review C2): the anchor gate must keep genuinely
    unrelated JD skills from semantic-matching under the REAL model. SAMPLE_RESUME
    has no Docker or Salesforce evidence and no chunk sharing a token with either,
    so both must stay absent — proving the gate suppresses the zero-overlap class
    that the ungated 0.60 threshold manufactured (Salesforce->tableau bullet,
    Docker->git)."""
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=date(2026, 7, 6))
    rows = {r["jd_skill"]: r for r in result.skill_table}
    for skill in ("Docker", "Salesforce"):
        row = rows[skill]
        assert row["matched"] is False, f"{skill} should be absent, got {row['match_form']!r}"
        assert row["fix_hint"] == "absent"
    # and no semantic row may carry a raw bullet fragment as matched_term (C3)
    for row in result.skill_table:
        if row["match_form"] == "semantic":
            assert row["matched_term"] is None


if __name__ == "__main__":
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(
        json.dumps(_golden_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {GOLDEN}")
