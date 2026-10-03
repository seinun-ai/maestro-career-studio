"""Keep the last runs' traces and fold each new run into per-mechanism counters.

SYSTEM.md {#inv-autofill-telemetry-no-values}: a counter key holds enums, ids and bands only,
never a host or a label, so the counters outlive clearing the runs. The stored runs hold the
trace itself (value-free by schema) and are what DELETE /telemetry clears.

Every key format lives here (the `*_key` builders, `KEY_PARTS`, `parse_key`) so the report
script reads keys the way this module writes them.
"""

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import begin_write
from app.models.autofill_mechanism_stat import AutofillMechanismStat
from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace, TraceField, TraceStep

RUNS_KEPT = 50
KEPT = frozenset({"verified", "closest", "assumed", "already", "partial"})  # report statuses (fill-loop.js header)
FAILED = frozenset({"unconfirmed", "cannot_operate", "unsupported"})
DECISIONS = frozenset({"map", "polarity", "pick", "step"})
ACTIONS = frozenset({"explore", "choose", "set", "write", "move"})
REJECTED = frozenset({"no_effect", "unexpected", "reverted", "refused"})  # the effects that waste a try
NONE_PART = "-"  # a key part with no value (no family, no floor, no band)

# The parts of each key family, after its name: `action|<family>|<kind>` and so on.
KEY_PARTS = {
    "action": ("family", "kind"),
    "decision": ("op", "engine", "by", "floor", "band", "choice"),
    "first": ("op", "floor", "band", "agree"),
    "second": ("op",),
}

Counters = dict[str, dict[str, int]]


def band(p: float | None) -> str | None:
    """The confidence band a decision is counted in: str(min(int(p * 10 + 1e-9), 9) / 10)."""
    if p is None:
        return None
    return str(min(int(p * 10 + 1e-9), 9) / 10)


def _band_part(p: float | None) -> str:
    return band(p) or NONE_PART


def _floor_part(floor: float | None) -> str:
    return NONE_PART if floor is None else str(round(floor, 2))


def action_key(family: str | None, kind: str) -> str:
    return f"action|{family or NONE_PART}|{kind}"


def decision_key(step: TraceStep) -> str:
    """`by` is `first` unless a second opinion decided: the second engine only runs on the first's
    abstentions, so its population differs. `choice` is the polarity `way` for a polarity step, else
    answer / none (the model chose the no-answer key) / unknown (its choice could not be read)."""
    by = "second" if step.second == "decided" else "first"
    if step.op == "polarity":
        choice = step.way or "unknown"
    else:
        choice = "unknown" if step.chose_none is None else "none" if step.chose_none else "answer"
    return (f"decision|{step.op}|{step.engine}|{by}|{_floor_part(step.floor)}|"
            f"{_band_part(step.p)}|{choice}")


def first_key(step: TraceStep) -> str:
    """One counter per step the second opinion decided, by the first engine's band: how often its
    answer was kept. The first engine is always Jev today (the second opinion only runs on Jev).
    `agree`: `same` (the first engine named the same choice), `other` (it named another) or
    `unknown` (not known). Only `same` rows are evidence the first engine was right."""
    agree = "unknown" if step.first_same is None else "same" if step.first_same else "other"
    return f"first|{step.op}|{_floor_part(step.floor)}|{_band_part(step.first_p)}|{agree}"


def second_key(op: str) -> str:
    """`asked`: the second opinion ran and did not change the answer; `decided`: its answer stands.
    Total asks are asked + decided."""
    return f"second|{op}"


def parse_key(key: str) -> tuple[str, dict[str, str]]:
    """A counter key as (family name, {part name: value})."""
    name, *parts = key.split("|")
    return name, dict(zip(KEY_PARTS[name], parts, strict=True))


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
    key = action_key(field.family, kind)
    _bump(out, key, "tries")
    _bump(out, key, step.effect or "effect_unknown")
    if step.ms is not None:
        _bump(out, key, "timed")
        _bump(out, key, "ms", step.ms)


def _rejected_next(field: TraceField, after: int) -> bool:
    """Whether the next page action after step `after` was refused, reverted or had no effect."""
    for step in field.steps[after + 1:]:
        if step.op in ACTIONS:
            return step.effect in REJECTED
    return False


def _fold_decision(out: Counters, field: TraceField, at: int, status: str) -> None:
    key = decision_key(field.steps[at])
    _bump(out, key, "n")
    _bump(out, key, status)
    if _rejected_next(field, at):
        _bump(out, key, "rejected")


def _fold_second(out: Counters, step: TraceStep, status: str) -> None:
    key = second_key(step.op)
    _bump(out, key, step.second)
    if step.second != "decided":
        return
    if status == "kept":
        _bump(out, key, "decided_kept")
    first = first_key(step)
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
            elif step.op in DECISIONS and step.engine:  # no engine: code decided, never counted
                _fold_decision(out, field, at, status)
                if step.second:
                    _fold_second(out, step, status)
    return dict(out)


def _add_counters(db: Session, increments: Counters) -> None:
    rows = {
        row.key: row
        for row in db.scalars(
            select(AutofillMechanismStat).where(AutofillMechanismStat.key.in_(increments))
        )
    }
    for key, counts in increments.items():
        row = rows.get(key)
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
    to the newest RUNS_KEPT by started_at, fold a NEW run into the counters, and COMMIT.

    The dump and the fold are computed first, so the write lock is held only for the reads and
    writes. The lock then comes before the run_id lookup: routes run in the threadpool, so two
    posts close together would otherwise lose counter increments (read-modify-write) or 500 on a
    duplicate run_id insert. A re-post of a run that was already pruned looks new and is folded
    again; that is accepted, because it is rare.
    """
    doc = trace.model_dump(mode="json", exclude_none=True)
    increments = fold(trace)
    begin_write(db)
    row = db.scalar(select(AutofillRun).where(AutofillRun.run_id == trace.run_id))
    if row is None:
        db.add(AutofillRun(run_id=trace.run_id, host=trace.host, started_at=trace.started_at, trace=doc))
        _add_counters(db, increments)
    else:
        row.host, row.started_at, row.trace = trace.host, trace.started_at, doc
    db.flush()
    _prune(db)
    db.commit()
