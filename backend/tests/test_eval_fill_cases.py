"""The fill-decision evaluation's labelled cases are well formed (offline: no
model is called). scripts/eval_fill_decisions.py runs them against the models."""

import os
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from app.services.autofill_catalog import describe_of
from app.services.autofill_slots import policy_for
from scripts import eval_fill_decisions as ev

PICKS = ev.load_cases(ev.PICK_CASES)
STEPS = ev.load_cases(ev.STEP_CASES)


def test_the_case_files_hold_the_plans_counts():
    # 80 was the plan's; live iCIMS cases (2026-10-01) are added as they are found.
    assert 38 <= len(PICKS["cases"]) <= 90
    assert 18 <= len(STEPS["cases"]) <= 45
    assert STEPS["today"] == PICKS["today"]
    for cases in (PICKS["cases"], STEPS["cases"]):
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids)), [i for i, n in Counter(ids).items() if n > 1]


@pytest.mark.parametrize("case", PICKS["cases"], ids=lambda c: c["id"])
def test_every_pick_case_is_well_formed(case):
    ev.check_pick_case(case)
    ev.pick_field(case)   # a request /pick accepts
    facts = ev.case_facts(case, PICKS["today"])
    if case.get("slot"):
        assert facts[case["slot"]].policy == policy_for(case["slot"])
    # Only a case whose history lists the job's company carries "worked here".
    listed = any(j["employer"] == ev.HINT_COMPANY for j in (case.get("history") or {}).get("jobs", []))
    if case.get("slot") != "derived.previously_employed_here":
        assert ("derived.previously_employed_here" in facts) is listed


@pytest.mark.parametrize("case", STEPS["cases"], ids=lambda c: c["id"])
def test_every_step_case_is_well_formed(case):
    ev.check_step_case(case)


def test_the_plans_labelled_cases_are_there():
    """Revision plan Task 12 item 4, and the original Task 10 coverage."""
    by_id = {c["id"]: c for c in PICKS["cases"]}
    assert (by_id["degree-masters-closest"]["fact"], by_id["degree-masters-closest"]["expected"]) == (
        "Masters of Business analytics", "Masters")
    assert (by_id["no-to-not-applicable"]["fact"], by_id["no-to-not-applicable"]["expected"]) == ("No", "Not Applicable")
    assert by_id["eeo-race-asian"]["expected"] == "Asian (Not Hispanic or Latino) (United States of America)"
    assert by_id["reasoned-gov-no"]["route"] == "reasoned" and "government" in by_id["reasoned-gov-no"]["question"]
    on, off = by_id["low-stakes-jd-experience-on"], by_id["low-stakes-jd-experience-off"]
    assert (on["question"], on["low_stakes"], off["low_stakes"]) == (off["question"], "on", "off")
    assert (on["expected"], off["expected"]) == ("Yes", None)
    policies = Counter(ev.policy_of(c) for c in PICKS["cases"])
    assert all(policies[p] >= 2 for p in ("exact", "flag", "any", "low_stakes", "reasoned")), policies
    # Abstaining is the right answer somewhere in each kind that can abstain.
    assert {ev.policy_of(c) for c in PICKS["cases"] if c["expected"] is None} >= {
        "exact", "flag", "low_stakes", "reasoned"}
    assert off.get("code_path") is True and sum(bool(c.get("code_path")) for c in PICKS["cases"]) == 1
    steps = {c["id"] for c in STEPS["cases"]}
    # Exact-policy steps with near-miss options.
    assert sum(ev.policy_of(c) == "exact" for c in STEPS["cases"]) >= 7
    assert {"category-job-board", "popup-needs-search", "not-in-list", "scroll-for-masters"} <= steps
    assert sum(ev.expected_of(c) == ["give_up"] for c in STEPS["cases"]) >= 3


def test_every_mapped_rule_is_a_real_rule_and_names_a_slot():
    ids = ev.rule_ids()
    assert "first-name" in ids and "disability" in ids   # the scan reads both tables
    assert set(ev.RULE_TO_SLOT) <= ids, set(ev.RULE_TO_SLOT) - ids
    for rule, slot in ev.RULE_TO_SLOT.items():
        assert slot.split(".", 1)[0] in {"personal", "derived", "work_auth", "education", "experience", "skills",
                                         "eligibility", "preferences", "eeo"}, rule


def test_a_reasoned_case_becomes_the_history_the_route_reads():
    from app.services.autofill_reasoned import history

    case = next(c for c in PICKS["cases"] if c["id"] == "reasoned-gov-no")
    hist = history(ev.case_facts(case, PICKS["today"]))
    assert hist["today"] == PICKS["today"]
    assert [j["id"] for j in hist["jobs"]] == ["j1", "j2"] and hist["jobs"][0]["current"] == "Yes"
    assert "end" not in hist["jobs"][0] and hist["jobs"][1]["end"] == "2023-01"
    assert [s["id"] for s in hist["schools"]] == ["s1"]


def test_a_step_that_clicks_an_option_not_stating_the_fact_is_a_wrong_click(monkeypatch):
    """The scorer, with /step stubbed: no model is called."""
    from app.schemas.autofill_fill import StepResponse
    from app.services import autofill_step

    case = next(c for c in STEPS["cases"] if c["id"] == "category-leaf")
    for mid, outcome in (("click:o4", "right"), ("click:o5", "wrong_click"), (None, "give_up")):
        monkeypatch.setattr(autofill_step, "step", lambda *_a, mid=mid, **_k: StepResponse(
            mid=mid, reason="matched" if mid else "abstained"))
        assert ev.run_step(case, ev.Run("fast"), None, PICKS["today"])["outcome"] == outcome
    harmless = next(c for c in STEPS["cases"] if c["id"] == "not-in-list")
    monkeypatch.setattr(autofill_step, "step", lambda *_a, **_k: StepResponse(mid="click:o3", reason="matched"))
    assert ev.run_step(harmless, ev.Run("fast"), None, PICKS["today"])["outcome"] == "harmless"


def test_a_pick_is_scored_against_what_it_names(monkeypatch):
    from app.schemas.autofill_fill import Picked
    from app.services import autofill_pick

    case = next(c for c in PICKS["cases"] if c["id"] == "degree-masters-closest")
    oid = {t: f"o{i + 1}" for i, t in enumerate(case["options"])}
    for picked, outcome in ((["Masters"], "right"), (["MBA"], "wrong_write"), ([], "abstained")):
        monkeypatch.setattr(autofill_pick, "pick", lambda *_a, p=picked, **_k: {"c1": Picked(
            oids=[oid[t] for t in p], reason="closest" if p else "abstained")})
        assert ev.run_pick(case, ev.Run("fast"), None, PICKS["today"])["outcome"] == outcome


def test_a_jev_pass_never_scores_the_fast_models_answer(monkeypatch):
    """In a Jev pass the fallback raises: a Jev failure is counted as one."""
    from app.services import autofill_pick, jev, llm

    def down(*_a, **_k):
        raise llm.LLMProviderError("Jev could not be reached.")

    monkeypatch.setattr(jev, "decide", down)
    monkeypatch.setattr(autofill_pick, "_with_llm", lambda *_a, **_k: pytest.fail("the fast model answered"))
    case = next(c for c in PICKS["cases"] if c["id"] == "authorized-yes")
    run = ev.Run("jev")
    assert ev.run_pick(case, run, None, PICKS["today"])["outcome"] == "jev_failed"
    assert run.jev_errors == ["Jev could not be reached."]


NEVER_KINDS = ("sponsorship", "work-auth", "race", "veteran", "clearance", "salary-range", "attestation", "years-sql")


def test_the_low_stakes_never_list_is_in_both_case_files():
    """A mis-routed protected question must come back empty from /pick and
    give_up from /step (review 2026-09-27)."""
    picks = {c["id"]: c for c in PICKS["cases"]}
    steps = {c["id"]: c for c in STEPS["cases"]}
    for kind in NEVER_KINDS:
        pick, step = picks[f"low-stakes-never-{kind}"], steps[f"low-stakes-never-step-{kind}"]
        assert (pick["route"], pick["low_stakes"], pick["expected"]) == ("low_stakes", "on", None), kind
        assert (step["route"], step["low_stakes"], step["expected"]) == ("low_stakes", "on", ["give_up"]), kind
    assert picks["low-stakes-worked-here-never"]["expected"] is None
    assert picks["low-stakes-sms-consent"]["expected"] == "I consent"
    assert picks["low-stakes-contact-method"]["expected"] == picks["low-stakes-contact-method"]["options"]


def test_a_code_path_case_is_reported_apart(monkeypatch):
    from app.schemas.autofill_fill import Picked
    from app.services import autofill_pick

    monkeypatch.setattr(autofill_pick, "pick", lambda *_a, **_k: {"c1": Picked(oids=[], reason="abstained")})
    case = next(c for c in PICKS["cases"] if c.get("code_path"))
    result = ev.run_pick(case, ev.Run("fast"), None, PICKS["today"])
    assert result["code_path"] is True and ev.tally([result]) == {}


# ---------- the database is a read-only copy, guaranteed by the script


LIVE = ev.HERE.parents[1] / "data" / ev.DB_FILENAME


def test_without_db_the_script_exits_with_usage(capsys):
    with pytest.raises(SystemExit) as exit_:
        ev.main([])
    assert exit_.value.code == 2 and "--db" in capsys.readouterr().err


def test_the_script_refuses_a_live_database(tmp_path, monkeypatch, capsys):
    """This checkout's data/ file, the main checkout's, and one in DATA_DIR
    are refused before anything is imported or opened."""
    main_checkout = ev.refused_dirs()
    assert (ev.HERE.parents[1] / "data").resolve() in main_checkout
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    (live_dir / ev.DB_FILENAME).write_bytes(b"")
    monkeypatch.setenv("DATA_DIR", str(live_dir))
    monkeypatch.setattr(ev, "bind_read_only", lambda *_a: pytest.fail("the database was opened"))
    for db in (live_dir / ev.DB_FILENAME, *(d / ev.DB_FILENAME for d in main_checkout if (d / ev.DB_FILENAME).is_file())):
        with pytest.raises(SystemExit) as exit_:
            ev.main(["--db", str(db)])
        assert exit_.value.code == 2 and "live database" in capsys.readouterr().err, db
    assert ev.refusal(live_dir / ev.DB_FILENAME) is not None
    assert ev.refusal(tmp_path / "missing.sqlite3") is not None
    copy = tmp_path / "copy" / ev.DB_FILENAME
    copy.parent.mkdir()
    copy.write_bytes(b"")
    assert ev.refusal(copy) is None


def test_the_main_checkout_is_refused():
    """The main checkout's root, found independently of the script, has its
    data/ among the refused directories."""
    common = subprocess.run(["git", "-C", str(Path(__file__).parent), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    assert (Path(common).parent / "data").resolve() in ev.refused_dirs()


def _stand_in(tmp_path, monkeypatch):
    """A refused directory that is not the live one: DATA_DIR pointed at a
    temporary directory holding a file named like the database."""
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    (live_dir / ev.DB_FILENAME).write_bytes(b"")
    monkeypatch.setenv("DATA_DIR", str(live_dir))
    return live_dir


def test_a_refused_directory_spelled_in_another_case_is_refused(tmp_path, monkeypatch):
    """macOS ignores case: ".../LIVE/..." is the live directory. Identity, not spelling, decides."""
    _stand_in(tmp_path, monkeypatch)
    other = tmp_path / "LIVE" / ev.DB_FILENAME
    if not other.is_file():
        pytest.skip("this filesystem tells case apart: another spelling is another directory")
    assert "live database" in ev.refusal(other)


def test_the_main_checkouts_data_in_upper_case_is_refused():
    """The real live directory, spelled DATA: only stat is used, nothing is opened."""
    lives = [d for d in ev.refused_dirs() if d.name == "data" and (d / ev.DB_FILENAME).is_file()]
    if not lives:
        pytest.skip("no live database on this machine")
    upper = lives[0].parent / "DATA" / ev.DB_FILENAME
    if not upper.is_file():
        pytest.skip("this filesystem tells case apart")
    assert "live database" in ev.refusal(upper)


def test_a_hard_link_to_a_file_in_a_refused_directory_is_refused(tmp_path, monkeypatch):
    live_dir = _stand_in(tmp_path, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for name in (ev.DB_FILENAME, f"{ev.DB_FILENAME}-wal"):
        (live_dir / name).write_bytes(b"x")
        link = elsewhere / f"copy-of-{name}"
        os.link(live_dir / name, link)
        assert "same file" in ev.refusal(link), name


def test_a_read_only_binding_refuses_writes(tmp_path, monkeypatch):
    """bind_read_only on a real sqlite copy: reads work, a write raises, and
    the app's own engine cannot connect. Restores the suite's binding."""
    import sqlite3

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from app import db as app_db

    copy = tmp_path / ev.DB_FILENAME
    with sqlite3.connect(copy) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    conn.close()
    before = app_db.SessionLocal.kw["bind"]
    listeners = []
    monkeypatch.setattr("sqlalchemy.event.listens_for", _collecting(listeners))
    try:
        ev.bind_read_only(copy)
        with app_db.SessionLocal() as session:
            assert session.execute(text("SELECT x FROM t")).scalar() == 1
            with pytest.raises(OperationalError):
                session.execute(text("INSERT INTO t VALUES (2)"))
        refused = [fn for target, name, fn in listeners if target is app_db.engine and name == "do_connect"]
        assert refused
        with pytest.raises(RuntimeError):
            refused[0]()
    finally:
        app_db.SessionLocal.configure(bind=before)
        from sqlalchemy import event
        for target, name, fn in listeners:
            if event.contains(target, name, fn):
                event.remove(target, name, fn)


def _collecting(into):
    """event.listens_for that also records (target, name, fn), so the test can
    call and then remove what bind_read_only installed."""
    from sqlalchemy import event

    real = event.listens_for

    def listens_for(target, name, *args, **kwargs):
        decorate = real(target, name, *args, **kwargs)

        def wrap(fn):
            into.append((target, name, fn))
            return decorate(fn)
        return wrap
    return listens_for


# ---------- engines: `jev` is Jev alone, `routed` is production (Jev, then one fast second opinion)


def _jev_says_none(monkeypatch, way=("same", 0.95)):
    """Jev: none to a pick, give_up to a step, `way` to a polarity question."""
    from app.services import jev
    from tests.test_autofill_choose_jev import _answer

    def decide(questions, *_a, **_k):
        return {k: _answer(q["criteria"], *(way if "opposite" in q["criteria"] else
                                            ("none" if "none" in q["criteria"] else "give_up", 0.9)))
                for k, q in questions.items()}

    monkeypatch.setattr(jev, "decide", decide)


def test_a_jev_pass_is_jev_alone(monkeypatch):
    from app.services import autofill_pick

    _jev_says_none(monkeypatch)
    monkeypatch.setattr(autofill_pick, "fast_json", lambda *_a, **_k: pytest.fail("the fast model answered"))
    case = next(c for c in PICKS["cases"] if c["id"] == "authorized-yes")
    result = ev.run_pick(case, ev.Run("jev"), None, PICKS["today"])
    assert (result["outcome"], result["decided_by"]) == ("abstained", "jev")


def test_a_routed_pass_scores_the_second_opinion_and_says_who_decided(monkeypatch):
    from app.services import autofill_pick, autofill_step

    second = autofill_pick._second_opinion
    _jev_says_none(monkeypatch)
    monkeypatch.setattr(autofill_pick, "fast_json", lambda *_a, **_k: {
        "picks": {"c1": {"oids": ["o1"], "confidence": 0.95}}})
    case = next(c for c in PICKS["cases"] if c["id"] == "authorized-yes")
    result = ev.run_pick(case, ev.Run("routed"), None, PICKS["today"])
    assert (result["outcome"], result["decided_by"]) == ("right", "fast")
    assert autofill_pick._second_opinion is second   # restored

    monkeypatch.setattr(autofill_step, "fast_json", lambda *_a, **_k: {"move": "open", "confidence": 0.9})
    case = next(c for c in STEPS["cases"] if c["id"] == "closed-popup-open")
    result = ev.run_step(case, ev.Run("routed"), None, STEPS["today"])
    assert (result["outcome"], result["decided_by"]) == ("right", "fast")


def test_a_second_opinion_that_abstained_or_never_ran_is_not_scored_as_deciding(monkeypatch):
    """An abstain carrying a trace is not equal to `ABSTAIN`: `fast_decided` is read by content."""
    from app.services import autofill_pick

    _jev_says_none(monkeypatch)
    case = next(c for c in PICKS["cases"] if c["id"] == "authorized-yes")
    monkeypatch.setattr(autofill_pick, "fast_json", lambda *_a, **_k: {
        "picks": {"c1": {"oids": [], "confidence": 0.95}}})
    result = ev.run_pick(case, ev.Run("routed"), None, PICKS["today"])
    assert (result["outcome"], result["decided_by"]) == ("abstained", "jev")

    monkeypatch.setattr(autofill_pick, "_second_opinion", lambda *_a, **_k: None)   # it never ran
    result = ev.run_pick(case, ev.Run("routed"), None, PICKS["today"])
    assert (result["outcome"], result["decided_by"]) == ("abstained", "jev")


def test_a_jev_pass_never_runs_the_second_opinion(monkeypatch):
    from app.services import autofill_pick

    _jev_says_none(monkeypatch)
    monkeypatch.setattr(autofill_pick, "fast_json", lambda *_a, **_k: pytest.fail("the fast model answered"))
    case = next(c for c in PICKS["cases"] if c["id"] == "authorized-yes")
    assert ev.run_pick(case, ev.Run("jev"), None, PICKS["today"])["decided_by"] == "jev"


def test_a_routed_pass_still_counts_a_jev_failure(monkeypatch):
    from app.services import autofill_pick, jev, llm

    def down(*_a, **_k):
        raise llm.LLMProviderError("Jev could not be reached.")

    monkeypatch.setattr(jev, "decide", down)
    monkeypatch.setattr(autofill_pick, "fast_json", lambda *_a, **_k: pytest.fail("the fast model answered"))
    case = next(c for c in PICKS["cases"] if c["id"] == "authorized-yes")
    assert ev.run_pick(case, ev.Run("routed"), None, PICKS["today"])["outcome"] == "jev_failed"


# ---------- reversed and negated wordings (owner, 2026-09-27): tagged, run on their own

REVERSED = [c for c in PICKS["cases"] if c.get("tag") == "reversed"]


def test_the_reversed_wording_cases_are_labelled():
    by_id = {c["id"]: c for c in REVERSED}
    assert len(by_id) >= 5
    assert (by_id["reversed-authorized-without-sponsorship"]["fact"],
            by_id["reversed-authorized-without-sponsorship"]["expected"]) == ("No", "Yes")
    assert (by_id["reversed-sponsor-direct-control"]["fact"], by_id["reversed-sponsor-direct-control"]["expected"]) \
        == ("No", "No")
    assert (by_id["reversed-under-18"]["fact"], by_id["reversed-under-18"]["expected"]) == ("Yes", "No")
    assert by_id["reversed-no-non-compete"]["slot"] == "eligibility.non_compete"
    assert by_id["reversed-not-a-citizen"]["slot"] == "derived.us_citizen"
    assert all(ev.policy_of(c) == "exact" for c in REVERSED)
    assert {c["tag"] for c in STEPS["cases"] if c.get("tag")} == {"reversed"}


# A profile holding every slot the cases name, built the way production builds it.
EVERY_SLOT = {
    "work_auth": {"status": "h1b", "authorized_now": True, "sponsorship_now": False, "sponsorship_future": False},
    "eligibility": {"over_18": True, "non_compete": False, "previously_employed_here": False},
    "eeo": {"gender": "male", "race_ethnicity": ["Asian"], "hispanic_latino": "no", "veteran_status": "not_veteran",
            "disability_status": "no"},
    "preferences": {"how_heard": "Referral", "willing_to_relocate": True},
    "personal": {"country": "United States", "state": "Texas"},
    "education": [{"school": "State University", "degree": "Master's", "discipline": "Analytics"}],
    "languages": [{"language": "Norwegian"}],
}


@pytest.mark.parametrize("case", [c for c in PICKS["cases"] + STEPS["cases"] if c.get("slot")],
                         ids=lambda c: c["id"])
def test_a_case_fact_is_described_as_the_catalog_describes_it(case):
    """The pick reads the fact's description, and whether it is a Yes or a No:
    the eval must send what production sends, for every case's slot."""
    from app.services import autofill_catalog

    # The job's company in the history makes "previously employed here" a
    # derived fact and drops the standing one: both catalogs, one lookup.
    jobs = [{"employer": ev.HINT_COMPANY, "title": "Analyst", "current": True}]
    built = autofill_catalog.with_agreement(autofill_catalog.build(EVERY_SLOT, jobs, ["SQL"]), True) | (
        autofill_catalog.build(EVERY_SLOT, jobs, ["SQL"], company=ev.HINT_COMPANY))
    fact = ev.case_facts(case, PICKS["today"])[case["slot"]]
    assert fact.describe == built[case["slot"]].describe
    # The Yes/No mark as production's, wherever the case holds production's value.
    if built[case["slot"]].value == fact.value:
        assert fact.yes_no is built[case["slot"]].yes_no


def test_tagged_cases_can_be_run_on_their_own():
    picked = ev.select_cases(PICKS["cases"], only=None, tag="reversed")
    assert picked == REVERSED
    assert ev.select_cases(PICKS["cases"], only={"over-18"}, tag=None) == [
        c for c in PICKS["cases"] if c["id"] == "over-18"]
    assert ev.select_cases(PICKS["cases"], only=None, tag=None) == PICKS["cases"]


def test_the_derived_cases_expect_a_status_or_list_never_turned_into_yes_or_no():
    derived = {c["id"]: c for c in PICKS["cases"] if c.get("tag") == "derived"}
    assert len(derived) >= 3
    assert all(c["expected"] is None and c["options"] == ["Yes", "No"] for c in derived.values())
    assert {c["slot"] for c in derived.values()} >= {"work_auth.status", "eeo.race_ethnicity"}
    assert ev.select_cases(PICKS["cases"], only=None, tag="derived") == list(derived.values())


# ---------- the polarity split (owner, 2026-09-27): each result says how a Yes/No question was read


def _jev_picks(monkeypatch, option, way):
    """Jev: `way` to the polarity question, `option` (a text) to the pick."""
    from app.services import jev
    from tests.test_autofill_choose_jev import _answer

    def decide(questions, *_a, **_k):
        return {k: _answer(q["criteria"], *(way if "opposite" in q["criteria"] else (option, 0.95)))
                for k, q in questions.items()}

    monkeypatch.setattr(jev, "decide", decide)


def test_a_reversed_case_reports_its_polarity_and_the_engine_that_read_it(monkeypatch):
    case = next(c for c in PICKS["cases"] if c["id"] == "reversed-authorized-without-sponsorship")
    _jev_picks(monkeypatch, "Yes", ("opposite", 0.95))
    result = ev.run_pick(case, ev.Run("jev"), None, PICKS["today"])
    assert (result["outcome"], result["polarity"], result["polarity_by"]) == ("right", "opposite", "jev")


def test_jev_alone_leaves_an_unsure_polarity_unsure(monkeypatch):
    from app.services import autofill_polarity

    case = next(c for c in PICKS["cases"] if c["id"] == "reversed-authorized-without-sponsorship")
    _jev_picks(monkeypatch, "Yes", ("opposite", 0.5))
    monkeypatch.setattr(autofill_polarity, "fast_json", lambda *_a, **_k: pytest.fail("the fast model answered"))
    result = ev.run_pick(case, ev.Run("jev"), None, PICKS["today"])
    assert (result["outcome"], result["polarity"], result["polarity_by"]) == ("abstained", "unsure", None)
    # A confident neither is Jev's decision: no answer, and no second opinion even when routed.
    _jev_picks(monkeypatch, "Yes", ("neither", 0.99))
    result = ev.run_pick(case, ev.Run("routed"), None, PICKS["today"])
    assert (result["outcome"], result["polarity"], result["polarity_by"]) == ("abstained", "neither", "jev")


def test_a_routed_pass_lets_the_fast_model_read_the_polarity_jev_was_unsure_of(monkeypatch):
    from app.services import autofill_polarity

    case = next(c for c in PICKS["cases"] if c["id"] == "reversed-authorized-without-sponsorship")
    _jev_picks(monkeypatch, "Yes", ("opposite", 0.5))
    monkeypatch.setattr(autofill_polarity, "fast_json", lambda *_a, **_k: {
        "polarity": {"c1": {"key": "opposite", "confidence": 0.95}}})
    result = ev.run_pick(case, ev.Run("routed"), None, PICKS["today"])
    assert (result["outcome"], result["polarity"], result["polarity_by"]) == ("right", "opposite", "fast")
    assert autofill_polarity._second_opinion.__name__ == "_second_opinion"   # restored


def test_a_fact_that_is_not_a_yes_or_no_asks_no_polarity(monkeypatch):
    case = next(c for c in PICKS["cases"] if c["id"] == "derived-status-for-sponsorship")
    _jev_says_none(monkeypatch)
    result = ev.run_pick(case, ev.Run("jev"), None, PICKS["today"])
    assert (result["polarity"], result["polarity_by"]) == (None, None)


def test_the_new_reversed_cases_cover_same_opposite_and_a_wordy_value():
    by_id = {c["id"]: c for c in REVERSED}
    assert (by_id["reversed-require-sponsorship-same"]["fact"], by_id["reversed-require-sponsorship-same"]["expected"]) \
        == ("Yes", "Yes")
    assert by_id["reversed-able-without-visa"]["expected"] == "Yes"
    assert (by_id["reversed-disability-free"]["slot"], by_id["reversed-disability-free"]["expected"]) \
        == ("eeo.disability_status", None)


def test_the_neutral_cases_expect_a_pick_from_an_undirected_label():
    neutral = {c["id"]: c for c in PICKS["cases"] if c.get("tag") == "neutral"}
    assert {"neutral-veteran-status", "neutral-disability-status", "neutral-employment-with-company"} <= set(neutral)
    assert all(c["expected"] for c in neutral.values())
    assert neutral["neutral-employment-with-company"]["options"] == ["Current Associate", "Former Associate",
                                                                      "Not Applicable"]


def test_a_label_form_reversed_case_and_a_same_statement_case_are_labelled():
    by_id = {c["id"]: c for c in PICKS["cases"]}
    label = by_id["reversed-label-unrestricted-authorization"]
    assert (label["tag"], label["question"], label["fact"], label["expected"]) == (
        "reversed", "Unrestricted work authorization (no sponsorship required)", "Yes", "No")
    visa = by_id["neutral-visa-sponsorship"]
    assert (visa["tag"], visa["slot"], visa["fact"], visa["expected"]) == (
        "neutral", "work_auth.sponsorship_future", "No", "I will not require sponsorship")


NOW_OR_FUTURE_IDS = {"sponsor-future-yes", "sponsor-worded-options", "sponsor-not-sure",
                     "reversed-authorized-without-sponsorship", "reversed-sponsor-direct-control",
                     "sponsor-now-yes-later-no", "exact-sponsor-worded", "reversed-step-authorized-without-sponsorship"}


def test_now_or_in_the_future_cases_ask_the_derived_fact():
    """A question worded "now or in the future" maps to the fact derived from
    both answers; the case the old future-only rule got wrong is one of them."""
    by_id = {c["id"]: c for c in PICKS["cases"] + STEPS["cases"]}
    assert {i: by_id[i]["slot"] for i in NOW_OR_FUTURE_IDS} == dict.fromkeys(
        NOW_OR_FUTURE_IDS, "derived.sponsorship_now_or_future")
    assert (by_id["sponsor-now-yes-later-no"]["fact"], by_id["sponsor-now-yes-later-no"]["expected"]) == ("Yes", "Yes")


def test_now_or_in_the_future_agrees_with_the_future_rule_in_map_agreement():
    """The old rule's `sponsorship_future` rows now map to the derived fact:
    one fact, not a disagreement."""
    assert "derived.sponsorship_now_or_future" in ev.SAME_FACT["work_auth.sponsorship_future"]


# ---------- labelled /map cases (fill_map_cases.json): live Workday wrong writes, 2026-09-27

MAPS = ev.load_cases(ev.MAP_CASES)


@pytest.mark.parametrize("case", MAPS["cases"], ids=lambda c: c["id"])
def test_every_map_case_is_well_formed(case):
    ev.check_map_case(case, MAPS["facts"])
    ev.map_field(case)   # a field /map accepts


def test_the_map_cases_hold_the_live_wrong_writes():
    """"Phone Extension" got the phone number, "Address Line 2" got line 1,
    and "Country Phone Code" searched for the phone number."""
    by_id = {c["id"]: c for c in MAPS["cases"]}
    assert len(by_id) == len(MAPS["cases"])
    assert by_id["phone-extension"]["expected"] == ["none"]
    assert by_id["address-line-2"]["expected"] == ["none"]
    assert "personal.phone" not in by_id["country-phone-code"]["expected"]
    assert by_id["phone-number"]["expected"] == ["personal.phone"]
    assert by_id["address-line-1"]["expected"] == ["personal.address"]
    assert by_id["military-status"]["expected"] == ["eeo.veteran_status"]   # live CarMax, 2026-09-30
    # Service questions are not the protected-veteran self-identification.
    for case in ("military-served", "military-spouse", "military-guard-reserve"):
        assert by_id[case]["expected"] == ["none"], case
    for case in ("terms-and-conditions", "background-check-consent", "certify-true"):
        assert by_id[case]["expected"] == ["derived.agrees_to_terms"], case
    # Not an agreement: a willingness question, and optional opt-ins (the low-stakes setting's).
    for case in ("agree-to-relocate", "sms-opt-in", "talent-community"):
        assert "derived.agrees_to_terms" not in by_id[case]["expected"], case
    # Live iCIMS (2026-10-01): a phone type is no phone, and the current job has no end.
    assert by_id["phone-type"]["expected"] == ["none"]
    assert by_id["start-date-year"]["expected"] == ["experience.0.start"]
    assert by_id["current-job-end-year"]["expected"] == ["none"]
    # Criminal history is never an agreement: a Yes there would be a catastrophic wrong write.
    for case in ("felony-conviction", "pending-charges"):
        assert by_id[case]["expected"] == ["none"], case
    picks = {c["id"]: c for c in PICKS["cases"]}
    assert (picks["conviction-is-no-agreement"]["slot"], picks["conviction-is-no-agreement"]["expected"]) == (
        "derived.agrees_to_terms", None)
    facts = ev.map_case_facts(MAPS)
    assert "personal.address_2" not in facts   # line 2 has nowhere to go but none
    assert facts["personal.phone"].describe == describe_of("personal.phone")


def test_a_malformed_map_case_is_refused():
    with pytest.raises(ValueError, match="expected"):
        ev.check_map_case({"id": "x", "question": "Q", "shape": "text", "expected": ["personal.nope"]}, MAPS["facts"])
    with pytest.raises(ValueError, match="expected"):
        ev.check_map_case({"id": "x", "question": "Q", "shape": "text", "expected": []}, MAPS["facts"])


def test_a_map_case_is_scored_against_the_slot_it_routes(monkeypatch):
    """The scorer, with /map stubbed: no model is called."""
    from app.schemas.autofill_fill import Mapped
    from app.services import autofill_map

    cases = [c for c in MAPS["cases"] if c["id"] in ("phone-extension", "phone-number", "country-phone-code")]
    routed = {"phone-extension": Mapped(route="slot", slot="personal.phone", value="555-0100"),
              "phone-number": Mapped(route="none"),
              "country-phone-code": Mapped(route="slot", slot="personal.country", value="United States")}
    fid_of = {f"m{i}": c["id"] for i, c in enumerate(cases)}
    monkeypatch.setattr(autofill_map, "map_fields",
                        lambda fields, *_a, **_k: {f.fid: routed[fid_of[f.fid]] for f in fields})
    got = {r["id"]: r["outcome"] for r in ev.run_map_cases(cases, ev.map_case_facts(MAPS), ev.Run("fast"), None)}
    assert got == {"phone-extension": "wrong_write", "phone-number": "missed", "country-phone-code": "right"}
