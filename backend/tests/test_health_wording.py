"""Task 10a: the Wording checklist, backend half.

Clichés and filler come from an editable word bank matched in CODE
(`health_wording`); spelling and grammar slips come from the classifier's
stored `language` field. All of it is a zero-score `note`, and Remove / Apply
text becomes a `suggestion` only when `health_guards` accepts it.
"""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.setting import Setting
from app.services import bullet_classify, coherence_check, health_wording
from app.services import resume_lint as rl

DEFAULT = health_wording.DEFAULT_BANK


def _lv(value, language=None, uncertain=False):
    return {"level": rl._level_name(value), "value": value, "reason": "",
            "confidence": 1.0, "source": "cache", "uncertain": uncertain,
            "language": language or []}


def _resume(bullets, summary="Data scientist with 3 years building ML systems."):
    return {
        "contact": {"email": "a@b.com"},
        "summary": summary,
        "experience": [
            {"company": "Acme", "role": "DS", "start_date": "Jan 2023", "end_date": "Present",
             "bullets": list(bullets)},
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


def _wording(notes):
    return [n for n in notes if str(n.get("rule", "")).startswith("language.")]


def _subjects(notes, rule):
    return {n["subject"] for n in notes if n.get("rule") == rule}


# --------------------------------------------------------------------------- #
# matcher + the default bank

def test_the_defaults_flag_results_driven_and_successfully():
    resume = _resume(["Successfully migrated the billing service to a new queue"],
                     summary="Results-driven engineer who ships reliable systems.")
    notes = _wording(rl.rule_notes(resume))
    assert _subjects(notes, "language.cliche") == {"results-driven"}
    assert _subjects(notes, "language.filler") == {"successfully"}
    cliche = next(n for n in notes if n["rule"] == "language.cliche")
    assert cliche["location"] == {"section": "summary"}
    assert cliche["issue"] == "'results-driven' is a cliché."
    filler = next(n for n in notes if n["rule"] == "language.filler")
    assert filler["location"] == {"section": "experience", "index": 0, "bullet_index": 0}
    assert filler["issue"] == "'successfully' adds nothing."


def test_matching_is_whole_word_and_case_insensitive():
    hits = health_wording.matches("A DYNAMIC team; very dynamically; non-dynamic; dynamic-range", DEFAULT)
    assert hits == [("cliche", "dynamic"), ("filler", "very")]


def test_one_note_per_location_and_word():
    resume = _resume(["Very very quickly shipped the very first release to customers"])
    notes = _wording(rl.rule_notes(resume))
    assert [n["subject"] for n in notes] == ["very"]


def test_a_user_added_word_flags():
    bank = health_wording.WordBank(cliche=(*DEFAULT.cliche, "rockstar"), filler=DEFAULT.filler)
    resume = _resume(["Rockstar engineer on the payments team for three years"])
    assert _subjects(rl.rule_notes(resume, word_bank=bank), "language.cliche") == {"rockstar"}
    assert not _wording(rl.rule_notes(resume))


def test_a_removed_default_stops_flagging():
    bank = health_wording.WordBank(
        cliche=DEFAULT.cliche, filler=tuple(w for w in DEFAULT.filler if w != "successfully"))
    resume = _resume(["Successfully migrated the billing service to a new queue"])
    assert _subjects(rl.rule_notes(resume), "language.filler") == {"successfully"}
    assert not _wording(rl.rule_notes(resume, word_bank=bank))


def test_never_flag_beats_the_bank():
    bank = health_wording.WordBank(cliche=DEFAULT.cliche, filler=DEFAULT.filler,
                                   ignored=("successfully",))
    resume = _resume(["Successfully migrated the billing service, a dynamic system"])
    notes = _wording(rl.rule_notes(resume, word_bank=bank))
    assert _subjects(notes, "language.filler") == set()
    assert _subjects(notes, "language.cliche") == {"dynamic"}


def test_dynamic_programming_still_flags_dynamic():
    """Known limitation (docs/health-check-rubric.md): matching is context-blind."""
    resume = _resume(["Applied dynamic programming to cut route planning time in half"])
    assert _subjects(rl.rule_notes(resume), "language.cliche") == {"dynamic"}


def test_every_scored_bullet_is_checked_but_skills_are_not():
    resume = _resume(["Built various dashboards for the sales team every quarter"])
    resume["projects"] = [{"name": "P", "bullets": ["Wrote several parsers for log files in Rust"]}]
    resume["extra_sections"] = [{"key": "vol", "title": "Volunteering", "type": "bullets",
                                 "bullets": ["Really enjoyed mentoring new volunteers each week"]}]
    resume["skills"] = [{"category": "Soft", "items": ["Team player"]}]
    notes = _wording(rl.rule_notes(resume))
    assert {(n["location"]["section"], n["subject"]) for n in notes} == {
        ("experience", "various"), ("projects", "several"), ("extra:vol", "really")}


# --------------------------------------------------------------------------- #
# Remove: clean text, guarded

@pytest.mark.parametrize("text, word, expected", [
    ("Successfully led the migration", "successfully", "Led the migration"),
    ("Successfully, led the migration", "successfully", "Led the migration"),
    ("successfully led the migration", "successfully", "led the migration"),
    ("Led the migration successfully.", "successfully", "Led the migration."),
    ("Led the migration, successfully, ahead of schedule", "successfully",
     "Led the migration ahead of schedule"),
    ("Led the migration , successfully .", "successfully", "Led the migration."),
    ("Built various dashboards", "various", "Built dashboards"),
    ("Engineer. Successfully led the migration", "successfully",
     "Engineer. Led the migration"),
    ("I think outside the box daily", "think outside the box", "I daily"),
    ("Hired a results-driven data analyst", "results-driven", "Hired a data analyst"),
    ("A dynamic, detail-oriented engineer", "dynamic", "A detail-oriented engineer"),
    ("Very very fast", "very", "Fast"),
    # the article follows the next word
    ("A dynamic engineer", "dynamic", "An engineer"),
    ("Joined as a proactive owner of billing", "proactive", "Joined as an owner of billing"),
    ("Hired an efficiently run team", "efficiently", "Hired a run team"),
    # the comma directly after the cut word goes (no determiner needed)
    ("Built dynamic, scalable systems", "dynamic", "Built scalable systems"),
    ("Built various, reusable dashboards", "various", "Built reusable dashboards"),
    ("Led the migration successfully, then retired the old queue", "successfully",
     "Led the migration then retired the old queue"),
    # no empty brackets, dangling slash or stray dash
    ("Led the migration (successfully) on time", "successfully", "Led the migration on time"),
    ("Kept it very/really simple", "very", "Kept it really simple"),
    ("Kept it really/very simple", "very", "Kept it really simple"),
    ("Shipped it - successfully - on time", "successfully", "Shipped it - on time"),
    ("Successfully - shipped it on time", "successfully", "Shipped it on time"),
    ("Shipped it on time - successfully", "successfully", "Shipped it on time"),
    ("very\nvery\nvery\nvery", "very", ""),
])
def test_remove_produces_clean_text(text, word, expected):
    assert health_wording.remove(text, word) == expected


def test_remove_leaves_no_double_space():
    out = health_wording.remove("Shipped   successfully   -   on time", "successfully")
    assert "  " not in out


def test_remove_note_carries_a_guarded_suggestion_subject_and_hash():
    text = "Successfully led the AWS migration for the billing team"
    resume = _resume([text])
    [note] = _wording(rl.rule_notes(resume))
    assert note["suggestion"] == "Led the AWS migration for the billing team"
    assert note["subject"] == "successfully"
    assert note["content_hash"] == bullet_classify.content_hash(text)
    assert note["type"] == "note" and note["cost"] == 0 and note["severity"] == "minor"


def test_remove_that_drops_a_proper_noun_gets_no_suggestion():
    # "Dynamic" mid-sentence is capitalised, so the guard reads it as an entity.
    resume = _resume(["Built the Dynamic Pricing engine for the retail team"])
    [note] = _wording(rl.rule_notes(resume))
    assert note["subject"] == "dynamic"
    assert note["suggestion"] is None


# --------------------------------------------------------------------------- #
# slips (the classifier's `language` field)

def _assemble(resume, levels, bank=DEFAULT):
    return rl.assemble(resume, levels, PASS_GATES, "experienced", set(levels),
                       word_bank=bank)["report"]


def test_a_slip_note_swaps_the_span_for_the_fix():
    text = "Maintaned the nightly ETL jobs that feed the finance warehouse"
    resume = _resume([text])
    report = _assemble(resume, {("experience", 0, 0): _lv(1.0, [
        {"span": "Maintaned", "fix": "Maintained"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["issue"] == "'Maintaned' looks like a slip: 'Maintained'."
    assert slip["suggestion"] == "Maintained the nightly ETL jobs that feed the finance warehouse"
    assert slip["subject"] == "Maintaned"
    assert slip["content_hash"] == bullet_classify.content_hash(text)
    assert slip["type"] == "note" and slip["cost"] == 0


def _slip(text, span, fix):
    report = _assemble(_resume([text]), {("experience", 0, 0): _lv(1.0, [
        {"span": span, "fix": fix}])})
    return [f for f in report["findings"] if f.get("rule") == "language.slip"]


def test_a_slip_span_that_occurs_twice_is_copy_only():
    [slip] = _slip("Ran a hour-long review of a data pipeline", "a", "an")
    assert slip["suggestion"] is None


def test_a_slip_span_inside_a_hyphenated_word_does_not_count():
    [slip] = _slip("Built in-house dashboards in a single week", "in", "within")
    assert slip["suggestion"] == "Built in-house dashboards within a single week"


def test_a_slip_span_found_only_inside_another_word_gets_no_note():
    assert _slip("Maintained the nightly ETL jobs for the finance team", "tain", "tin") == []
    assert _slip("Owned the in-house ETL jobs for the finance team", "in", "on") == []


def test_apply_fix_is_none_unless_the_span_occurs_once():
    assert health_wording.apply_fix("a hour and a day", "a", "an") is None
    assert health_wording.apply_fix("teh cat", "teh", "the") == "the cat"
    assert health_wording.apply_fix("shipped it", "shipped it.", "x") is None


def test_slips_cover_the_summary_too():
    resume = _resume(["Owned the release train for the mobile app across teams"],
                     summary="Engineer whom ships reliable systems.")
    report = _assemble(resume, {("summary", None, None): _lv(0.5, [
        {"span": "whom", "fix": "who"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["location"] == {"section": "summary"}
    assert slip["suggestion"] == "Engineer who ships reliable systems."


def test_a_slip_fix_that_introduces_a_digit_gets_no_suggestion():
    resume = _resume(["Trained two new analysts on the reporting stack this year"])
    report = _assemble(resume, {("experience", 0, 0): _lv(1.0, [
        {"span": "two", "fix": "2"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["suggestion"] is None


def test_a_slip_fix_that_drops_a_proper_noun_gets_no_suggestion():
    resume = _resume(["Moved the ingest jobs from Airflow to cron on one host"])
    report = _assemble(resume, {("experience", 0, 0): _lv(1.0, [
        {"span": "from Airflow to cron", "fix": "to cron"}])})
    [slip] = [f for f in report["findings"] if f.get("rule") == "language.slip"]
    assert slip["suggestion"] is None


def test_never_flag_beats_a_slip_span():
    resume = _resume(["Maintaned the nightly ETL jobs that feed the finance warehouse"])
    levels = {("experience", 0, 0): _lv(1.0, [{"span": "Maintaned", "fix": "Maintained"}])}
    bank = health_wording.WordBank(cliche=DEFAULT.cliche, filler=DEFAULT.filler,
                                   ignored=("maintaned",))
    assert [f for f in _assemble(resume, levels)["findings"] if f.get("rule") == "language.slip"]
    assert not [f for f in _assemble(resume, levels, bank)["findings"]
                if f.get("rule") == "language.slip"]


# --------------------------------------------------------------------------- #
# never suppressed, never scored

def test_wording_notes_survive_a_ladder_ask_on_the_same_bullet():
    resume = _resume(["Successfully shipped it"])  # also short: bullet.too_short is suppressed
    levels = {("experience", 0, 0): _lv(0.5, [{"span": "shipped it", "fix": "shipped it."}])}
    report = _assemble(resume, levels)
    at_bullet = [f for f in report["findings"]
                 if f["location"] == {"section": "experience", "index": 0, "bullet_index": 0}]
    assert any(f["type"] == "ask" for f in at_bullet)
    rules = {f.get("rule") for f in at_bullet}
    assert {"language.filler", "language.slip"} <= rules
    assert "bullet.too_short" not in rules  # the old skip still applies to other advisories


# --------------------------------------------------------------------------- #
# storage

def test_an_absent_row_means_the_defaults(db_session):
    assert health_wording.load(db_session) == DEFAULT
    assert db_session.get(Setting, health_wording.BANK_KEY) is None


def test_save_normalizes_and_load_reads_it_back(db_session):
    health_wording.save(db_session, cliche=[" Rockstar ", "rockstar", "Ninja"],
                        filler=["very"], ignored=["Dynamic"])
    bank = health_wording.load(db_session)
    assert bank.cliche == ("rockstar", "ninja")
    assert bank.filler == ("very",)
    assert bank.ignored == ("dynamic",)


def test_reset_restores_the_defaults_but_keeps_the_ignored_list(db_session):
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=["dynamic"])
    bank = health_wording.reset(db_session)
    assert (bank.cliche, bank.filler) == (DEFAULT.cliche, DEFAULT.filler)
    assert bank.ignored == ("dynamic",)
    assert health_wording.load(db_session) == bank


def test_a_first_edit_that_loses_the_insert_race_retries_as_an_update(db_session, monkeypatch):
    from sqlalchemy import insert
    # Another request inserted both rows between our read and our commit.
    db_session.execute(insert(Setting).values(key=health_wording.BANK_KEY, value="{}"))
    db_session.execute(insert(Setting).values(key=health_wording.IGNORED_KEY, value="[]"))
    db_session.commit()
    real_get, calls = db_session.get, []

    def stale_get(model, key):
        calls.append(key)
        return None if len(calls) <= 2 else real_get(model, key)

    monkeypatch.setattr(db_session, "get", stale_get)
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=["dynamic"])
    monkeypatch.undo()
    bank = health_wording.load(db_session)
    assert (bank.cliche, bank.ignored) == (("rockstar",), ("dynamic",))
    assert len(calls) == 4  # one failed attempt, one retry


def test_a_corrupt_row_reads_as_the_defaults(db_session):
    db_session.add(Setting(key=health_wording.BANK_KEY, value="{not json"))
    db_session.add(Setting(key=health_wording.IGNORED_KEY, value='{"a": 1}'))
    db_session.commit()
    assert health_wording.load(db_session) == DEFAULT


def test_run_report_uses_the_users_bank(db_session, monkeypatch):
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=[])
    resume = _resume(["Rockstar engineer who successfully owned the payments service"])
    monkeypatch.setattr(rl, "structure_gates", lambda db, tid, data: list(PASS_GATES))
    row = rl.run_report(db_session, "base", "wording", resume, use_llm=False)
    notes = _wording(row.report_json["findings"])
    assert {n["subject"] for n in notes} == {"rockstar"}


def test_the_coherence_check_uses_the_users_bank(db_session, monkeypatch):
    monkeypatch.setattr(coherence_check.resume_lint, "structure_gates", lambda *a, **k: [])
    monkeypatch.setattr(coherence_check.llm, "call_openai", lambda **k: {"flags": []})
    monkeypatch.setattr(coherence_check.model_settings, "get_fast_model", lambda s=None: "fast")
    base = _resume(["Owned the payments service for the retail checkout team"])
    tailored = deepcopy(base)
    tailored["experience"][0]["bullets"] = ["Rockstar owner of the payments service for checkout"]

    assert not [e for e in coherence_check.run(base, tailored, db_session)["hygiene"]
                if e["rule"].startswith("language.")]
    health_wording.save(db_session, cliche=["rockstar"], filler=[], ignored=[])
    hygiene = coherence_check.run(base, tailored, db_session)["hygiene"]
    assert [e["rule"] for e in hygiene if e["rule"].startswith("language.")] == ["language.cliche"]


# --------------------------------------------------------------------------- #
# router

@pytest.fixture
def client(db_session):
    def _inner():
        yield db_session
    app.dependency_overrides[get_db] = _inner
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_wording_returns_the_bank_ignored_and_defaults(client):
    body = client.get("/api/resume-lint/wording").json()
    assert body == {
        "cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler), "ignored": [],
        "defaults": {"cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler)},
    }


def test_put_wording_trims_lowercases_and_dedupes(client):
    r = client.put("/api/resume-lint/wording", json={
        "cliche": [" Rockstar", "rockstar ", "Team  Player"], "filler": ["VERY"],
        "ignored": ["Dynamic", "dynamic"]})
    assert r.status_code == 200
    body = r.json()
    assert body["cliche"] == ["rockstar", "team player"]
    assert body["filler"] == ["very"]
    assert body["ignored"] == ["dynamic"]
    assert client.get("/api/resume-lint/wording").json() == body


@pytest.mark.parametrize("bad", [
    {"cliche": [""], "filler": [], "ignored": []},
    {"cliche": ["   "], "filler": [], "ignored": []},
    {"cliche": [], "filler": ["x" * 41], "ignored": []},
    {"cliche": [], "filler": [], "ignored": [f"w{i}" for i in range(201)]},
    {"cliche": [], "filler": []},
    {"cliche": [3], "filler": [], "ignored": []},
])
def test_put_wording_rejects_bad_lists_with_422(client, bad):
    r = client.put("/api/resume-lint/wording", json=bad)
    assert r.status_code == 422
    assert client.get("/api/resume-lint/wording").json()["cliche"] == list(DEFAULT.cliche)


def test_put_wording_accepts_200_entries_after_dedupe(client):
    words = [f"w{i}" for i in range(200)]
    r = client.put("/api/resume-lint/wording",
                   json={"cliche": words + ["W0"], "filler": [], "ignored": []})
    assert r.status_code == 200
    assert len(r.json()["cliche"]) == 200


def test_reset_wording_restores_defaults_and_keeps_ignored(client):
    client.put("/api/resume-lint/wording",
               json={"cliche": ["rockstar"], "filler": [], "ignored": ["dynamic"]})
    r = client.post("/api/resume-lint/wording/reset")
    assert r.status_code == 200
    assert r.json() == {
        "cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler), "ignored": ["dynamic"],
        "defaults": {"cliche": list(DEFAULT.cliche), "filler": list(DEFAULT.filler)},
    }
