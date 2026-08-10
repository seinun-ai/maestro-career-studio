"""v2 health-check assembly tests.

Pure `assemble` tests need no DB/LLM (levels + rewrite_fn are passed in).
`run_report`/`structure_gates` tests use the DB fixture + monkeypatch.
"""
from copy import deepcopy

from app.services import resume_lint as rl


def _lv(value, uncertain=False):
    return {"level": rl._level_name(value), "value": value, "reason": "",
            "confidence": 1.0, "source": "cache", "uncertain": uncertain}


def _resume():
    return {
        "contact": {"email": "a@b.com", "phone": "555"},
        "summary": "Data scientist with 3 years building ML systems.",
        "experience": [
            {"company": "Acme", "role": "DS", "start_date": "Jan 2023", "end_date": "Present",
             "bullets": ["b0", "b1", "b2"]},
        ],
        "projects": [], "education": [], "skills": [],
    }


PASS_GATES = [
    {"id": "S1", "tier": "fatal", "status": "pass", "label": "Parse", "detail": ""},
    {"id": "S2", "tier": "fatal", "status": "pass", "label": "Contact", "detail": ""},
    {"id": "S4", "tier": "serious", "status": "pass", "label": "Headers", "detail": ""},
    {"id": "S3", "tier": "serious", "status": "pass", "label": "Dates", "detail": ""},
    {"id": "S5", "tier": "serious", "status": "pass", "label": "Placeholders", "detail": ""},
]

FULL_HOT = {("summary", None, None), ("experience", 0, 0),
            ("experience", 0, 1), ("experience", 0, 2)}


def test_score_is_mean_over_exp_and_projects_only():
    resume = _resume()
    levels = {
        ("summary", None, None): _lv(0.0),          # summary is NOT scored
        ("experience", 0, 0): _lv(1.0),
        ("experience", 0, 1): _lv(0.5),
        ("experience", 0, 2): _lv(0.5),
    }
    out = rl.assemble(resume, levels, PASS_GATES, "experienced", FULL_HOT)
    # mean(1.0, 0.5, 0.5) = 0.667 → 67 ; the 0.0 summary does not drag it down
    assert out["report"]["score"] == 67
    assert out["report"]["grade"] == "C"


def test_fatal_gate_caps_at_54():
    resume = _resume()
    levels = {("experience", 0, 0): _lv(1.0)}
    bad = [dict(g, status="fail") if g["id"] == "S1" else g for g in PASS_GATES]
    out = rl.assemble(resume, levels, bad, "experienced", {("experience", 0, 0)})
    assert out["report"]["score"] == 54
    assert out["report"]["grade"] == "D"


def test_dead_hot_zone_fires_c1_and_caps_at_69():
    resume = _resume()
    resume["experience"][0]["bullets"] = ["b0", "b1", "b2"] + [f"g{i}" for i in range(20)]
    levels = {("summary", None, None): _lv(0.0)}
    for i in range(3):
        levels[("experience", 0, i)] = _lv(0.0)
    for i in range(3, 23):
        levels[("experience", 0, i)] = _lv(1.0)
    out = rl.assemble(resume, levels, PASS_GATES, "experienced", FULL_HOT)
    assert out["report"]["score"] <= 69
    assert any(g["id"] == "C1" and g["status"] == "fail" for g in out["report"]["gates"])


def test_advisories_are_free():
    resume = _resume()
    resume["experience"][0]["bullets"] = ["word " * 40, "word " * 40, "word " * 40]  # 3 long bullets
    levels = {("experience", 0, i): _lv(1.0) for i in range(3)}
    hot = {("experience", 0, 0), ("experience", 0, 1), ("experience", 0, 2)}
    out = rl.assemble(resume, levels, PASS_GATES, "experienced", hot)
    assert out["report"]["score"] == 100  # notes never move the score
    assert any(f["type"] == "note" for f in out["report"]["findings"])


def test_c2_ask_first_then_cap_on_repeat():
    resume = _resume()
    levels = {("experience", 0, 0): _lv(1.0)}
    hot = {("experience", 0, 0)}
    c2 = {"claimed_years": 8, "actual_years": 3.0}
    first = rl.assemble(resume, levels, PASS_GATES, "experienced", hot, c2_hit=c2)
    assert first["report"]["score"] == 100
    assert next(g for g in first["report"]["gates"] if g["id"] == "C2")["status"] == "ask"
    assert any(f["type"] == "ask" for f in first["report"]["findings"])
    second = rl.assemble(resume, levels, PASS_GATES, "experienced", hot,
                         c2_hit=c2, prior_report=first["report"])
    assert second["report"]["score"] == 69
    assert next(g for g in second["report"]["gates"] if g["id"] == "C2")["status"] == "fail"


def test_c2_resolved_does_not_cap():
    # user fixed the summary → no c2_hit this run → no C2 gate, no cap
    resume = _resume()
    levels = {("experience", 0, 0): _lv(1.0)}
    hot = {("experience", 0, 0)}
    prior = rl.assemble(resume, levels, PASS_GATES, "experienced", hot,
                        c2_hit={"claimed_years": 8, "actual_years": 3.0})["report"]
    resolved = rl.assemble(resume, levels, PASS_GATES, "experienced", hot,
                           c2_hit=None, prior_report=prior)
    assert resolved["report"]["score"] == 100
    assert not any(g["id"] == "C2" for g in resolved["report"]["gates"])


def test_waiver_suppresses_gate_cap():
    resume = _resume()
    levels = {("experience", 0, 0): _lv(1.0)}
    hot = {("experience", 0, 0)}
    bad = [dict(g, status="fail") if g["id"] == "S3" else g for g in PASS_GATES]
    assert rl.assemble(resume, levels, bad, "experienced", hot)["report"]["score"] == 69
    waived = rl.assemble(resume, levels, bad, "experienced", hot, waivers={"S3"})
    assert waived["report"]["score"] == 100
    assert next(g for g in waived["report"]["gates"] if g["id"] == "S3")["status"] == "waived"


def test_fix_when_rewrite_exists_else_ask():
    resume = _resume()
    resume["experience"][0]["bullets"] = ["Responsible for stuff", "Responsible for things", "ok"]
    levels = {
        ("experience", 0, 0): _lv(0.0),
        ("experience", 0, 1): _lv(0.0),
        ("experience", 0, 2): _lv(1.0),
    }
    hot = {("experience", 0, 0), ("experience", 0, 1), ("experience", 0, 2)}

    def rw(text):
        return "Built stuff." if "stuff" in text else None

    out = rl.assemble(resume, levels, PASS_GATES, "experienced", hot, rewrite_fn=rw)
    by_bi = {f["location"].get("bullet_index"): f
             for f in out["report"]["findings"]
             if f["location"].get("section") == "experience"}
    assert by_bi[0]["type"] == "fix" and by_bi[0]["suggestion"] == "Built stuff."
    assert by_bi[1]["type"] == "ask"


def test_uncertain_routes_to_ask():
    resume = _resume()
    levels = {("experience", 0, 0): _lv(0.5, uncertain=True)}
    out = rl.assemble(resume, levels, PASS_GATES, "experienced", {("experience", 0, 0)})
    f = next(f for f in out["report"]["findings"] if f["location"].get("section") == "experience")
    assert f["type"] == "ask" and f["question"]


def test_classifier_finding_exposes_override_metadata():
    resume = _resume()
    text = resume["experience"][0]["bullets"][0]
    level = _lv(0.5)
    level.update({"source": "override", "reason": "Verified with the candidate."})
    levels = {("experience", 0, 0): level}

    out = rl.assemble(
        resume, levels, PASS_GATES, "experienced", {("experience", 0, 0)}
    )
    finding = next(
        f
        for f in out["report"]["findings"]
        if f["location"].get("bullet_index") == 0
    )

    assert finding["content_hash"] == rl.bullet_classify.content_hash(text)
    assert finding["classification_level"] == "adjacent"
    assert finding["classification_source"] == "override"
    assert finding["classification_reason"] == "Verified with the candidate."


def test_gap_emits_ask():
    resume = _resume()
    levels = {("experience", 0, 0): _lv(1.0)}
    gaps = [{"after": "A", "before": "B", "months": 12}]
    out = rl.assemble(resume, levels, PASS_GATES, "experienced", {("experience", 0, 0)},
                      gap_hits=gaps)
    assert any(f["type"] == "ask" and "gap" in f["issue"].lower()
               for f in out["report"]["findings"])


def test_findings_ordered_gates_first_then_cost_then_notes():
    resume = _resume()
    resume["experience"][0]["bullets"] = ["dead", "weak", "word " * 40]
    levels = {
        ("experience", 0, 0): _lv(0.0),   # high cost
        ("experience", 0, 1): _lv(0.5),   # lower cost
        ("experience", 0, 2): _lv(1.0),   # long bullet → note only
    }
    hot = {("experience", 0, 0), ("experience", 0, 1), ("experience", 0, 2)}
    bad = [dict(g, status="fail") if g["id"] == "S3" else g for g in PASS_GATES]
    out = rl.assemble(resume, levels, bad, "experienced", hot, rewrite_fn=lambda t: None)
    types = [f["type"] for f in out["report"]["findings"]]
    assert types[0] == "gate"                    # gate first
    assert types[-1] == "note"                   # note last
    # among fix/ask, higher cost precedes lower
    fa = [f for f in out["report"]["findings"] if f["type"] in ("fix", "ask")]
    costs = [f["cost"] for f in fa]
    assert costs == sorted(costs, reverse=True)


def test_determinism_same_input_same_report():
    resume = _resume()
    levels = {("experience", 0, 0): _lv(0.5), ("experience", 0, 1): _lv(0.0)}
    hot = {("experience", 0, 0)}
    a = rl.assemble(deepcopy(resume), dict(levels), PASS_GATES, "experienced", set(hot),
                    rewrite_fn=lambda t: None)
    b = rl.assemble(deepcopy(resume), dict(levels), PASS_GATES, "experienced", set(hot),
                    rewrite_fn=lambda t: None)
    assert a["report"] == b["report"]            # byte-identical incl. finding ids


# --------------------------------------------------------------------------- #
# run_report integration (DB + monkeypatched classify/gates)

def test_run_report_persists_features_and_model_version(db_session, monkeypatch):
    resume = _resume()
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, r: list(PASS_GATES))
    monkeypatch.setattr(
        rl.bullet_classify, "classify_items",
        lambda db, items: {rl.bullet_classify.content_hash(i["text"]): _lv(1.0) for i in items})
    monkeypatch.setattr(rl.model_settings, "get_smart_model", lambda db: "test-model")
    row = rl.run_report(db_session, "base", "k-features", resume, template_id=None)
    assert row.model_version == "health-v2"
    assert row.features_json is not None and "levels" in row.features_json
    assert row.report_json["grade"] == "A"


def test_run_report_persists_and_reuses_verifier_cache(db_session, monkeypatch):
    resume = _resume()
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, r: list(PASS_GATES))
    monkeypatch.setattr(
        rl.bullet_classify, "classify_items",
        lambda db, items: {rl.bullet_classify.content_hash(i["text"]): _lv(1.0) for i in items})
    monkeypatch.setattr(rl.model_settings, "get_smart_model", lambda db: "test-model")

    seen_prior = []

    def fake_verify(db, r, gap_hits, c2_hit, *, prior_cache=None):
        seen_prior.append(prior_cache)
        return gap_hits, c2_hit, {"cafe0123": {"verdict": "keep", "context": ""}}

    monkeypatch.setattr(rl.health_verify, "verify_detections", fake_verify)
    first = rl.run_report(db_session, "base", "k-verifier", resume, template_id=None)
    assert first.features_json["verifier"] == {"cafe0123": {"verdict": "keep", "context": ""}}
    assert seen_prior[0] is None  # no prior report on the first run

    rl.run_report(db_session, "base", "k-verifier", resume, template_id=None)
    # second run receives the first run's persisted verdict cache
    assert seen_prior[1] == {"cafe0123": {"verdict": "keep", "context": ""}}


def test_run_report_skips_verifier_without_llm(db_session, monkeypatch):
    resume = _resume()
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, r: list(PASS_GATES))

    def boom(*a, **k):
        raise AssertionError("verifier must not run when use_llm=False")

    monkeypatch.setattr(rl.health_verify, "verify_detections", boom)
    row = rl.run_report(db_session, "base", "k-nollm", resume,
                        template_id=None, use_llm=False)
    assert row.features_json["verifier"] == {}


def test_ladder_items_excludes_extra_sections():
    # Phase-1 ATS-neutral: classification/evidence scoring stays experience/
    # projects-only. Custom-section text must NOT become a scored ladder item.
    resume = _resume()
    resume["extra_sections"] = [
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, 2025"]},
        {"key": "pubs", "title": "Publications", "type": "entries", "enabled": True,
         "entries": [{"heading": "Paper", "enabled": True,
                      "bullets": ["Bullet inside an extra section."]}]},
    ]
    items = rl._ladder_items(resume)
    assert {loc[0] for loc, _ in items} <= {"summary", "experience", "projects"}
    texts = [t for _, t in items]
    assert "Bullet inside an extra section." not in texts
    assert "First place, 2025" not in texts


def test_run_report_scans_extras_without_crashing(db_session, monkeypatch):
    resume = _resume()
    resume["extra_sections"] = [
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, [YEAR]"]},
    ]
    # Real structure_gates only yields S1/S2/S4; gate_dates (S3) and
    # gate_placeholders (S5) run for real so S5 can see the extra-section text.
    monkeypatch.setattr(
        rl, "structure_gates",
        lambda db, tid, r: [g for g in PASS_GATES if g["id"] in ("S1", "S2", "S4")])
    row = rl.run_report(db_session, "base", "k-extras", resume,
                        template_id=None, use_llm=False)
    # Report builds (no crash) and S5 caught the placeholder inside the extra.
    assert {"score", "grade", "findings"} <= row.report_json.keys()
    s5 = next(g for g in row.report_json["gates"] if g["id"] == "S5")
    assert s5["status"] == "fail"
    assert "awards" in s5["detail"]
    # Extras never entered the evidence ladder / features levels.
    assert all(not loc.startswith("extra") for loc in row.features_json["levels"])


def test_run_report_reads_waivers_from_db(db_session, monkeypatch):
    from app.models.health_gate_waiver import HealthGateWaiver
    resume = _resume()
    bad = [dict(g, status="fail") if g["id"] == "S3" else g for g in PASS_GATES]
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, r: [g for g in bad if g["id"] in
                        ("S1", "S2", "S4")])
    # gate_dates/gate_placeholders run for real; make S3 fail via a bad date, then waive it
    resume["experience"][0]["start_date"] = ""      # S3 fails
    monkeypatch.setattr(
        rl.bullet_classify, "classify_items",
        lambda db, items: {rl.bullet_classify.content_hash(i["text"]): _lv(1.0) for i in items})
    monkeypatch.setattr(rl.model_settings, "get_smart_model", lambda db: "test-model")
    capped = rl.run_report(db_session, "base", "k-waive", resume, template_id=None)
    assert capped.report_json["score"] <= 69
    db_session.add(HealthGateWaiver(resume_kind="base", resume_key="k-waive",
                                    gate_id="S3", reason="present role, dates implied"))
    db_session.commit()
    waived = rl.run_report(db_session, "base", "k-waive", resume, template_id=None)
    assert next(g for g in waived.report_json["gates"] if g["id"] == "S3")["status"] == "waived"
