"""Meaning evaluation of the fill engine's decisions (fill-engine revision Task 12).

Four reports, each printed as Markdown (and written as JSON with --out):

- MAPPING AGREEMENT (diagnostic, not ground truth): the distinct
  (label, kind, rule_id) rows of `autofill_field_observations` whose rule id
  names ONE slot (`RULE_TO_SLOT`, built from the ids in
  extension/content/autofill.js's RULES and eeo.js), sent through
  `autofill_map.map_fields` over the real profile's fact catalog. Labels and
  fact DESCRIPTIONS only reach the model, as /map in production. A row whose
  rule slot the profile does not hold is counted apart: no answer could agree.
- LABELLED PICKS (`fill_pick_cases.json`): each case through `autofill_pick.pick`,
  scored per policy as right (matched / closest / assumed), abstained, or a
  WRONG WRITE (an option that does not state the fact).
- LABELLED STEPS (`fill_step_cases.json`): each case through `autofill_step.step`,
  scored as right, WRONG CLICK (an option that does not state the fact),
  wrong-but-harmless move, or give_up.
- LABELLED MAPS (`fill_map_cases.json`, with `--part map`): each label through
  `autofill_map.map_fields` over the file's synthetic facts, scored as right,
  missed (none where a fact was expected) or a WRONG WRITE (any slot not
  expected: "Phone Extension" given the phone number).

Picks and steps run once per engine (Jev, then the fast model; `--engines`),
reported separately: the fast model's confidence is not calibrated by sharing
Jev's floors. In a Jev pass Jev's own fallback to the fast model is turned
off, so a Jev failure is counted as one, never scored as Jev's answer, and
the fast second opinion on Jev's unsure answers is off too: `jev` is Jev
alone. `routed` is what production runs on the Jev engine: Jev, then ONE fast
second opinion where Jev was unsure (its failure fallback still refused);
each result says which engine decided (`decided_by`). A Yes/No fact's
question polarity (autofill_polarity: same / opposite, decided before the
literal pick) is reported per result (`polarity`, and `polarity_by`: the
engine that decided it); `jev` asks Jev alone for it too. The reasoning route is
the fast model's on every engine (autofill_reasoned).

Only labels, options and each case's own fact go to the models; the cases are
synthetic. The database is a COPY of the live one, named by the required
`--db`, and the script guarantees it only reads it: a path inside any
checkout's `data/` or the configured DATA_DIR is refused; the session is bound
to a read-only connection (`mode=ro`, `query_only`) and a probe write must
fail before anything runs; the app's own engine is made unable to connect;
settings and the profile are PEEKED (nothing is lazily seeded); SETTINGS_DIR
and LOGS_DIR default to fresh temporary directories. Run from backend/ (do
not set DATA_DIR to the copy's directory, or the script refuses it):

    cp <main-checkout>/data/maestro_cs.sqlite3* <scratch>/    # stack stopped, or a backups/ snapshot
    set -a; source <main-checkout>/.env; set +a
    BASE_RESUMES_DIR=<main-checkout>/base_resumes \\
        /opt/anaconda3/bin/python3 -m scripts.eval_fill_decisions --db <scratch>/maestro_cs.sqlite3 \\
        --out <scratch>/eval.json

The model keys are the copy's settings (and .env's). `--part map|pick|step`
runs one report (map: the agreement and the labelled maps); `--base <slug>` picks the resume the mapping catalog reads
(default: the first active one); `--only id,id` runs named cases, `--tag reversed` the tagged ones. Offline
checks: tests/test_eval_fill_cases.py.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PICK_CASES = HERE / "fill_pick_cases.json"
STEP_CASES = HERE / "fill_step_cases.json"
MAP_CASES = HERE / "fill_map_cases.json"
EXTENSION = HERE.parents[1] / "extension"
RULE_FILES = (EXTENSION / "content" / "autofill.js", EXTENSION / "content" / "eeo.js")

# A rule id -> the ONE slot it fills. Rules that fill no single slot are left
# out: phone-ext-fax (skips), custom (a saved answer each), consent-forms (a
# tick), emp-day / emp-year-in-order / emp-month-in-order (start OR end, by
# DOM order). An entry slot is written with index 0 and compared without it.
RULE_TO_SLOT: dict[str, str] = {
    "first-name": "personal.first_name", "last-name": "personal.last_name", "full-name": "derived.full_name",
    "email": "personal.email", "phone": "personal.phone", "phone-country-code": "personal.country",
    "address-2": "personal.address_2", "address": "personal.address",
    "sponsorship-now": "work_auth.sponsorship_now", "sponsorship-future": "work_auth.sponsorship_future",
    "work-auth": "work_auth.authorized_now",
    "city": "personal.city", "state": "personal.state", "postal-code": "personal.postal_code",
    "country": "personal.country", "linkedin": "personal.linkedin", "github": "personal.github",
    "website": "personal.website",
    "edu-school": "education.0.school", "edu-degree": "education.0.degree",
    "edu-discipline": "education.0.discipline", "edu-gpa": "education.0.gpa",
    "edu-end-year": "education.0.end_year", "edu-start-year": "education.0.start_year",
    "emp-employer": "experience.0.employer", "emp-title": "experience.0.title",
    "emp-location": "experience.0.location", "emp-description": "experience.0.description",
    "emp-start-month": "experience.0.start", "emp-start-year": "experience.0.start",
    "emp-start-date": "experience.0.start", "emp-end-month": "experience.0.end",
    "emp-end-year": "experience.0.end", "emp-end-date": "experience.0.end",
    "emp-current": "experience.0.current", "skills": "skills",
    "over-18": "eligibility.over_18", "previously-employed-here": "eligibility.previously_employed_here",
    "non-compete": "eligibility.non_compete",
    "salary": "preferences.desired_salary", "notice-period": "preferences.notice_period",
    "earliest-start-date": "preferences.earliest_start_date",
    "willing-to-relocate": "preferences.willing_to_relocate", "how-heard": "preferences.how_heard",
    "gender": "eeo.gender", "race-ethnicity": "eeo.race_ethnicity", "hispanic-latino": "eeo.hispanic_latino",
    "veteran": "eeo.veteran_status", "disability": "eeo.disability_status",
}
# The same fact under its derived name: an answer naming either agrees.
SAME_FACT = {"preferences.earliest_start_date": {"derived.earliest_start_date"},
             "eligibility.previously_employed_here": {"derived.previously_employed_here"},
             # The old rule answered "now or in the future" from the future answer.
             "work_auth.sponsorship_future": {"derived.sponsorship_now_or_future"}}
# Telemetry's control kinds as the fill loop's shapes (a combobox is a search
# box or a popup; /map reads the shape only to tell prose from a choice).
KIND_TO_SHAPE = {"text": "text", "textarea": "text", "select": "select", "combobox": "search",
                 "radio": "group", "checkbox": "group"}
MAP_BATCH = 10
GIVE_UP_DESCRIBE = "Stop: no move will select the goal's answer to the question"
JOB_KEYS = ("employer", "title", "description", "start", "end", "current")
SCHOOL_KEYS = ("school", "degree", "discipline", "start_year", "end_year")
POLICIES = ("exact", "flag", "any", "low_stakes", "reasoned")
DB_FILENAME = "maestro_cs.sqlite3"
# The job every case is asked for; a case history listing this company makes
# "previously employed here" a derived fact (autofill_catalog._worked_here).
HINT_TITLE, HINT_COMPANY = "Data Analyst", "Acme Corp"


# ---------------------------------------------------------------- the database: a read-only copy


def refused_dirs() -> list[Path]:
    """Where a live database lives: every checkout's `data/` (this one and the
    main checkout, found through git's common dir) and the configured DATA_DIR
    (the running app's, /app/data by default)."""
    roots = {HERE.parents[1]}
    try:
        common = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        roots.add(Path(common).parent)
    except (OSError, subprocess.SubprocessError):
        pass
    dirs = [root / "data" for root in roots] + [Path(os.environ.get("DATA_DIR") or "/app/data")]
    return [d.resolve() for d in dirs]


def _identity(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_dev, st.st_ino


def refusal(db: Path) -> str | None:
    """Why `db` may not be evaluated against, or None.

    By file IDENTITY, never by spelling: macOS's filesystem ignores case, so
    ".../DATA/..." names the live directory while no string compare says so,
    and a hard link elsewhere IS the live file. Every directory above `db`
    is compared (device, inode) with each refused directory, and `db` itself
    with every file in them. Only stat is used: nothing is opened."""
    path = db.resolve()
    if not path.is_file():
        return f"{db} is not a file"
    refused = {}
    for d in refused_dirs():
        if d.is_dir():
            refused[_identity(d)] = d
    for parent in path.parents:
        if (d := refused.get(_identity(parent))) is not None:
            return f"{db} is inside {d}, where a live database lives: copy it elsewhere first"
    for d in refused.values():
        for live in d.iterdir():
            if live.is_file() and path.samefile(live):
                return f"{db} is the same file as {live}, a live database: copy it, never link it"
    return None


def bind_read_only(db: Path) -> None:
    """Every session the app's code opens reads `db` through a read-only
    connection; the app's own engine cannot connect at all. Raises unless a
    probe write fails."""
    import sqlite3
    from urllib.parse import quote

    from sqlalchemy import create_engine, event, text
    from sqlalchemy.exc import OperationalError

    from app import db as app_db

    uri = f"file:{quote(str(db.resolve()))}?mode=ro"
    read_only = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False))

    @event.listens_for(read_only, "connect")
    def _query_only(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA query_only=ON")

    # insert=True: before make_engine's own do_connect listener, which would
    # pre-create (and chmod) the file its URL names.
    @event.listens_for(app_db.engine, "do_connect", insert=True)
    def _never(*_args):
        raise RuntimeError("the evaluation reads the database only through its read-only session")

    app_db.SessionLocal.configure(bind=read_only)
    with app_db.SessionLocal() as session:
        try:
            session.execute(text("CREATE TABLE eval_write_probe (x INTEGER)"))
            session.commit()
        except OperationalError:
            session.rollback()
        else:
            raise RuntimeError(f"{db} opened writable: stopping before any model call")


# ---------------------------------------------------------------- cases


def rule_ids() -> set[str]:
    """Every rule id the extension's rule tables declare."""
    ids: set[str] = set()
    for path in RULE_FILES:
        ids |= set(re.findall(r'\{\s*id:\s*"([a-z0-9-]+)"', path.read_text(encoding="utf-8")))
    return ids


def load_cases(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_cases(cases: list[dict], *, only: set[str] | None, tag: str | None) -> list[dict]:
    """The cases a run asks: named by id (`--only`), or carrying a tag (`--tag`), else all."""
    return [c for c in cases if (only is None or c["id"] in only) and (tag is None or c.get("tag") == tag)]


def expected_of(case: dict) -> list[str]:
    """The acceptable answers: [] when abstaining (or give_up) is the only right answer."""
    got = case.get("expected")
    return [] if got is None else [got] if isinstance(got, str) else list(got)


def policy_of(case: dict) -> str:
    """A case's row in the report: its slot's policy, or its route."""
    from app.services.autofill_slots import policy_for

    route = case.get("route", "slot")
    return route if route != "slot" else policy_for(case["slot"])


def check_history(cid: str, hist: object) -> None:
    if not (isinstance(hist, dict) and isinstance(hist.get("jobs"), list) and isinstance(hist.get("schools"), list)):
        raise ValueError(f"{cid}: a history is jobs and schools")
    for job in hist["jobs"]:
        if set(job) - set(JOB_KEYS) or not job.get("employer"):
            raise ValueError(f"{cid}: a job holds only {JOB_KEYS}, an employer at least")
    for school in hist["schools"]:
        if set(school) - set(SCHOOL_KEYS) or not school.get("school"):
            raise ValueError(f"{cid}: a school holds only {SCHOOL_KEYS}, a school at least")


def check_pick_case(case: dict) -> None:
    """Raise ValueError when a pick case is malformed."""
    cid = case.get("id")
    route = case.get("route", "slot")
    if route not in ("slot", "low_stakes", "reasoned"):
        raise ValueError(f"{cid}: unknown route {route}")
    options = case.get("options")
    if not (isinstance(options, list) and options and all(isinstance(o, str) and o for o in options)):
        raise ValueError(f"{cid}: options must be a non-empty list of texts")
    if len(set(options)) != len(options):
        raise ValueError(f"{cid}: duplicate option texts")
    missing = [e for e in expected_of(case) if e not in options]
    if missing:
        raise ValueError(f"{cid}: expected {missing} is not an option")
    if route == "slot":
        if not case.get("slot") or case.get("fact") in (None, "", []):
            raise ValueError(f"{cid}: a slot case needs a slot and a fact")
        if isinstance(case["fact"], list) and case.get("item") not in case["fact"]:
            raise ValueError(f"{cid}: a set fact is picked one `item` at a time")
    else:
        if case.get("slot") or case.get("fact") is not None:
            raise ValueError(f"{cid}: a {route} case carries no slot or fact")
    if route == "low_stakes" and case.get("low_stakes") not in ("on", "off"):
        raise ValueError(f"{cid}: a low_stakes case names the setting, on or off")
    if route == "reasoned" and "history" not in case:
        raise ValueError(f"{cid}: a reasoned case carries a history of jobs and schools")
    if "history" in case:
        check_history(cid, case["history"])
    if case.get("code_path") and route != "low_stakes":
        raise ValueError(f"{cid}: only a low_stakes setting check is a code-path case")


def check_step_case(case: dict) -> None:
    """Raise ValueError when a step case is malformed (the request must be one /step accepts)."""
    cid = case.get("id")
    route = case.get("route", "slot")
    try:
        step_request(case)
    except Exception as exc:  # pydantic's error names the bad part
        raise ValueError(f"{cid}: not a valid /step request: {exc}") from exc
    mids = {c["mid"] for c in case["candidates"]}
    if "give_up" in mids:
        raise ValueError(f"{cid}: give_up is added by the script, as the page adds it")
    expected = expected_of(case)
    if not expected or any(m != "give_up" and m not in mids for m in expected):
        raise ValueError(f"{cid}: expected moves must be offered (or give_up)")
    if any(m not in mids for m in case.get("harmless", [])):
        raise ValueError(f"{cid}: a harmless move must be offered")
    if route == "slot" and (not case.get("slot") or case.get("fact") in (None, "", [])):
        raise ValueError(f"{cid}: a slot case needs a slot and a fact")
    if route == "low_stakes" and (case.get("slot") or case.get("fact") is not None or
                                  case.get("low_stakes") not in ("on", "off")):
        raise ValueError(f"{cid}: a low_stakes case names the setting and carries no slot or fact")


def check_map_case(case: dict, facts: dict[str, str]) -> None:
    """Raise ValueError when a map case is malformed: `expected` lists slots
    the file's facts hold, or "none"."""
    cid = case.get("id")
    expected = case.get("expected")
    if not (isinstance(expected, list) and expected and all(e == "none" or e in facts for e in expected)):
        raise ValueError(f"{cid}: expected is a non-empty list of the file's fact slots or \"none\"")
    if not case.get("question"):
        raise ValueError(f"{cid}: a map case needs a question")


def map_field(case: dict, fid: str = "m0"):
    from app.schemas.autofill_fill import MapField

    return MapField(fid=fid, question=case["question"], shape=case["shape"], options=case.get("options", []))


def map_case_facts(cases: dict) -> dict:
    """The map cases' facts, built by the catalog's own `make_fact` (production's descriptions)."""
    from app.services.autofill_catalog import make_fact

    return {slot: make_fact(slot, value) for slot, value in cases["facts"].items()}


def step_request(case: dict):
    from app.schemas.autofill_fill import StepCandidate, StepRequest

    candidates = [StepCandidate(**c) for c in case["candidates"]]
    candidates.append(StepCandidate(mid="give_up", describe=GIVE_UP_DESCRIBE))
    return StepRequest(fid="s1", question=case["question"], route=case.get("route", "slot"),
                       slot=case.get("slot"), item=case.get("item"), history=case.get("history", []),
                       candidates=candidates, complete=bool(case.get("complete", False)))


def pick_field(case: dict):
    from app.schemas.autofill_fill import PickField, PickOption

    route = case.get("route", "slot")
    return PickField(fid="c1", question=case["question"], route=route,
                     slot=case.get("slot") if route == "slot" else None, item=case.get("item"),
                     options=[PickOption(oid=f"o{i + 1}", text=t) for i, t in enumerate(case["options"])],
                     complete=bool(case.get("complete", True)))


def case_facts(case: dict, today: str) -> dict:
    """The facts one case holds: its slot's fact, its history, and today; and
    "previously employed here" when the history lists HINT_COMPANY."""
    from app.services.autofill_catalog import _worked_here, make_fact
    from app.services.autofill_slots import _as_text

    # Built by the catalog's own `make_fact`: the description and the Yes/No
    # mark production sends.
    facts = {"derived.today": make_fact("derived.today", today)}

    def add(slot: str, value: Any) -> None:
        value = tuple(value) if isinstance(value, list) else value if isinstance(value, str) else _as_text(value)
        if value not in (None, "", ()):
            facts[slot] = make_fact(slot, value)

    if case.get("slot"):
        add(case["slot"], case["fact"])
    # A pick case's `history` is the applicant's jobs and schools; a step
    # case's is the moves tried so far (a list), which holds no fact.
    hist = case.get("history") if isinstance(case.get("history"), dict) else {}
    for i, job in enumerate(hist.get("jobs", [])):
        for key in JOB_KEYS:
            add(f"experience.{i}.{key}", job.get(key, False if key == "current" else None))
    for i, school in enumerate(hist.get("schools", [])):
        for key in SCHOOL_KEYS:
            add(f"education.{i}.{key}", school.get(key))
    _worked_here(facts, HINT_COMPANY)
    return facts


# ---------------------------------------------------------------- running


class JevFellBack(Exception):
    """A Jev pass reached the fast-model fallback: Jev failed this call."""


@dataclass
class Run:
    engine: str
    jev_errors: list[str] = field(default_factory=list)
    # (option or move id, probability or confidence) of each decision, as
    # the floors saw it: the report shows the number behind an abstain.
    trace: list[tuple[str | None, float]] = field(default_factory=list)
    # `routed` only: the fields the fast second opinion was asked about, and
    # whether it decided the last case (it answered where Jev did not).
    second_asked: set[str] = field(default_factory=set)
    fast_decided: bool = False
    # fid -> autofill_polarity.Polarity, for a Yes/No fact's last case.
    polarity: dict = field(default_factory=dict)

    def polarity_of(self, fid: str) -> dict:
        """same / opposite / unsure (asked, undecided) / None (no Yes/No fact), and its engine."""
        p = self.polarity.get(fid)
        return {"polarity": (p.way or "unsure") if p else None, "polarity_by": p.engine if p else None}

    def decided_by(self) -> str:
        return "fast" if self.fast_decided else ("jev" if self.engine == "routed" else self.engine)


@contextmanager
def engine_of(run: Run, low_stakes: bool = False):
    """Force the engine and the low-stakes setting; in a Jev pass, record
    Jev's failures and refuse the fast-model fallback."""
    from app.services import autofill_map, autofill_pick, autofill_polarity, autofill_step, jev, llm, model_settings

    saved = {(model_settings, "get_autofill_engine"): model_settings.get_autofill_engine,
             (model_settings, "get_autofill_low_stakes"): model_settings.get_autofill_low_stakes,
             (jev, "decide"): jev.decide,
             (autofill_pick, "_with_llm"): autofill_pick._with_llm,
             (autofill_map, "_with_llm"): autofill_map._with_llm,
             (autofill_step, "fast_json"): autofill_step.fast_json,
             (autofill_pick, "verdict"): autofill_pick.verdict,
             (autofill_step, "_decide"): autofill_step._decide,
             (autofill_map, "_second_opinion"): autofill_map._second_opinion,
             (autofill_pick, "_second_opinion"): autofill_pick._second_opinion,
             (autofill_step, "_second_opinion"): autofill_step._second_opinion,
             (autofill_polarity, "_with_llm"): autofill_polarity._with_llm,
             (autofill_polarity, "_second_opinion"): autofill_polarity._second_opinion,
             (autofill_polarity, "decide"): autofill_polarity.decide}
    fast_calls = {key: saved[key] for key in ((autofill_pick, "_with_llm"), (autofill_map, "_with_llm"),
                                              (autofill_step, "fast_json"), (autofill_polarity, "_with_llm"))}
    polarity_decide = autofill_polarity.decide

    def seen_polarity(*args, **kwargs):
        got = polarity_decide(*args, **kwargs)
        run.polarity.update(got)
        return got
    decide, verdict, step_decide = jev.decide, autofill_pick.verdict, autofill_step._decide

    def seen_pick(fld, oid, p, *args, **kwargs):
        run.trace.append((oid, p))
        return verdict(fld, oid, p, *args, **kwargs)

    def seen_step(req, mid, p, *args, **kwargs):
        run.trace.append((mid, p))
        return step_decide(req, mid, p, *args, **kwargs)

    def recorded(*args, **kwargs):
        try:
            return decide(*args, **kwargs)
        except llm.LLMProviderError as exc:
            run.jev_errors.append(str(exc))  # the message only: never the detail or a key
            raise

    def refuse(*_args, **_kwargs):
        raise JevFellBack()

    def second_opinion(module):
        """The production second opinion, allowed the fast model the failure
        fallback is refused."""
        ask = saved[(module, "_second_opinion")]

        def asked(*args, **kwargs):
            for (owner, name), fn in fast_calls.items():
                setattr(owner, name, fn)
            try:
                got = ask(*args, **kwargs)
            finally:
                for owner, name in fast_calls:
                    setattr(owner, name, refuse)
            if module is autofill_map:
                run.second_asked.update(f.fid for f in args[0])
            elif module is autofill_polarity:
                pass   # recorded by `seen_polarity`, with its engine
            else:
                run.fast_decided = (any(p != autofill_pick.ABSTAIN for p in got.values()) if isinstance(got, dict)
                                    else got != autofill_step.ABSTAIN)
            return got
        return asked

    engine = "jev" if run.engine == "routed" else run.engine
    model_settings.get_autofill_engine = lambda session=None: engine
    model_settings.get_autofill_low_stakes = lambda session=None: low_stakes
    autofill_pick.verdict, autofill_step._decide = seen_pick, seen_step
    autofill_polarity.decide = seen_polarity
    autofill_polarity.forget()   # each case, on each engine, asks its own polarity
    run.fast_decided = False
    run.polarity.clear()
    if engine == "jev":
        jev.decide = recorded
        autofill_pick._with_llm = refuse
        autofill_map._with_llm = refuse
        autofill_step.fast_json = refuse
        autofill_polarity._with_llm = refuse
    if run.engine == "jev":   # Jev alone: its unsure answers stand
        autofill_map._second_opinion = lambda *_a, **_k: None   # never ran
        autofill_pick._second_opinion = lambda *_a, **_k: {}
        autofill_step._second_opinion = lambda *_a, **_k: autofill_step.ABSTAIN
        autofill_polarity._second_opinion = lambda *_a, **_k: {}
    elif run.engine == "routed":
        for module in (autofill_map, autofill_pick, autofill_step, autofill_polarity):
            module._second_opinion = second_opinion(module)
    try:
        yield
    finally:
        for (module, name), value in saved.items():
            setattr(module, name, value)


def job_hint(case: dict):
    """The job every /pick and /step case is asked for, with the case's page source."""
    from app.services import autofill_pick

    return autofill_pick.JobHint(title=HINT_TITLE, company=HINT_COMPANY, source=case.get("source"))


def failure(case: dict, exc: Exception) -> dict:
    """A case whose engine call failed: Jev fell back, or the model provider errored."""
    failed = "jev_failed" if isinstance(exc, JevFellBack) else "model_failed"
    return {"id": case["id"], "policy": policy_of(case), "outcome": failed, "got": None, "reason": str(exc)}


def run_pick(case: dict, run: Run, session, today: str) -> dict:
    from app.services import autofill_pick, llm

    fld = pick_field(case)
    hint = job_hint(case)
    run.trace.clear()
    try:
        with engine_of(run, low_stakes=case.get("low_stakes") == "on"):
            picked = autofill_pick.pick([fld], case_facts(case, today), session, hint)["c1"]
    except (JevFellBack, llm.LLMProviderError) as exc:
        return failure(case, exc)
    got = next((o.text for o in fld.options if picked.oids and o.oid == picked.oids[0]), None)
    expected = expected_of(case)
    if got is None:
        outcome = "abstained_ok" if not expected else "abstained"
    else:
        outcome = "right" if got in expected else "wrong_write"
    said = {o.oid: o.text for o in fld.options}.get(run.trace[-1][0]) if run.trace else None
    return {"id": case["id"], "policy": policy_of(case), "code_path": bool(case.get("code_path")),
            "outcome": outcome, "got": got, "decided_by": run.decided_by(), **run.polarity_of("c1"),
            "reason": picked.reason, "said": said, "p": run.trace[-1][1] if run.trace else None,
            "expected": expected, "question": case["question"], "options": case["options"],
            "fact": case.get("item") or case.get("fact")}


def run_step(case: dict, run: Run, session, today: str) -> dict:
    from app.services import autofill_step, llm

    req = step_request(case)
    hint = job_hint(case)
    run.trace.clear()
    try:
        with engine_of(run, low_stakes=case.get("low_stakes") == "on"):
            resp = autofill_step.step(req, case_facts(case, today), session, hint)
    except (JevFellBack, llm.LLMProviderError) as exc:
        return failure(case, exc)
    mid = resp.mid or "give_up"
    expected = expected_of(case)
    describe = {c["mid"]: c["describe"] for c in case["candidates"]}
    if mid in expected:
        outcome = "give_up_ok" if mid == "give_up" else "right"
    elif mid == "give_up":
        outcome = "give_up"
    elif describe[mid].startswith("Click the option") and mid not in case.get("harmless", []):
        outcome = "wrong_click"
    else:
        outcome = "harmless"
    return {"id": case["id"], "policy": policy_of(case), "outcome": outcome, "got": mid, "decided_by": run.decided_by(),
            **run.polarity_of("s1"),
            "got_describe": describe.get(mid, GIVE_UP_DESCRIBE), "reason": resp.reason, "expected": expected,
            "said": run.trace[-1][0] if run.trace else None, "p": run.trace[-1][1] if run.trace else None,
            "question": case["question"], "fact": case.get("item") or case.get("fact")}


def observed_rows(session) -> list[dict]:
    """The distinct (label, kind, rule_id) telemetry rows whose rule names one slot."""
    from sqlalchemy import select

    from app.models.autofill_field_observation import AutofillFieldObservation as Obs

    rows: dict[tuple, dict] = {}
    for label, kind, rule_id, options in session.execute(
            select(Obs.label, Obs.kind, Obs.rule_id, Obs.options).where(Obs.rule_id.in_(RULE_TO_SLOT))):
        key = (label, kind, rule_id)
        if key not in rows:
            opts = options if isinstance(options, list) else json.loads(options) if isinstance(options, str) else None
            rows[key] = {"label": label, "kind": kind, "rule_id": rule_id,
                         "options": [str(o) for o in (opts or [])][:30]}
    return list(rows.values())


def unindexed(slot: str | None) -> str | None:
    return re.sub(r"\.\d+\.", ".", slot) if slot else slot


def catalog(session, base: str | None) -> dict:
    """The real fact catalog, as /map builds it (consent-gated profile + a resume)."""
    from app.services import autofill_catalog, autofill_profile, eeo_consent
    from app.services.autofill_context import employment_blocks, resume_skills
    from app.services.base_resume_data import active_base_resume_slugs, load_base_resume

    slug = base or next(iter(active_base_resume_slugs(session)), None)
    resume = load_base_resume(slug, session) if slug else None
    # disclosable_profile, PEEKED: get_profile / get_consent lazily seed a row and a file mirror.
    profile = eeo_consent.withhold_unconsented(autofill_profile.peek_profile(session),
                                               eeo_consent.peek_consent(session).model_dump(mode="json"))
    return autofill_catalog.build(profile,
                                  employment_blocks(resume) if resume else [],
                                  resume_skills(resume) if resume else [])


def run_map(session, run: Run, base: str | None) -> dict:
    from app.schemas.autofill_fill import MapField
    from app.services import autofill_map, eeo_consent

    facts = catalog(session, base)
    held = {unindexed(s) for s in facts}
    rows = observed_rows(session)
    absent = Counter(RULE_TO_SLOT[r["rule_id"]] for r in rows if unindexed(RULE_TO_SLOT[r["rule_id"]]) not in held)
    rows = [r for r in rows if unindexed(RULE_TO_SLOT[r["rule_id"]]) in held]
    raw: dict[str, tuple[str, float]] = {}
    with_jev, answerable = autofill_map._with_jev, autofill_map._answerable
    consented = eeo_consent.peek_consent(session).enabled

    def keep(fields, criteria, session_):
        got = with_jev(fields, criteria, session_)
        raw.update(got)
        return got

    results = []
    for start in range(0, len(rows), MAP_BATCH):
        batch = rows[start:start + MAP_BATCH]
        fields = [MapField(fid=f"m{start + i}", question=r["label"][:300], shape=KIND_TO_SHAPE.get(r["kind"], "text"),
                           options=r["options"] if KIND_TO_SHAPE.get(r["kind"]) != "text" else [])
                  for i, r in enumerate(batch)]
        mapped, failed = None, False
        for _attempt in range(2):   # one retry of a batch Jev failed
            # The reasoning pass is not a mapping: it is not asked. Jev's raw
            # answers (and their p) are kept only on a Jev pass.
            if run.engine in ("jev", "routed"):
                autofill_map._with_jev = keep
            autofill_map._answerable = lambda *_a, **_k: set()
            try:
                with engine_of(run):
                    mapped = autofill_map.map_fields(fields, facts, session, eeo_consented=consented, low_stakes=False)
                break
            except JevFellBack:
                failed = True
            finally:
                autofill_map._with_jev, autofill_map._answerable = with_jev, answerable
        for f, r in zip(fields, batch):
            want = unindexed(RULE_TO_SLOT[r["rule_id"]])
            if mapped is None:
                results.append({**r, "rule_slot": want, "got": None, "p": None, "agree": None, "retried": failed})
                continue
            m = mapped[f.fid]
            key, p = raw.get(f.fid, (None, None))
            got = unindexed(m.slot) if m.route == "slot" else f"({m.route}{': ' + key if key and m.route == 'none' else ''})"
            agree = m.route == "slot" and (got == want or got in SAME_FACT.get(want, set()))
            # An asked field is one Jev routed none: routed now, the fast model decided it.
            decided_by = "fast" if f.fid in run.second_asked and m.route != "none" else (
                "jev" if run.engine == "routed" else run.engine)
            results.append({**r, "rule_slot": want, "got": got, "p": p, "agree": agree, "retried": failed,
                            "decided_by": decided_by})
    scored = [r for r in results if r["agree"] is not None]
    return {"engine": run.engine, "rows": results, "absent_from_profile": dict(absent),
            "agreement": (sum(r["agree"] for r in scored) / len(scored)) if scored else None,
            "scored": len(scored), "failed_batches_rows": len(results) - len(scored)}


def run_map_cases(cases: list[dict], facts: dict, run: Run, session) -> list[dict]:
    """Each labelled label through /map, a batch at a time; no optional pass is asked."""
    from app.services import autofill_map, llm

    answerable, results = autofill_map._answerable, []
    for start in range(0, len(cases), MAP_BATCH):
        batch = cases[start:start + MAP_BATCH]
        fields = [map_field(c, f"m{start + i}") for i, c in enumerate(batch)]
        autofill_map._answerable = lambda *_a, **_k: set()
        try:
            with engine_of(run):
                mapped = autofill_map.map_fields(fields, facts, session, eeo_consented=False, low_stakes=False)
        except (JevFellBack, llm.LLMProviderError) as exc:
            failed = "jev_failed" if isinstance(exc, JevFellBack) else "model_failed"
            results += [{"id": c["id"], "outcome": failed, "got": None, "expected": c["expected"]} for c in batch]
            continue
        finally:
            autofill_map._answerable = answerable
        for f, c in zip(fields, batch):
            m = mapped[f.fid]
            got = m.slot if m.route == "slot" else "none" if m.route in ("none", "blocked") else m.route
            outcome = "right" if got in c["expected"] else "missed" if got == "none" else "wrong_write"
            results.append({"id": c["id"], "question": c["question"], "outcome": outcome, "got": got,
                            "expected": c["expected"]})
    return results


# ---------------------------------------------------------------- reports


def tally(results: list[dict]) -> dict[str, Counter]:
    by: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        if r.get("code_path"):
            continue   # a setting check, not a model's judgement: reported apart
        by[r["policy"]][r["outcome"]] += 1
        by[r["policy"]]["cases"] += 1
        if r["outcome"] == "right" and r.get("reason"):
            by[r["policy"]][f"right_{r['reason']}"] += 1
    return {p: by[p] for p in POLICIES if p in by}


def _p(r: dict) -> str:
    return f"{r['p']:.2f}" if isinstance(r.get("p"), (int, float)) else "—"


def print_polarity(results: list[dict]) -> None:
    """How the Yes/No facts' questions were read (same / opposite / unsure), and by which engine."""
    asked = [r for r in results if r.get("polarity")]
    if asked:
        print(f"\nPolarity of Yes/No questions: {dict(Counter(r['polarity'] for r in asked))}; decided by "
              f"{dict(Counter(r['polarity_by'] for r in asked if r.get('polarity_by')))}")


def print_second_opinions(results: list[dict]) -> None:
    fast = [r for r in results if r.get("decided_by") == "fast"]
    if fast:
        print(f"\nDecided by the fast second opinion ({len(fast)}): "
              + ", ".join(f"{r.get('id') or r.get('label', '')[:40]} ({r['outcome'] if 'outcome' in r else r['got']})"
                          for r in fast))


def print_picks(engine: str, results: list[dict]) -> None:
    print(f"\n### Labelled picks — {engine}\n")
    print("| policy | cases | right (matched / closest / assumed) | abstained (answer expected) | abstained (right) "
          "| wrong writes | failed (Jev / model) |")
    print("|---|---|---|---|---|---|---|")
    for policy, c in tally(results).items():
        label = "reasoned (fast model, every engine)" if policy == "reasoned" else policy
        print(f"| {label} | {c['cases']} | {c['right']} ({c['right_matched']} / {c['right_closest']} / "
              f"{c['right_assumed']}) | {c['abstained']} | {c['abstained_ok']} | {c['wrong_write']} | "
              f"{c['jev_failed']} / {c['model_failed']} |")
    for r in results:
        if r.get("code_path"):
            print(f"- code-path check {r['id']}: {r['outcome']} (not counted above)")
    for r in results:
        if r["outcome"] == "wrong_write" and not r.get("code_path"):
            print(f"- WRONG WRITE [{r['policy']}] {r['id']}: {r['question']!r} fact {r['fact']!r} options {r['options']} "
                  f"expected {r['expected'] or 'none'} got {r['got']!r} ({r['reason']}, p={_p(r)})")
    for r in results:
        if r["outcome"] == "abstained":
            print(f"- abstained [{r['policy']}] {r['id']}: expected {r['expected']}; the model said {r['said']!r} "
                  f"at p={_p(r)}")
        elif r["outcome"] in ("jev_failed", "model_failed"):
            print(f"- {r['outcome']} [{r['policy']}] {r['id']}: {r['reason']}")
    print_polarity(results)
    print_second_opinions(results)


def print_steps(engine: str, results: list[dict]) -> None:
    print(f"\n### Labelled steps — {engine}\n")
    print("| policy | cases | right | give_up (right) | give_up (a move expected) | wrong clicks "
          "| wrong-but-harmless | failed (Jev / model) |")
    print("|---|---|---|---|---|---|---|---|")
    for policy, c in tally(results).items():
        print(f"| {policy} | {c['cases']} | {c['right']} | {c['give_up_ok']} | {c['give_up']} | {c['wrong_click']} "
              f"| {c['harmless']} | {c['jev_failed']} / {c['model_failed']} |")
    for r in results:
        if r["outcome"] in ("wrong_click", "harmless", "give_up"):
            print(f"- {r['outcome'].upper()} [{r['policy']}] {r['id']}: {r['question']!r} fact {r['fact']!r} "
                  f"expected {r['expected']} got {r['got']} ({r['got_describe']}; {r['reason']}; the model said "
                  f"{r['said']} at p={_p(r)})")
        elif r["outcome"] in ("jev_failed", "model_failed"):
            print(f"- {r['outcome']} [{r['policy']}] {r['id']}: {r['reason']}")
    print_polarity(results)
    print_second_opinions(results)


def print_map(report: dict) -> None:
    print(f"\n### Mapping agreement — {report['engine']}\n")
    pct = f"{report['agreement']:.1%}" if report["agreement"] is not None else "n/a"
    print(f"Agreement {pct} over {report['scored']} rows; {report['failed_batches_rows']} rows in batches the engine "
          f"failed; rule slots the profile does not hold (not sent): {report['absent_from_profile']}\n")
    print("| label | rule slot | Jev slot | p |")
    print("|---|---|---|---|")
    for r in report["rows"]:
        if r["agree"] is False:
            p = f"{r['p']:.2f}" if isinstance(r["p"], float) else "—"
            label = r["label"].replace("|", "¦")[:140]
            print(f"| {label} | {r['rule_slot']} | {r['got']} | {p} |")
    print_second_opinions(report["rows"])


def print_map_cases(engine: str, results: list[dict]) -> None:
    c = Counter(r["outcome"] for r in results)
    print(f"\n### Labelled maps — {engine}\n")
    print(f"{len(results)} cases: {c['right']} right, {c['missed']} missed, {c['wrong_write']} wrong writes, "
          f"{c['jev_failed']} / {c['model_failed']} failed (Jev / model)")
    for r in results:
        if r["outcome"] in ("wrong_write", "missed"):
            print(f"- {r['outcome'].upper()} {r['id']}: {r['question']!r} expected {r['expected']} got {r['got']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, required=True,
                    help="a COPY of the database (never a file under a checkout's data/ or DATA_DIR)")
    ap.add_argument("--part", choices=["map", "pick", "step", "all"], default="all")
    ap.add_argument("--engines", default="jev,fast,routed", help="any of jev (alone), fast, routed (production)")
    ap.add_argument("--map-engine", default="routed")
    ap.add_argument("--base", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", default=None, help="comma-separated case ids (a smoke run)")
    ap.add_argument("--tag", default=None, help='only the cases carrying this tag (e.g. "reversed")')
    args = ap.parse_args(argv)
    if why := refusal(args.db):
        ap.error(why)
    # Before the app is imported: its settings read these once.
    os.environ["DATABASE_URL"] = f"sqlite:///{args.db.resolve()}"
    os.environ.pop("TEST_DATABASE_URL", None)
    for name in ("SETTINGS_DIR", "LOGS_DIR"):
        os.environ.setdefault(name, tempfile.mkdtemp(prefix=f"eval-{name.lower()}-"))
    logging.basicConfig(level=logging.ERROR)
    bind_read_only(args.db)

    from app.db import SessionLocal

    engines = [e for e in args.engines.split(",") if e]
    out: dict[str, Any] = {}
    picks, steps, maps = load_cases(PICK_CASES), load_cases(STEP_CASES), load_cases(MAP_CASES)
    for case in picks["cases"]:
        check_pick_case(case)
    for case in steps["cases"]:
        check_step_case(case)
    for case in maps["cases"]:
        check_map_case(case, maps["facts"])
    only = set(args.only.split(",")) if args.only else None
    picks["cases"] = select_cases(picks["cases"], only=only, tag=args.tag)
    steps["cases"] = select_cases(steps["cases"], only=only, tag=args.tag)
    maps["cases"] = select_cases(maps["cases"], only=only, tag=args.tag)
    with SessionLocal() as session:
        if args.part in ("pick", "all"):
            for engine in engines:
                run = Run(engine)
                results = [run_pick(c, run, session, picks["today"]) for c in picks["cases"]]
                out[f"pick_{engine}"] = {"results": results, "jev_errors": Counter(run.jev_errors)}
                print_picks(engine, results)
        if args.part in ("step", "all"):
            for engine in engines:
                run = Run(engine)
                results = [run_step(c, run, session, steps["today"]) for c in steps["cases"]]
                out[f"step_{engine}"] = {"results": results, "jev_errors": Counter(run.jev_errors)}
                print_steps(engine, results)
        if args.part in ("map", "all"):
            for engine in engines:
                run = Run(engine)
                results = run_map_cases(maps["cases"], map_case_facts(maps), run, session)
                out[f"map_cases_{engine}"] = {"results": results, "jev_errors": Counter(run.jev_errors)}
                print_map_cases(engine, results)
            run = Run(args.map_engine)
            report = run_map(session, run, args.base)
            report["jev_errors"] = Counter(run.jev_errors)
            out["map"] = report
            print_map(report)
        session.rollback()   # nothing to undo: the session is read-only (bind_read_only)
    for key, value in out.items():
        if value.get("jev_errors"):
            print(f"\n{key}: Jev errors {dict(value['jev_errors'])}")
    if args.out:
        args.out.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
