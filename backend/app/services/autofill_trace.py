"""Keep the last runs' traces and fold each new run into per-mechanism counters.

SYSTEM.md {#inv-autofill-telemetry-no-values}: a counter key holds enums, ids and bands only,
never a host or a label, so the counters outlive clearing the runs. The stored runs hold the
trace itself (value-free by schema) and are what DELETE /telemetry clears.
"""

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import begin_write
from app.models.autofill_mechanism_stat import AutofillMechanismStat
from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace, TraceField, TraceStep

RUNS_KEPT = 50
KEPT = {"verified", "closest", "assumed", "already", "partial"}  # report statuses (fill-loop.js header)
FAILED = {"unconfirmed", "cannot_operate", "unsupported"}
DECISIONS = {"map", "polarity", "pick", "step"}
ACTIONS = {"explore", "choose", "set", "write", "move"}
REJECTED = {"no_effect", "unexpected", "reverted", "refused"}

Counters = dict[str, dict[str, int]]


def band(p: float | None) -> str | None:
    """The confidence band a decision is counted in: str(min(int(p * 10 + 1e-9), 9) / 10)."""
    if p is None:
        return None
    return str(min(int(p * 10 + 1e-9), 9) / 10)


def _status(field: TraceField) -> str:
    """How the field ended, as the counters name it: kept, failed, or left (everything else)."""
    if field.outcome in KEPT:
        return "kept"
    return "failed" if field.outcome in FAILED else "left"


def _bump(out: Counters, key: str, name: str, n: int = 1) -> None:
    counts = out[key]
    counts[name] = counts.get(name, 0) + n


def _fold_action(out: Counters, field: TraceField, step: TraceStep) -> None:
    kind = step.move.split(":")[0] if step.op == "move" and step.move else step.op
    key = f"action|{field.family or '-'}|{kind}"
    _bump(out, key, "tries")
    if step.effect:
        _bump(out, key, step.effect)
    if step.ms:
        _bump(out, key, "ms", step.ms)


def _rejected_next(field: TraceField, after: int) -> bool:
    """Whether the next page action after step `after` was refused, reverted or had no effect."""
    for step in field.steps[after + 1:]:
        if step.op in ACTIONS:
            return step.effect in REJECTED
    return False


def _fold_decision(out: Counters, field: TraceField, at: int, status: str) -> None:
    step = field.steps[at]
    floor = "-" if step.floor is None else str(round(step.floor, 2))
    answer = "none" if step.chose_none else "answer"
    key = f"decision|{step.op}|{step.engine}|{floor}|{band(step.p) or '-'}|{answer}"
    _bump(out, key, "n")
    _bump(out, key, status)
    if _rejected_next(field, at):
        _bump(out, key, "rejected")


def _fold_second(out: Counters, step: TraceStep, status: str) -> None:
    key = f"second|{step.op}"
    _bump(out, key, step.second)
    if step.second == "decided":
        if status == "kept":
            _bump(out, key, "decided_kept")
        if step.first_same:
            first = f"first|{step.op}|{band(step.first_p) or '-'}"
            _bump(out, first, "n")
            _bump(out, first, status)


def fold(trace: RunTrace) -> Counters:
    """The counter increments one run adds, keyed without host or label."""
    out: Counters = defaultdict(dict)
    for field in trace.fields:
        status = _status(field)
        for at, step in enumerate(field.steps):
            if step.op in ACTIONS:
                _fold_action(out, field, step)
            if step.op in DECISIONS and step.engine:
                _fold_decision(out, field, at, status)
            if step.second:
                _fold_second(out, step, status)
    return dict(out)


def _add_counters(db: Session, increments: Counters) -> None:
    for key, counts in increments.items():
        row = db.get(AutofillMechanismStat, key)
        if row is None:
            db.add(AutofillMechanismStat(key=key, counts=dict(counts)))
            continue
        merged = dict(row.counts)
        for name, n in counts.items():
            merged[name] = merged.get(name, 0) + n
        # JSON column: REASSIGN, never mutate in place (the telemetry route's rule).
        row.counts = merged


def _prune(db: Session) -> None:
    old = db.scalars(
        select(AutofillRun.id)
        .order_by(AutofillRun.started_at.desc(), AutofillRun.created_at.desc(), AutofillRun.id)
        .offset(RUNS_KEPT)
    ).all()
    if old:
        db.execute(delete(AutofillRun).where(AutofillRun.id.in_(old)))


def store_run(db: Session, trace: RunTrace) -> None:
    """Insert the run (a re-post of the same run_id replaces it and is NOT folded twice), prune
    to the newest RUNS_KEPT by started_at, and fold a NEW run into the counters.

    The write lock comes first: routes run in the threadpool, so two posts close together would
    otherwise lose counter increments (read-modify-write) or 500 on a duplicate run_id insert.
    A re-post of a run that was already pruned looks new and is folded again; that is accepted,
    because it is rare.
    """
    begin_write(db)
    doc = trace.model_dump(mode="json", exclude_none=True)
    row = db.scalar(select(AutofillRun).where(AutofillRun.run_id == trace.run_id))
    if row is None:
        db.add(AutofillRun(run_id=trace.run_id, host=trace.host, started_at=trace.started_at, trace=doc))
        _add_counters(db, fold(trace))
    else:
        row.host, row.started_at, row.trace = trace.host, trace.started_at, doc
    db.flush()
    _prune(db)
    db.commit()
