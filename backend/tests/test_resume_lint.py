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


def test_score_is_mean_over_exp_projects_and_extras_not_summary():
    resume = _resume()
    levels = {
        ("summary", None, None): _lv(0.0),          # summary is NOT scored
        ("experience", 0, 0): _lv(1.0),
        ("experience", 0, 1): _lv(0.5),
        ("experience", 0, 2): _lv(0.5),
        ("extra:awards", None, 0): _lv(0.0),        # extras ARE scored
    }
    out = rl.assemble(resume, levels, PASS_GATES, "experienced", FULL_HOT)
    # mean(1.0, 0.5, 0.5, 0.0) = 0.5 → 50 ; the 0.0 summary does not drag it
    # down, the 0.0 extras bullet does — extras are in the mean.
    assert out["report"]["score"] == 50
    assert out["report"]["grade"] == "D"


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


def test_failed_gate_finding_reuses_its_gate_coaching_copy():
    """Generic gate coaching would hide the specific remedy the gate contract owns."""
    resume = _resume()
    levels = {("experience", 0, 0): _lv(1.0)}
    bad = [dict(g, status="fail") if g["id"] == "S3" else g for g in PASS_GATES]

    out = rl.assemble(resume, levels, bad, "experienced", {("experience", 0, 0)})
    gate = next(g for g in out["report"]["gates"] if g["id"] == "S3")
    finding = next(f for f in out["report"]["findings"] if f["type"] == "gate")

    assert finding["why"] == gate["why"]
    assert finding["how"] == gate["fix_hint"]


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


def test_ladder_items_includes_extra_sections():
    # Custom-section bullets join the evidence ladder and score (Tier 1 Task 5).
    # Extras stay out of hot zones and get no rewrite suggestions.
    resume = _resume()
    resume["extra_sections"] = [
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, 2025"]},
        {"key": "pubs", "title": "Publications", "type": "entries", "enabled": True,
         "entries": [{"heading": "Paper", "enabled": True,
                      "bullets": ["Bullet inside an extra section."]}]},
    ]
    items = rl._ladder_items(resume)
    assert {loc[0] for loc, _ in items} == {
        "summary", "experience", "extra:awards", "extra:pubs"}
    texts = [t for _, t in items]
    assert "Bullet inside an extra section." in texts
    assert "First place, 2025" in texts


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
    # gate_dates/gate_placeholders run for real; make S3 fail via a bad date, then waive it.
    # It must be a NON-EMPTY unparseable string: an absent start date is a legal
    # undated role and no longer fails S3.
    resume["experience"][0]["start_date"] = "whenever"      # S3 fails
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
    waived_s3 = next(g for g in waived.report_json["gates"] if g["id"] == "S3")
    ordinary_s5 = next(g for g in waived.report_json["gates"] if g["id"] == "S5")
    assert waived_s3["status"] == "waived"
    assert waived_s3["waiver_reason"] == "present role, dates implied"
    assert "waiver_reason" not in ordinary_s5


def test_trailing_punctuation_flagged_on_skills_and_certs():
    resume = _resume()
    resume["skills"] = [{"category": "Languages", "items": ["Python.", "SQL"]}]
    resume["certifications"] = ["AWS Certified AI Practitioner (AIF-C01).",
                                "IBM Data Science Professional Certificate"]
    notes = rl._advisories(resume)
    punct = [n for n in notes if "ends with a stray" in n["issue"]]
    assert len(punct) == 2
    assert any(n["location"]["section"] == "skills" and "Python." in n["label"] for n in punct)
    assert any(n["location"]["section"] == "certifications" and "(AIF-C01)." in n["label"] for n in punct)


def test_clean_items_emit_no_punctuation_notes():
    resume = _resume()
    resume["skills"] = [{"category": "Languages", "items": ["Python", "SQL"]}]
    resume["certifications"] = ["AWS Certified AI Practitioner (AIF-C01)"]
    assert not [n for n in rl._advisories(resume) if "ends with a stray" in n["issue"]]


def test_punctuation_note_names_the_actual_character():
    resume = _resume()
    resume["skills"] = [{"category": "Languages", "items": ["Python.", "SQL,", "Go…"]}]
    notes = rl._advisories(resume)
    punct = {n["label"]: n["issue"] for n in notes if "ends with a stray" in n["issue"]}
    assert "a stray period" in punct["Skills · Python."]
    assert "a stray comma" in punct["Skills · SQL,"]
    assert "a stray ellipsis" in punct["Skills · Go…"]


def test_duplicate_detection_ignores_trailing_punct_and_spacing():
    resume = _resume()
    resume["skills"] = [
        {"category": "Languages", "items": ["Python"]},
        {"category": "Tools", "items": [" python . "]},
    ]
    notes = rl._advisories(resume)
    assert any("appears in both" in n["issue"] for n in notes)


def test_certification_duplicates_flagged_punctuation_blind():
    resume = _resume()
    resume["certifications"] = [
        "AWS Certified AI Practitioner (AIF-C01)",
        "AWS  Certified AI Practitioner (AIF-C01).",
    ]
    notes = rl._advisories(resume)
    assert any(n["location"]["section"] == "certifications"
               and "more than once" in n["issue"] for n in notes)


def test_distinct_certifications_not_flagged_as_duplicates():
    resume = _resume()
    resume["certifications"] = [
        "AWS Certified AI Practitioner (AIF-C01)",
        "AWS Certified AI Practitioner (AIF-C02)",  # differs only in the code
    ]
    assert not any("more than once" in n["issue"] for n in rl._advisories(resume))


def test_punctuated_skill_matched_against_bullet_evidence():
    resume = _resume()
    resume["experience"][0]["bullets"] = ["Built things in Python daily."]
    resume["skills"] = [{"category": "Languages", "items": ["Python."]}]
    notes = rl._advisories(resume)
    assert not any("never demonstrated" in n["issue"] for n in notes)


def test_certification_duplicate_with_space_before_trailing_punctuation():
    # "_norm_item" must not leave a trailing space after stripping the
    # punctuation — a space *before* the punctuation (e.g. from "(X) .")
    # is the exact case that reopens the false positive this round fixes.
    resume = _resume()
    resume["certifications"] = [
        "AWS Certified AI Practitioner (AIF-C01)",
        "AWS Certified AI Practitioner (AIF-C01) .",
    ]
    notes = rl._advisories(resume)
    assert any(n["location"]["section"] == "certifications"
               and "more than once" in n["issue"] for n in notes)


def test_skill_with_space_before_punctuation_matched_against_bullet():
    # The bullet ends right after "Python" — no trailing text that would let a
    # leftover trailing space in the token accidentally still match.
    resume = _resume()
    resume["experience"][0]["bullets"] = ["Built things in Python."]
    resume["skills"] = [{"category": "Languages", "items": ["Python ."]}]
    notes = rl._advisories(resume)
    assert not any("never demonstrated" in n["issue"] for n in notes)


def test_bullet_blob_whitespace_normalized_for_never_demonstrated_check():
    # Pins the OTHER half of the never-demonstrated fix: the blob itself must
    # also have its whitespace collapsed, not just the skills token, or a
    # multi-word skill won't match a bullet where the words are separated by
    # something other than a single plain space (here, a newline).
    resume = _resume()
    resume["experience"][0]["bullets"] = ["Built systems using data\nmodeling techniques."]
    resume["skills"] = [{"category": "Languages", "items": ["data modeling"]}]
    notes = rl._advisories(resume)
    assert not any("never demonstrated" in n["issue"] for n in notes)


def test_sentence_like_skills_item_flagged():
    resume = _resume()
    resume["skills"] = [{"category": "GenAI", "items": [
        "built RAG pipelines with pgvector for semantic retrieval",  # 8 tokens
        "led the pgvector retrieval pipeline",  # 5 tokens (== MAX_SKILL_ITEM_WORDS) — must NOT flag
        "led the pgvector retrieval pipeline today",  # 6 tokens — one over the line, must flag
        "RAG pipelines",
    ]}]
    notes = rl._advisories(resume)
    hits = {n["label"] for n in notes if "reads like a sentence" in n["issue"]}
    assert hits == {
        "Skills · built RAG pipelines with pgvector for semantic retrieval",
        "Skills · led the pgvector retrieval pipeline today",
    }


def test_sentence_like_skills_items_have_distinct_ids():
    # Regression guard for the id-collision bug: the sentence-like rule's
    # location and old constant issue string made every hit share one id,
    # which collides as a React key on the health report page.
    resume = _resume()
    resume["skills"] = [{"category": "GenAI", "items": [
        "built RAG pipelines with pgvector for semantic retrieval",
        "designed distributed systems for high throughput workloads",
    ]}]
    notes = rl._advisories(resume)
    hits = [n for n in notes if "reads like a sentence" in n["issue"]]
    assert len(hits) == 2
    assert hits[0]["id"] != hits[1]["id"]


def test_long_certifications_not_flagged_as_sentences():
    resume = _resume()
    resume["certifications"] = [
        "Award: 1st Place, UTA Business Analytics Symposium AWS GenAI Hackathon (Mar 2026)"]
    assert not any("reads like a sentence" in n["issue"] for n in rl._advisories(resume))


def test_norm_item_folding_stays_in_sync_with_the_bullet_blob():
    # Guards _norm_item's stated invariant. Separator folding added for dedup
    # alone would falsely flag "Scikit-Learn" as never demonstrated.
    resume = _resume()
    resume["experience"][0]["bullets"] = ["Built models with Scikit-Learn in production."]
    resume["skills"] = [{"category": "ML", "items": ["Scikit-Learn"]}]
    assert not any("never demonstrated" in n["issue"] for n in rl._advisories(resume))


ALL_ADVISORY_RULE_CODES = {
    "summary.missing",
    "entry.too_many_bullets",
    "bullet.too_long",
    "bullet.too_short",
    "skills.duplicate_across_groups",
    "skills.undemonstrated",
    "skills.sentence_like",
    "skills.trailing_punct",
    "certifications.trailing_punct",
    "certifications.duplicate",
}


def _resume_tripping_every_advisory_rule():
    # One resume that trips all ten deterministic rules, so the rule-code
    # test pins the exact slug set rather than a subset a smaller fixture
    # would happen to cover.
    resume = _resume()
    resume["summary"] = ""  # summary.missing
    resume["experience"] = [{
        "company": "Acme", "role": "DS", "start_date": "Jan 2023", "end_date": "Present",
        "bullets": [
            "Managed onboarding docs.",       # 3 words -> bullet.too_short
            "word " * 40,                     # 40 words -> bullet.too_long
            "filler word " * 5,
            "filler word " * 5,
            "filler word " * 5,
            "filler word " * 5,
            "filler word " * 5,
            "filler word " * 5,
        ],  # 8 bullets total (> MAX_BULLETS_PER_ENTRY) -> entry.too_many_bullets
    }]
    resume["skills"] = [
        {"category": "Languages", "items": ["Python."]},  # skills.trailing_punct
        {"category": "Tools", "items": ["python"]},        # dup of "Python." across groups
        {"category": "GenAI", "items": [
            "built RAG pipelines with pgvector for semantic retrieval",  # skills.sentence_like
        ]},
    ]  # none of these appear in any bullet -> skills.undemonstrated too
    resume["certifications"] = ["AWS (X).", "AWS (X)"]  # trailing_punct + duplicate
    return resume


def test_every_advisory_note_carries_a_rule_code():
    resume = _resume_tripping_every_advisory_rule()
    rules = {note.get("rule") for note in rl._advisories(resume)}
    assert rules == ALL_ADVISORY_RULE_CODES


def test_rule_codes_identify_trailing_punctuation_by_section():
    resume = _resume()
    resume["skills"] = [{"category": "L", "items": ["Python."]}]
    resume["certifications"] = ["AWS (X)."]
    rules = {n["rule"] for n in rl._advisories(resume)}
    assert "skills.trailing_punct" in rules
    assert "certifications.trailing_punct" in rules


def test_rule_code_does_not_change_finding_ids():
    # _fid hashes type|location|issue — adding a field must not perturb ids.
    resume = _resume()
    resume["skills"] = [{"category": "L", "items": ["Python."]}]
    note = next(n for n in rl._advisories(resume) if n["rule"] == "skills.trailing_punct")
    assert note["id"] == rl._fid("note", ("skills", None, None), note["issue"])


def test_rule_notes_is_public_and_matches_advisories():
    resume = _resume()
    resume["skills"] = [{"category": "L", "items": ["built RAG pipelines with pgvector for retrieval"]}]
    assert rl.rule_notes(resume) == rl._advisories(resume)


def test_trailing_punctuation_notes_carry_the_offending_raw_text():
    # Task 2 (post-tailoring coherence check) needs the exact raw item text
    # for a trailing-punctuation note to compute a mechanical fix and use it
    # as an exact-match needle — not by parsing the label or issue prose.
    resume = _resume()
    resume["skills"] = [{"category": "L", "items": ["Python."]}]
    resume["certifications"] = ["AWS (X)."]
    notes = {n["rule"]: n for n in rl._advisories(resume) if n.get("rule", "").endswith(".trailing_punct")}
    assert notes["skills.trailing_punct"]["subject"] == "Python."
    assert notes["certifications.trailing_punct"]["subject"] == "AWS (X)."


def test_trailing_punctuation_subject_is_raw_not_stripped_for_padded_items():
    # subject is the exact-match needle a downstream consumer uses against
    # `items.index(subject)` / list membership on the resume's own array.
    # Regression: subject used to come from the already-.strip()'d local, so
    # a padded source item ("  Padded Skill.  ") yielded a subject that no
    # longer matched the raw array element.
    resume = _resume()
    padded_skill = "  Padded Skill.  "
    padded_cert = "  AWS (X).  "
    resume["skills"] = [{"category": "L", "items": [padded_skill]}]
    resume["certifications"] = [padded_cert]

    notes = {n["rule"]: n for n in rl._advisories(resume) if n.get("rule", "").endswith(".trailing_punct")}
    skill_note = notes["skills.trailing_punct"]
    cert_note = notes["certifications.trailing_punct"]

    # the needle is the exact, unstripped source string ...
    assert skill_note["subject"] == padded_skill
    assert cert_note["subject"] == padded_cert
    # ... which is what makes it findable in the resume's own arrays.
    assert skill_note["subject"] in resume["skills"][0]["items"]
    assert cert_note["subject"] in resume["certifications"]

    # the mechanical fix (strip a trailing run of punctuation-or-whitespace,
    # then strip the leading side) still derives the clean proposal.
    proposal = rl._TRAILING_PUNCT_RUN.sub("", skill_note["subject"]).strip()
    assert proposal == "Padded Skill"


def _extras_only_resume():
    return {
        "contact": {"name": "A", "email": "a@b.c"},
        "extra_sections": [
            {"key": "publications", "title": "Publications", "type": "entries",
             "entries": [{"heading": "Paper X", "enabled": True,
                          "bullets": ["Improved retrieval accuracy 12% on benchmark Y"]}]},
            {"key": "awards", "title": "Awards & Honors", "type": "bullets",
             "bullets": ["Dean's list 2019"]},
        ],
    }


def test_ladder_items_include_extras_bullets():
    items = rl._ladder_items(_extras_only_resume())
    locs = [loc for loc, _ in items]
    assert ("extra:publications", 0, 0) in locs
    assert ("extra:awards", None, 0) in locs


def test_extras_only_resume_scores_nonzero():
    resume = _extras_only_resume()
    levels = {("extra:publications", 0, 0): {"value": 0.8, "level": "analogue"},
              ("extra:awards", None, 0): {"value": 0.5, "level": "adjacent"}}
    out = rl.assemble(resume, levels, [], "experienced", set())
    assert out["report"]["score"] == 65  # mean of 0.8, 0.5


def test_extras_fix_candidates_never_get_rewrite_suggestions():
    resume = _extras_only_resume()
    levels = {("extra:publications", 0, 0): {"value": 0.0, "level": "unaddressed"}}
    out = rl.assemble(
        resume, levels, [], "experienced", set(), rewrite_fn=lambda t: "REWRITTEN")
    ladder = [f for f in out["report"]["findings"]
              if f["location"]["section"] == "extra:publications"]
    assert ladder and all(f["type"] == "ask" and f["suggestion"] is None for f in ladder)


def test_labels_and_text_resolve_for_extras():
    resume = _extras_only_resume()
    assert "Publications" in rl._label_at(resume, ("extra:publications", 0, 0))
    assert rl._text_at(resume, ("extra:awards", None, 0)) == "Dean's list 2019"


def test_stale_extras_locations_degrade_instead_of_raising():
    """A location can outlive its section (rename/delete between runs); the
    frontend returns null there — the backend must not IndexError."""
    resume = _extras_only_resume()
    for loc in [
        ("extra:gone", 0, 0),            # section deleted/renamed
        ("extra:gone", None, 0),         # flat section deleted/renamed
        ("extra:publications", 9, 0),    # entry index out of range
        ("extra:publications", 0, 9),    # bullet index out of range
        ("extra:awards", None, 9),       # flat bullet out of range
    ]:
        assert isinstance(rl._label_at(resume, loc), str)
        assert rl._text_at(resume, loc) == ""
