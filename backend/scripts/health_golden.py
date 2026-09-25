"""Manual pilot: python scripts/health_golden.py --split test --trials 3.

Synthetic text, uncached requests, disposable SQLite. Configure the provider via
its environment settings (the disposable database holds no stored key, model or
endpoint). Needs no DATABASE_URL: see `golden_session`.
"""
from __future__ import annotations
import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.orm import Session
import app.models  # noqa: F401 -- registers every table for create_all
from app.config import settings
from app.db import Base, SessionLocal, make_engine
from app.services import bullet_classify as bc, model_settings

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/health_golden.json"
RANK = {name: i for i, name in enumerate(("unaddressed", "implied", "adjacent", "analogue", "direct"))}


def summarize(cases: list[dict], runs: list[list[dict]], disputes: list[dict],
              dispute_runs: list[list[dict]]) -> dict:
    """Aggregate all case/trial pairs; enforce each role independently."""
    def metrics(role):
        exact = within = unnatural = total = 0
        for run in runs:
            for i, case in enumerate(cases):
                if role is not None and case["role"] != role:
                    continue
                result = run[i] if i < len(run) else {}
                total += 1
                level, expected = result.get("level"), case["expected_level"]
                exact += level == expected
                within += level in RANK and abs(RANK[level] - RANK[expected]) <= 1
                unnatural += result.get("ask_kind") == "measure" and not case["number_natural"]
        return {"exact": exact / total if total else 0, "within_one": within / total if total else 0,
                "unnatural_number_asks": unnatural, "n": total}
    overall = metrics(None)
    by_role = {role: metrics(role) for role in sorted({c["role"] for c in cases})}
    flips = sum(before[i].get("level") != after[i].get("level")
                for before, after in zip(runs, runs[1:])
                for i in range(min(len(before), len(after))))
    above = survived = missing = 0
    for run in dispute_runs:
        for i, case in enumerate(disputes):
            result = run[i] if i < len(run) else {}
            level = result.get("level")
            missing += level not in RANK
            above += level in RANK and RANK[level] > RANK[case["max_level"]]
            survived += case["metric_unavailable"] and result.get("ask_kind") == "measure"
    passed = bool(runs) and overall["within_one"] >= 0.9 and overall["exact"] >= 0.7
    passed = passed and all(m["within_one"] >= 0.8 and m["unnatural_number_asks"] == 0
                            for m in by_role.values())
    passed = passed and not (above or survived or missing) and (not disputes or bool(dispute_runs))
    return {"overall": overall, "roles": by_role, "level_flips": flips,
            "unnatural_number_asks": overall["unnatural_number_asks"],
            "disputes": {"above_max": above, "measure_survived": survived, "missing": missing},
            "passed": passed}


def run_trials(db: Session, cases: list[dict], disputes: list[dict], trials: int) -> dict:
    runs, dispute_runs = [], []
    for _ in range(trials):
        pending = {bc.content_hash(c["text"]): {"id": bc.content_hash(c["text"]),
                   "text": c["text"], "hints": []} for c in cases}
        results = bc.evaluate_uncached(db, pending)  # bypass classify_items cache
        runs.append([results.get(bc.content_hash(c["text"]), {}) for c in cases])
        trial = []
        # Same text with different notes must not collapse in a hash-keyed batch.
        for case in disputes:
            key = bc.content_hash(case["text"])
            result = bc.evaluate_uncached(db, {key: {"id": key, "text": case["text"],
                                        "note": case["note"], "hints": []}})
            trial.append(result.get(key, {}))
        dispute_runs.append(trial)
    return summarize(cases, runs, disputes, dispute_runs)


@contextmanager
def golden_session(directory: str) -> Iterator[Session]:
    """A session on a fresh SQLite file in `directory`, and every app read with it.

    The session passed around is not the only reader: `llm.call_openai` reads `llm.json_mode`,
    the API keys and the base URL through the app's global `SessionLocal`, whose engine is
    whatever DATABASE_URL named at import (unset: a file with no tables). So `SessionLocal`
    is bound to this engine for the run and handed back after. Call logs land in `directory`
    too, unless LOGS_DIR says otherwise (the default, /app/logs, exists only in the image).
    """
    engine = make_engine(f"sqlite:///{directory}/golden.sqlite3")
    Base.metadata.create_all(engine)
    previous_bind, previous_logs = SessionLocal.kw.get("bind"), settings.logs_dir
    SessionLocal.configure(bind=engine)
    if "LOGS_DIR" not in os.environ:
        settings.logs_dir = Path(directory) / "logs"
    try:
        with SessionLocal() as db:
            yield db
    finally:
        SessionLocal.configure(bind=previous_bind)
        settings.logs_dir = previous_logs
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    fixture = json.loads(FIXTURE.read_text())
    cases = [c for c in fixture["bullets"] if c["split"] == args.split]
    with tempfile.TemporaryDirectory(prefix="health-golden-") as directory:
        with golden_session(directory) as db:
            report = run_trials(db, cases, fixture["disputes"], args.trials)
            report.update(split=args.split, trials=args.trials,
                          model=model_settings.get_smart_model(db),
                          rubric_version=bc.RUBRIC_VERSION)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
