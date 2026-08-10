"""Design validation-table invariants for the health check v2.

Scorer-level invariants (size/position invariance, target sanity, ceiling,
compute_score monotonicity, gate caps) live in test_health_score.py; assembly
behavior (C1/C2, waivers, fix-vs-ask, ordering) in test_resume_lint.py. This
file asserts the remaining design invariants at the assembly/integration level
so a future change that breaks one fails loudly.
"""
from copy import deepcopy

from app.services import health_score, resume_lint as rl


def _lv(value, uncertain=False):
    return {"level": rl._level_name(value), "value": value, "reason": "",
            "confidence": 1.0, "source": "cache", "uncertain": uncertain}


def _resume():
    return {
        "contact": {"email": "a@b.com"},
        "summary": "Data scientist with 3 years building ML systems.",
        "experience": [
            {"company": "Acme", "role": "DS", "start_date": "Jan 2023", "end_date": "Present",
             "bullets": ["b0", "b1", "b2"]},
        ],
        "projects": [], "education": [], "skills": [],
    }


PASS_GATES = [
    {"id": "S1", "tier": "fatal", "status": "pass", "label": "P", "detail": ""},
    {"id": "S2", "tier": "fatal", "status": "pass", "label": "C", "detail": ""},
    {"id": "S4", "tier": "serious", "status": "pass", "label": "H", "detail": ""},
    {"id": "S3", "tier": "serious", "status": "pass", "label": "D", "detail": ""},
    {"id": "S5", "tier": "serious", "status": "pass", "label": "PL", "detail": ""},
]


def test_advisories_are_free_many_notes_move_score_by_zero():
    r1 = _resume()
    lv = {("experience", 0, i): _lv(1.0) for i in range(3)}
    hot = {("experience", 0, 0), ("experience", 0, 1), ("experience", 0, 2)}
    base = rl.assemble(r1, lv, PASS_GATES, "experienced", hot)["report"]["score"]

    r2 = _resume()
    r2["experience"][0]["bullets"] = ["word " * 40, "word " * 40, "word " * 40]
    r2["skills"] = [
        {"category": "A", "items": [f"Skill{i}" for i in range(20)]},
        {"category": "B", "items": [f"Skill{i}" for i in range(20)]},  # dupes + undemonstrated
    ]
    out = rl.assemble(r2, lv, PASS_GATES, "experienced", hot)
    notes = [f for f in out["report"]["findings"] if f["type"] == "note"]
    assert len(notes) >= 10
    assert out["report"]["score"] == base


def test_determinism_five_runs_zero_variance():
    r = _resume()
    lv = {("experience", 0, 0): _lv(0.5), ("experience", 0, 1): _lv(0.0),
          ("summary", None, None): _lv(0.3)}
    hot = {("summary", None, None), ("experience", 0, 0)}
    reports = [
        rl.assemble(deepcopy(r), dict(lv), PASS_GATES, "experienced", set(hot),
                    rewrite_fn=lambda t: None)["report"]
        for _ in range(5)
    ]
    for rep in reports[1:]:
        assert rep == reports[0]


def test_monotonicity_raising_a_bullet_level_never_lowers_score():
    r = _resume()
    hot = {("experience", 0, 0), ("experience", 0, 1), ("experience", 0, 2)}
    low = {("experience", 0, 0): _lv(0.0), ("experience", 0, 1): _lv(0.5),
           ("experience", 0, 2): _lv(0.5)}
    base = rl.assemble(r, low, PASS_GATES, "experienced", hot)["report"]["score"]
    for bump_to in (0.3, 0.5, 0.8, 1.0):
        raised = dict(low)
        raised[("experience", 0, 0)] = _lv(bump_to)
        s = rl.assemble(r, raised, PASS_GATES, "experienced", hot)["report"]["score"]
        assert s >= base


def test_no_finding_lacks_a_remedy():
    r = _resume()
    r["experience"][0]["bullets"] = ["Responsible for things", "did a specific thing", "word " * 40]
    lv = {("summary", None, None): _lv(0.3),
          ("experience", 0, 0): _lv(0.0),
          ("experience", 0, 1): _lv(0.5),
          ("experience", 0, 2): _lv(1.0)}
    hot = {("summary", None, None), ("experience", 0, 0),
           ("experience", 0, 1), ("experience", 0, 2)}
    bad = [dict(g, status="fail") if g["id"] == "S3" else g for g in PASS_GATES]
    out = rl.assemble(r, lv, bad, "experienced", hot,
                      gap_hits=[{"after": "A", "before": "B", "months": 12}],
                      c2_hit={"claimed_years": 8, "actual_years": 3.0},
                      rewrite_fn=lambda t: "Built a specific thing serving many users.")
    for f in out["report"]["findings"]:
        has_remedy = (
            bool(f.get("suggestion"))
            or bool(f.get("question"))
            or bool((f.get("how") or "").strip())
        )
        assert has_remedy, f"finding without remedy: {f['type']} / {f['label']} / {f['issue']}"


def test_unrun_gate_is_not_a_passed_gate(db_session, monkeypatch):
    class _FakeTemplate:
        id = "faketmpl"
        parse_certified = None
        parse_report_json = None

    monkeypatch.setattr(rl.template_registry, "get_usable_template",
                        lambda tid, db: _FakeTemplate())

    def _boom(tid, db):
        raise RuntimeError("no pdflatex")

    monkeypatch.setattr(rl.template_validation, "validate_template", _boom)
    gates = rl.structure_gates(db_session, "faketmpl", _resume())
    s1 = next(g for g in gates if g["id"] == "S1")
    assert s1["status"] == "not_assessed"
    assert health_score.apply_gates(90, gates) == 90
