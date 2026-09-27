"""Meaning evaluation of the fill engine's decisions (fill-engine revision Task 12).

Three reports, each printed as Markdown (and written as JSON with --out):

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

Picks and steps run once per engine (Jev, then the fast model; `--engines`),
reported separately: the fast model's confidence is not calibrated by sharing
Jev's floors. In a Jev pass Jev's own fallback to the fast model is turned
off, so a Jev failure is counted as one, never scored as Jev's answer. The
reasoning route is the fast model's on every engine (autofill_reasoned).

Only labels, options and each case's own fact go to the models; the cases are
synthetic. Run from backend/, against a COPY of the live database (never the
live file), with the keys the copy's settings hold:

    set -a; source <main-checkout>/.env; set +a
    DATA_DIR=<copy dir> SETTINGS_DIR=<copy dir>/settings LOGS_DIR=<scratch>/logs \\
    BASE_RESUMES_DIR=<main-checkout>/base_resumes \\
        /opt/anaconda3/bin/python3 -m scripts.eval_fill_decisions --out <scratch>/eval.json

`--part map|pick|step` runs one report; `--base <slug>` picks the resume the
mapping catalog reads (default: the first active one). Offline shape checks:
tests/test_eval_fill_cases.py.
"""

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PICK_CASES = HERE / "fill_pick_cases.json"
STEP_CASES = HERE / "fill_step_cases.json"
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
             "eligibility.previously_employed_here": {"derived.previously_employed_here"}}
# Telemetry's control kinds as the fill loop's shapes (a combobox is a search
# box or a popup; /map reads the shape only to tell prose from a choice).
KIND_TO_SHAPE = {"text": "text", "textarea": "text", "select": "select", "combobox": "search",
                 "radio": "group", "checkbox": "group"}
MAP_BATCH = 10
GIVE_UP_DESCRIBE = "Stop: no move will select an option that states the value"
JOB_KEYS = ("employer", "title", "description", "start", "end", "current")
SCHOOL_KEYS = ("school", "degree", "discipline", "start_year", "end_year")
POLICIES = ("exact", "flag", "any", "low_stakes", "reasoned")


# ---------------------------------------------------------------- cases


def rule_ids() -> set[str]:
    """Every rule id the extension's rule tables declare."""
    ids: set[str] = set()
    for path in RULE_FILES:
        ids |= set(re.findall(r'\{\s*id:\s*"([a-z0-9-]+)"', path.read_text(encoding="utf-8")))
    return ids


def load_cases(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_of(case: dict) -> list[str]:
    """The acceptable answers: [] when abstaining (or give_up) is the only right answer."""
    got = case.get("expected")
    return [] if got is None else [got] if isinstance(got, str) else list(got)


def pick_policy(case: dict) -> str:
    from app.services.autofill_slots import policy_for

    route = case.get("route", "slot")
    return route if route != "slot" else policy_for(case["slot"])


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
    if route == "reasoned":
        hist = case.get("history")
        if not (isinstance(hist, dict) and isinstance(hist.get("jobs"), list) and isinstance(hist.get("schools"), list)):
            raise ValueError(f"{cid}: a reasoned case carries a history of jobs and schools")
        for job in hist["jobs"]:
            if set(job) - set(JOB_KEYS) or not job.get("employer"):
                raise ValueError(f"{cid}: a job holds only {JOB_KEYS}, an employer at least")
        for school in hist["schools"]:
            if set(school) - set(SCHOOL_KEYS) or not school.get("school"):
                raise ValueError(f"{cid}: a school holds only {SCHOOL_KEYS}, a school at least")


def check_step_case(case: dict) -> None:
    """Raise ValueError when a step case is malformed (the request must be one /step accepts)."""
    from app.schemas.autofill_fill import StepRequest

    cid = case.get("id")
    route = case.get("route", "slot")
    try:
        req = step_request(case)
    except Exception as exc:  # pydantic's error names the bad part
        raise ValueError(f"{cid}: not a valid /step request: {exc}") from exc
    assert isinstance(req, StepRequest)
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
    """The facts one case holds: its slot's fact, its history, and today."""
    from app.services.autofill_catalog import Fact, _describe
    from app.services.autofill_slots import _as_text, policy_for

    facts = {"derived.today": Fact("derived.today", today, "today's date", policy_for("derived.today"))}

    def add(slot: str, value: Any) -> None:
        value = tuple(value) if isinstance(value, list) else value if isinstance(value, str) else _as_text(value)
        if value not in (None, "", ()):
            facts[slot] = Fact(slot, value, _describe(slot), policy_for(slot))

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


@contextmanager
def engine_of(run: Run, low_stakes: bool = False):
    """Force the engine and the low-stakes setting; in a Jev pass, record
    Jev's failures and refuse the fast-model fallback."""
    from app.services import autofill_map, autofill_pick, autofill_step, jev, llm, model_settings

    saved = {(model_settings, "get_autofill_engine"): model_settings.get_autofill_engine,
             (model_settings, "get_autofill_low_stakes"): model_settings.get_autofill_low_stakes,
             (jev, "decide"): jev.decide,
             (autofill_pick, "_with_llm"): autofill_pick._with_llm,
             (autofill_map, "_with_llm"): autofill_map._with_llm,
             (autofill_step, "fast_json"): autofill_step.fast_json,
             (autofill_pick, "verdict"): autofill_pick.verdict,
             (autofill_step, "_decide"): autofill_step._decide}
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

    model_settings.get_autofill_engine = lambda session=None: run.engine
    model_settings.get_autofill_low_stakes = lambda session=None: low_stakes
    autofill_pick.verdict, autofill_step._decide = seen_pick, seen_step
    if run.engine == "jev":
        jev.decide = recorded
        autofill_pick._with_llm = refuse
        autofill_map._with_llm = refuse
        autofill_step.fast_json = refuse
    try:
        yield
    finally:
        for (module, name), value in saved.items():
            setattr(module, name, value)


def run_pick(case: dict, run: Run, session, today: str) -> dict:
    from app.services import autofill_pick, llm

    fld = pick_field(case)
    hint = autofill_pick.JobHint(title="Data Analyst", company="Acme Corp", source=case.get("source"))
    run.trace.clear()
    try:
        with engine_of(run, low_stakes=case.get("low_stakes") == "on"):
            picked = autofill_pick.pick([fld], case_facts(case, today), session, hint)["c1"]
    except (JevFellBack, llm.LLMProviderError) as exc:
        failed = "jev_failed" if isinstance(exc, JevFellBack) else "model_failed"
        return {"id": case["id"], "policy": pick_policy(case), "outcome": failed, "got": None, "reason": str(exc)}
    got = next((o.text for o in fld.options if picked.oids and o.oid == picked.oids[0]), None)
    expected = expected_of(case)
    if got is None:
        outcome = "abstained_ok" if not expected else "abstained"
    else:
        outcome = "right" if got in expected else "wrong_write"
    said = {o.oid: o.text for o in fld.options}.get(run.trace[-1][0]) if run.trace else None
    return {"id": case["id"], "policy": pick_policy(case), "outcome": outcome, "got": got,
            "reason": picked.reason, "said": said, "p": run.trace[-1][1] if run.trace else None,
            "expected": expected, "question": case["question"], "options": case["options"],
            "fact": case.get("item") or case.get("fact")}


def step_policy(case: dict) -> str:
    from app.services.autofill_slots import policy_for

    route = case.get("route", "slot")
    return route if route != "slot" else policy_for(case["slot"])


def run_step(case: dict, run: Run, session, today: str) -> dict:
    from app.services import autofill_pick, autofill_step, llm

    req = step_request(case)
    hint = autofill_pick.JobHint(title="Data Analyst", company="Acme Corp", source=case.get("source"))
    run.trace.clear()
    try:
        with engine_of(run, low_stakes=case.get("low_stakes") == "on"):
            resp = autofill_step.step(req, case_facts(case, today), session, hint)
    except (JevFellBack, llm.LLMProviderError) as exc:
        failed = "jev_failed" if isinstance(exc, JevFellBack) else "model_failed"
        return {"id": case["id"], "policy": step_policy(case), "outcome": failed, "got": None, "reason": str(exc)}
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
    return {"id": case["id"], "policy": step_policy(case), "outcome": outcome, "got": mid,
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
    from app.services import autofill_catalog, eeo_consent
    from app.services.autofill_context import employment_blocks, resume_skills
    from app.services.base_resume_data import active_base_resume_slugs, load_base_resume

    slug = base or next(iter(active_base_resume_slugs(session)), None)
    resume = load_base_resume(slug, session) if slug else None
    return autofill_catalog.build(eeo_consent.disclosable_profile(session),
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
    consented = eeo_consent.get_consent(session).enabled

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
            # The reasoning pass is not a mapping: it is not asked.
            autofill_map._with_jev, autofill_map._answerable = keep, lambda *_a, **_k: set()
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
                results.append({**r, "rule_slot": want, "got": None, "p": None, "agree": None})
                continue
            m = mapped[f.fid]
            key, p = raw.get(f.fid, (None, None))
            got = unindexed(m.slot) if m.route == "slot" else f"({m.route}{': ' + key if key and m.route == 'none' else ''})"
            agree = m.route == "slot" and (got == want or got in SAME_FACT.get(want, set()))
            results.append({**r, "rule_slot": want, "got": got, "p": p, "agree": agree, "retried": failed})
    scored = [r for r in results if r["agree"] is not None]
    return {"engine": run.engine, "rows": results, "absent_from_profile": dict(absent),
            "agreement": (sum(r["agree"] for r in scored) / len(scored)) if scored else None,
            "scored": len(scored), "failed_batches_rows": len(results) - len(scored)}


# ---------------------------------------------------------------- reports


def tally(results: list[dict]) -> dict[str, Counter]:
    by: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        by[r["policy"]][r["outcome"]] += 1
        by[r["policy"]]["cases"] += 1
        if r["outcome"] == "right" and r.get("reason"):
            by[r["policy"]][f"right_{r['reason']}"] += 1
    return {p: by[p] for p in POLICIES if p in by}


def _p(r: dict) -> str:
    return f"{r['p']:.2f}" if isinstance(r.get("p"), (int, float)) else "—"


def print_picks(engine: str, results: list[dict]) -> None:
    print(f"\n### Labelled picks — {engine}\n")
    print("| policy | cases | right (matched / closest / assumed) | abstained (answer expected) | abstained (right) "
          "| wrong writes | failed (Jev / model) |")
    print("|---|---|---|---|---|---|---|")
    for policy, c in tally(results).items():
        print(f"| {policy} | {c['cases']} | {c['right']} ({c['right_matched']} / {c['right_closest']} / "
              f"{c['right_assumed']}) | {c['abstained']} | {c['abstained_ok']} | {c['wrong_write']} | "
              f"{c['jev_failed']} / {c['model_failed']} |")
    for r in results:
        if r["outcome"] == "wrong_write":
            print(f"- WRONG WRITE [{r['policy']}] {r['id']}: {r['question']!r} fact {r['fact']!r} options {r['options']} "
                  f"expected {r['expected'] or 'none'} got {r['got']!r} ({r['reason']}, p={_p(r)})")
    for r in results:
        if r["outcome"] == "abstained":
            print(f"- abstained [{r['policy']}] {r['id']}: expected {r['expected']}; the model said {r['said']!r} "
                  f"at p={_p(r)}")
        elif r["outcome"] in ("jev_failed", "model_failed"):
            print(f"- {r['outcome']} [{r['policy']}] {r['id']}: {r['reason']}")


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--part", choices=["map", "pick", "step", "all"], default="all")
    ap.add_argument("--engines", default="jev,fast")
    ap.add_argument("--map-engine", default="jev")
    ap.add_argument("--base", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", default=None, help="comma-separated case ids (a smoke run)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)

    from app.db import SessionLocal

    engines = [e for e in args.engines.split(",") if e]
    out: dict[str, Any] = {}
    picks, steps = load_cases(PICK_CASES), load_cases(STEP_CASES)
    for case in picks["cases"]:
        check_pick_case(case)
    for case in steps["cases"]:
        check_step_case(case)
    if args.only:
        only = set(args.only.split(","))
        picks["cases"] = [c for c in picks["cases"] if c["id"] in only]
        steps["cases"] = [c for c in steps["cases"] if c["id"] in only]
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
                results = [run_step(c, run, session, picks["today"]) for c in steps["cases"]]
                out[f"step_{engine}"] = {"results": results, "jev_errors": Counter(run.jev_errors)}
                print_steps(engine, results)
        if args.part in ("map", "all"):
            run = Run(args.map_engine)
            report = run_map(session, run, args.base)
            report["jev_errors"] = Counter(run.jev_errors)
            out["map"] = report
            print_map(report)
        session.rollback()   # the eval writes nothing
    for key, value in out.items():
        if value.get("jev_errors"):
            print(f"\n{key}: Jev errors {dict(value['jev_errors'])}")
    if args.out:
        args.out.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
