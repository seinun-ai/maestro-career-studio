"""The fill-decision evaluation's labelled cases are well formed (offline: no
model is called). scripts/eval_fill_decisions.py runs them against the models."""

import os
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from app.services.autofill_slots import policy_for
from scripts import eval_fill_decisions as ev

PICKS = ev.load_cases(ev.PICK_CASES)
STEPS = ev.load_cases(ev.STEP_CASES)


def test_the_case_files_hold_the_plans_counts():
    assert 38 <= len(PICKS["cases"]) <= 70
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
