"""Read the stored Autofill run traces: one run's decision path, field by field.

Run from backend/ against a COPY of the database (the same guard as the fill evaluation):

    python -m scripts.fill_trace --db <copy> last [--host H] [--n 1]

`last` prints the N newest runs. Per run one header line, then per field one line and one
indented line per step, so `grep` finds a field, an op or a floor:

    RUN <run_id>  <host>  <UTC time>  fields=N filled=N left=N prefilled=N halted=<none|stopped|timeout> rounds=N
    [outcome]  "label"  shape  label←source  family  round N
      map → <slot | route>  jev 0.97 ≥0.90  1.2s
      pick #2 matched  fast 0.97 ≥0.90  (decided; jev was 0.82, same choice)  2.1s
      polarity unsure  fast 0.61 (asked)
      choose → no_effect (no_effect)  412ms

A step with no engine was decided by code. "—" is a value the extension could not read; "none" is the
model choosing the no-answer key. The trace holds no answer text (SYSTEM.md
{#inv-autofill-telemetry-no-values}), so none is printed.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from scripts.db_copy import bind_read_only, open_copy, refusal


def _ms(ms: int | None) -> str | None:
    if ms is None:
        return None
    return f"{ms}ms" if ms < 1000 else f"{ms / 1000:.1f}s"


def _num(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def _join(*parts: str | None) -> str:
    return "  ".join(p for p in parts if p)


# ---------- decisions: what was chosen, then how sure the engine was


def _map_target(step) -> str:
    where = step.slot if step.route == "slot" and step.slot else step.route
    return f"→ {where or '—'}" + (f" ({step.why})" if step.why else "")


def _pick_target(step) -> str:
    chosen = "none" if step.chose_none else "—" if step.option is None else f"#{step.option}"
    return f"{chosen} {step.reason}" if step.reason else chosen


def _step_target(step) -> str:
    chosen = step.move or ("none" if step.chose_none else "—")
    return f"{chosen} {step.reason}" if step.reason else chosen


DECISION_TARGETS: dict[str, Callable] = {
    "map": _map_target,
    "pick": _pick_target,
    "polarity": lambda step: step.way or "—",
    "step": _step_target,
}


def _confidence(step) -> str:
    if step.engine is None:
        return "code"
    floor = f" ≥{step.floor:.2f}" if step.floor is not None else ""
    return f"{step.engine} {_num(step.p)}{floor}"


def _second(step) -> str | None:
    """`asked`: the second opinion ran and changed nothing; `decided`: its answer stands over Jev's."""
    if step.second == "decided":
        same = {True: ", same choice", False: ", other choice"}.get(step.first_same, "")
        return f"(decided; jev was {_num(step.first_p)}{same})"
    return f"({step.second})" if step.second else None


def _decision(step) -> str:
    return _join(f"{step.op} {DECISION_TARGETS[step.op](step)}", _confidence(step), _second(step), _ms(step.ms))


# ---------- page actions: what was tried, and what the page did


def _action(step) -> str:
    what = f"{step.op} {step.move}" if step.move else step.op
    effect = f"→ {step.effect or '—'}" + (f" ({step.word})" if step.word else "")
    return _join(f"{what} {effect}", _ms(step.ms))


def render_step(step) -> str:
    return _decision(step) if step.op in DECISION_TARGETS else _action(step)


# ---------- fields and runs


def render_field(field) -> list[str]:
    source = f"label←{field.label_source}" if field.label_source else None
    head = _join(f"[{field.outcome}]", f'"{field.label}"', field.shape, source, field.family,
                 f"round {field.round}" if field.round else None)
    return [head, *(f"  {render_step(step)}" for step in field.steps)]


def render_header(run, trace) -> str:
    """filled = ended kept (the key module's KEPT) except `already`, which is prefilled: the page
    had the answer before the run. left = every other outcome, FAILED ones included."""
    from app.services.autofill_trace import KEPT

    outcomes = [f.outcome for f in trace.fields]
    prefilled = outcomes.count("already")
    filled = sum(o in KEPT for o in outcomes) - prefilled
    left = len(outcomes) - filled - prefilled
    when = trace.started_at.strftime("%Y-%m-%d %H:%M:%SZ")
    return _join(f"RUN {trace.run_id}", trace.host, when,
                 f"fields={len(outcomes)} filled={filled} left={left} prefilled={prefilled} "
                 f"halted={trace.halted or 'none'} rounds={trace.rounds}")


def render_run(run) -> list[str]:
    from pydantic import ValidationError

    from app.schemas.autofill_trace import RunTrace

    try:
        trace = RunTrace.model_validate(run.trace)
    except ValidationError:
        return [f"RUN {run.run_id}  {run.host}  unreadable trace (it does not match the current schema)"]
    return [render_header(run, trace), *(line for field in trace.fields for line in render_field(field))]


def last(session, host: str | None, n: int) -> int:
    from sqlalchemy import select

    from app.models.autofill_run import AutofillRun

    query = select(AutofillRun).order_by(AutofillRun.started_at.desc(), AutofillRun.created_at.desc())
    if host:
        query = query.where(AutofillRun.host == host)
    runs = session.scalars(query.limit(n)).all()
    if not runs:
        print("no stored run" + (f" for host {host}" if host else ""), file=sys.stderr)
        return 1
    for run in runs:
        print("\n".join(render_run(run)))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, required=True,
                    help="a COPY of the database (never a file under a checkout's data/ or DATA_DIR)")
    sub = ap.add_subparsers(dest="command", required=True)
    p_last = sub.add_parser("last", help="the newest run(s), field by field")
    p_last.add_argument("--host", default=None, help="only runs on this host")
    p_last.add_argument("--n", type=int, default=1, help="how many runs, newest first (default 1)")
    args = ap.parse_args(argv)
    if why := refusal(args.db):
        ap.error(why)
    # Before the app is imported: its settings read these once.
    open_copy(args.db, bind=bind_read_only)

    from app.db import SessionLocal

    with SessionLocal() as session:
        return last(session, args.host, args.n)


if __name__ == "__main__":
    sys.exit(main())
