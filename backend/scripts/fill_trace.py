"""Read the stored Autofill run traces: one run's decision path, field by field.

Run from backend/ against a COPY of the database (the same guard as the fill evaluation):

    python -m scripts.fill_trace --db <copy> last [--host H] [--n 1]

    python -m scripts.fill_trace --db <copy> report

`report` prints the never-expiring counters and the stored runs: a `window:` line (how far back the
counters and the runs reach), a `legend:` line (what kept and rejected mean), then five `== Section ==`
blocks: wasted actions, calibration, first-engine and second-opinion value, slowest fields, threshold
suggestions. A block with nothing to show prints `(no data)`. Headers, `window:`, `legend:` and
`note:` lines are prose; every other line is `key=value` pairs separated by two spaces, so `grep`
finds a family, an op or a floor. A count prints as `kept=41/42(98%)`: the count first, never only
a rounded percent. `kept` is an outcome proxy (the field ended filled), not proof the answer was
right.

A suggestion lowers a floor only on evidence: the contiguous bands just under the floor, each with at
least 20 decisions, where the second opinion decided, the first engine agreed and the field was kept,
with a Wilson 95% lower bound of at least 0.85. The first engine's other below-floor answers count in
the denominator as not confirmed. A band must END at or below the floor (band + 0.1 <= floor), so a
flag-policy floor of 0.85 is only ever suggested from the 0.7 band down. The `first|pick` rows at the
closest floor are skipped (see `_suggests`).

`last` prints the N newest runs. Per run one header line, then per field one line and one
indented line per step, so `grep` finds a field, an op or a floor:

    RUN <run_id>  <host>  <UTC time>  fields=N filled=N left=N failed=N prefilled=N halted=<none|stopped|timeout> rounds=N
    [outcome]  "label"  shape  label←source  family  round N
      map → <slot | route:R>  jev 0.97 ≥0.90  1.2s
      pick opt[2] matched  fast 0.97 ≥0.90  (decided; jev was 0.82, same choice)  2.1s
      polarity unsure  fast 0.61  (asked)
      choose → no_effect (no_effect)  412ms

A step with no engine was decided by code. "—" is a value the extension could not read; "none" is
the model choosing the no-answer key; `route:none` is /map routing the field to no fact. In
`opt[N]`, N is the 0-based index into the options offered to /pick (not the field's `options`
list, which is capped). Labels print as JSON strings, so a label cannot fake a line. The trace
holds no answer text (SYSTEM.md {#inv-autofill-telemetry-no-values}), so none is printed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.db_copy import bind_read_only, open_copy, refusal

if TYPE_CHECKING:  # the app is imported only after open_copy sets its environment
    from sqlalchemy.orm import Session

    from app.models.autofill_run import AutofillRun
    from app.schemas.autofill_trace import RunTrace, TraceField, TraceStep


# json leaves these raw with ensure_ascii=False, yet str.splitlines() splits on them.
_LINE_BREAKS = str.maketrans({"\u2028": "\\u2028", "\u2029": "\\u2029", "\x85": "\\u0085"})


def _label(s: str) -> str:
    """A page's text as one JSON string: quotes and line breaks escaped, so it cannot fake a line."""
    return json.dumps(s, ensure_ascii=False).translate(_LINE_BREAKS)


def _ms(ms: int | None) -> str | None:
    if ms is None:
        return None
    return f"{ms}ms" if ms < 1000 else f"{ms / 1000:.1f}s"


def _num(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def _join(*parts: str | None) -> str:
    return "  ".join(p for p in parts if p)


# ---------- decisions: what was chosen, then how sure the engine was


def _map_target(step: TraceStep) -> str:
    where = step.slot if step.route == "slot" and step.slot else f"route:{step.route}" if step.route else "—"
    return f"→ {where}" + (f" ({step.why})" if step.why else "")


def _pick_target(step: TraceStep) -> str:
    chosen = "none" if step.chose_none else "—" if step.option is None else f"opt[{step.option}]"
    return f"{chosen} {step.reason}" if step.reason else chosen


def _step_target(step: TraceStep) -> str:
    chosen = step.move or ("none" if step.chose_none else "—")
    return f"{chosen} {step.reason}" if step.reason else chosen


DECISION_TARGETS: dict[str, Callable[[TraceStep], str]] = {
    "map": _map_target,
    "pick": _pick_target,
    "polarity": lambda step: step.way or "—",
    "step": _step_target,
}


def _confidence(step: TraceStep) -> str:
    if step.engine is None:
        return "code"
    floor = f" ≥{step.floor:.2f}" if step.floor is not None else ""
    return f"{step.engine} {_num(step.p)}{floor}"


def _second(step: TraceStep) -> str | None:
    """`asked`: the second opinion ran and changed nothing; `decided`: its answer stands over the
    first engine's. The first engine is always Jev today (see autofill_trace.first_key's docstring)."""
    if step.second == "decided":
        same = {True: ", same choice", False: ", other choice"}.get(step.first_same, "")
        return f"(decided; jev was {_num(step.first_p)}{same})"
    return f"({step.second})" if step.second else None


def _decision(step: TraceStep) -> str:
    return _join(f"{step.op} {DECISION_TARGETS[step.op](step)}", _confidence(step), _second(step), _ms(step.ms))


# ---------- page actions: what was tried, and what the page did


def _action(step: TraceStep) -> str:
    what = f"{step.op} {step.move}" if step.move else step.op
    effect = f"→ {step.effect or '—'}" + (f" ({step.word})" if step.word else "")
    return _join(f"{what} {effect}", _ms(step.ms))


def render_step(step: TraceStep) -> str:
    return _decision(step) if step.op in DECISION_TARGETS else _action(step)


# ---------- fields and runs


def render_field(field: TraceField) -> list[str]:
    source = f"label←{field.label_source}" if field.label_source else None
    head = _join(f"[{field.outcome}]", _label(field.label), field.shape, source, field.family,
                 f"round {field.round}" if field.round else None)
    return [head, *(f"  {render_step(step)}" for step in field.steps)]


def render_header(trace: RunTrace) -> str:
    """The key module's sets name how each field ended. prefilled: `already` (the page had the answer
    before the run). filled: the other KEPT outcomes. failed: FAILED outcomes. left: everything else."""
    from app.services.autofill_trace import FAILED, KEPT

    outcomes = [f.outcome for f in trace.fields]
    prefilled = outcomes.count("already")
    filled = sum(o in KEPT for o in outcomes) - prefilled
    failed = sum(o in FAILED for o in outcomes)
    left = len(outcomes) - filled - failed - prefilled
    when = trace.started_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    return _join(f"RUN {trace.run_id}", trace.host, when,
                 f"fields={len(outcomes)} filled={filled} left={left} failed={failed} prefilled={prefilled} "
                 f"halted={trace.halted or 'none'} rounds={trace.rounds}")


def _check(run: AutofillRun) -> tuple[RunTrace | None, str]:
    """The stored trace as a RunTrace and "", or None and the first failing location (never the
    value found there) when it no longer matches the schema."""
    from pydantic import ValidationError

    from app.schemas.autofill_trace import RunTrace

    try:
        return RunTrace.model_validate(run.trace), ""
    except ValidationError as e:
        loc = ".".join(str(part) for part in e.errors(include_input=False)[0]["loc"])
        return None, loc or "<root>"


def _trace(run: AutofillRun) -> RunTrace | None:
    return _check(run)[0]


def render_run(run: AutofillRun) -> list[str]:
    trace, loc = _check(run)
    if trace is None:
        return [f"RUN {run.run_id}  {run.host}  unreadable trace at {loc} (it does not match the current schema)"]
    return [render_header(trace), *(line for field in trace.fields for line in render_field(field))]


# ---------- report: counters and stored runs, aggregated

Row = tuple[dict[str, str], dict[str, int]]   # one counter row: (key parts, counts)
SlowField = tuple[str, str, int, int, str]    # (host, label, steps, total ms, outcome)
NO_DATA = "(no data)"
WASTED_SHOWN = 15
SLOWEST_SHOWN = 10
SUGGEST_MIN_N = 20
SUGGEST_MIN_LO = 0.85   # the Wilson lower bound the kept share of a band must reach
NO_SUGGESTION = ("no suggestion: no band just under a floor has ≥20 decisions with a 95% Wilson lower "
                 "bound ≥0.85 on being confirmed and kept")
SUGGESTION_NOTE = ("note: kept_same counts only decisions where the second opinion decided and the first engine "
                   "agreed; the first engine's other below-floor answers are in `of` as not confirmed; a "
                   "decision under its floor with no second opinion abstains, so real runs cannot show "
                   "whether it would have been kept; use the eval (scripts.eval_fill_decisions) for those")


def wilson95_lo(k: int, n: int) -> float:
    """The lower end of the Wilson 95% interval for k successes in n trials (0.0 when n is 0)."""
    if n <= 0:
        return 0.0
    z, p = 1.96, k / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / (1 + z * z / n))


def _frac(part: int, whole: int) -> str:
    """`41/42(98%)`: the count first, so a rounded percent never hides a small number."""
    return f"{part}/{whole}({100 * part / whole:.0f}%)" if whole else f"{part}/{whole}(—)"


def _pairs(**fields: object) -> str:
    return "  ".join(f"{name}={value}" for name, value in fields.items())


def _order(value: str) -> float:
    """A floor or band part as a number, for sorting; NONE_PART sorts first."""
    try:
        return float(value)
    except ValueError:
        return -1.0


def _wasted(counts: dict[str, int]) -> tuple[float | None, float | None]:
    """(average ms, wasted ms) of one action row; None when no try of it was timed."""
    from app.services.autofill_trace import REJECTED

    if not counts.get("timed"):
        return None, None
    average = counts.get("ms", 0) / counts["timed"]
    return average, sum(counts.get(effect, 0) for effect in REJECTED) * average


def _whole(x: float | None) -> int | str:
    return "—" if x is None else round(x)


def render_wasted(rows: list[Row]) -> list[str]:
    """Family x kind, most wasted ms first: tries, share that was not progress (effect_unknown counts
    as not progress and is shown apart), timed tries, average ms, and ms spent on tries the page rejected."""
    ranked = []
    for parts, counts in rows:
        average, wasted = _wasted(counts)
        tries = counts.get("tries", 0)
        ranked.append((wasted or 0, tries, _pairs(
            family=parts["family"], kind=parts["kind"], tries=tries,
            not_progress=_frac(tries - counts.get("progress", 0), tries),
            unknown=counts.get("effect_unknown", 0), timed=counts.get("timed", 0),
            avg_ms=_whole(average), wasted_ms=_whole(wasted))))
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return [line for *_, line in ranked[:WASTED_SHOWN]] or [NO_DATA]


def render_calibration(rows: list[Row]) -> list[str]:
    """One line per op x engine x by x floor x band x choice, with the counts of its n that were kept,
    left, failed, or followed by a rejected page action."""
    def order(row: Row) -> tuple:
        p = row[0]
        return p["op"], p["engine"], p["by"], _order(p["floor"]), _order(p["band"]), p["choice"]

    return [_pairs(**parts, n=counts.get("n", 0),
                   **{name: _frac(counts.get(name, 0), counts.get("n", 0))
                      for name in ("kept", "left", "failed", "rejected")})
            for parts, counts in sorted(rows, key=order)] or [NO_DATA]


def _first_order(row: Row) -> tuple:
    p = row[0]
    return p["op"], _order(p["floor"]), _order(p["band"]), p["agree"]


def render_second(first: list[Row], second: list[Row]) -> list[str]:
    """`first|`: every step the second opinion decided, per op x floor x band x agreement of the first
    engine, with how often it was kept. `second|`: per op, how often the second opinion was asked or
    decided, and kept when it decided."""
    lines = [_pairs(first=parts["op"], floor=parts["floor"], band=parts["band"], agree=parts["agree"],
                    n=counts.get("n", 0), kept=_frac(counts.get("kept", 0), counts.get("n", 0)),
                    wilson95_lo=f"{wilson95_lo(counts.get('kept', 0), counts.get('n', 0)):.2f}")
             for parts, counts in sorted(first, key=_first_order)]
    lines += [_pairs(second=parts["op"], asked=counts.get("asked", 0), decided=counts.get("decided", 0),
                     decided_kept=_frac(counts.get("decided_kept", 0), counts.get("decided", 0)))
              for parts, counts in sorted(second, key=lambda r: r[0]["op"])]
    return lines or [NO_DATA]


def render_slowest(fields: list[SlowField]) -> list[str]:
    """The fields with the most steps, ties broken by total ms."""
    top = sorted(fields, key=lambda f: (-f[2], -f[3]))[:SLOWEST_SHOWN]
    return [_pairs(host=host, label=_label(label), steps=steps, total_ms=ms, outcome=outcome)
            for host, label, steps, ms, outcome in top] or [NO_DATA]


def _band_evidence(first: list[Row], decision: list[Row]) -> dict[tuple[str, str], dict[str, list[int]]]:
    """{(op, floor): {band: [kept_same, of]}}. `of` is every step the second opinion decided in the band
    (any agreement) plus jev's own answers in it that the second opinion did not decide; `kept_same` is
    the kept count of the decided steps where jev agreed."""
    from app.services.autofill_trace import NONE_PART

    out: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for parts, counts in first:
        if NONE_PART not in (parts["floor"], parts["band"]):
            cell = out[parts["op"], parts["floor"]][parts["band"]]
            cell[1] += counts.get("n", 0)
            cell[0] += counts.get("kept", 0) if parts["agree"] == "same" else 0
    for parts, counts in decision:
        if ((parts["engine"], parts["by"], parts["choice"]) == ("jev", "first", "answer")
                and NONE_PART not in (parts["floor"], parts["band"])):
            out[parts["op"], parts["floor"]][parts["band"]][1] += counts.get("n", 0)
    return out


def _suggestion(op: str, floor: str, cells: dict[str, list[int]]) -> str | None:
    """Walk the bands down from just under the floor while each one qualifies; the lowest is the
    candidate. A missing band, one with too few decisions, or a weak Wilson bound stops the walk."""
    bands = []
    for tenth in range(int(float(floor) * 10 + 1e-9) - 1, -1, -1):
        kept, of = cells.get(str(tenth / 10), (0, 0))
        if of < SUGGEST_MIN_N or wilson95_lo(kept, of) < SUGGEST_MIN_LO:
            break
        bands.append((tenth, kept, of))
    if not bands:
        return None
    kept, of = sum(b[1] for b in bands), sum(b[2] for b in bands)
    return "suggest " + _pairs(
        op=op, floor=f"{float(floor):.2f}", candidate=f"{bands[-1][0] / 10:.2f}",
        bands=",".join(str(t / 10) for t, *_ in reversed(bands)), kept_same=kept, of=of,
        wilson95_lo=f"{wilson95_lo(kept, of):.2f}", note="check_with_the_eval_before_changing")


def render_suggestions(first: list[Row], decision: list[Row]) -> list[str]:
    """Evidence-backed floor suggestions, then the one standing note. A `first|pick` row at the closest
    floor is the second opinion's "closest" pick clearing it, not the match floor jev faced, so that
    group is skipped. Only `pick`: /step's progress floor is also 0.5. MATCH_FLOOR["any"] is 0.5 too,
    so a genuine any-policy pick at 0.5 is skipped as well; conservative and accepted, since
    suggestions are advice."""
    from app.services.autofill_choose import CLOSEST_FLOOR

    evidence = _band_evidence(first, decision)
    found = (_suggestion(op, floor, evidence[op, floor])
             for op, floor in sorted(evidence, key=lambda k: (k[0], _order(k[1])))
             if not (op == "pick" and abs(float(floor) - CLOSEST_FLOOR) < 1e-9))
    lines = [line for line in found if line] or [NO_SUGGESTION if first else NO_DATA]
    return [*lines, SUGGESTION_NOTE]


def render_legend() -> str:
    """What kept and rejected mean, from the key module's own sets."""
    from app.services.autofill_trace import KEPT, REJECTED

    return (f"legend: kept=field ended {'|'.join(sorted(KEPT))} (an outcome proxy, not correctness); "
            f"rejected=next page action {'|'.join(sorted(REJECTED))}; "
            "first=second opinion decided, by agreement with jev")


def render_window(since: datetime | None, runs: list[datetime]) -> str:
    """How far back the counters (all-time since their first row) and the stored runs reach."""
    counters = f"all-time since {since.astimezone(UTC):%Y-%m-%d %H:%MZ}" if since else "none"
    stored = f"last {len(runs)} (oldest {min(runs).astimezone(UTC):%Y-%m-%d})" if runs else "none"
    return f"window: counters={counters}  runs={stored}"


def _counter_rows(session: Session) -> tuple[dict[str, list[Row]], datetime | None]:
    """The stored counters by key family, and when the oldest was first counted. A key this reader
    does not know (an unknown family, a wrong part count, a floor or band that is not a number) is skipped."""
    from sqlalchemy import select

    from app.models.autofill_mechanism_stat import AutofillMechanismStat
    from app.services.autofill_trace import KEY_PARTS, NONE_PART, parse_key

    out: dict[str, list[Row]] = {family: [] for family in KEY_PARTS}
    stats = session.scalars(select(AutofillMechanismStat)).all()
    for stat in stats:
        try:
            family, parts = parse_key(stat.key)
            for name in ("floor", "band"):
                if parts.get(name, NONE_PART) != NONE_PART:
                    float(parts[name])
        except (KeyError, ValueError):
            continue
        out[family].append((parts, stat.counts))
    return out, min((stat.created_at for stat in stats), default=None)


def _stored_runs(session: Session) -> tuple[list[datetime], list[SlowField]]:
    """When each stored run started, and every field with at least one step in the runs that still
    match the schema (an unreadable one is skipped)."""
    from sqlalchemy import select

    from app.models.autofill_run import AutofillRun

    runs = session.scalars(select(AutofillRun)).all()
    fields = []
    for run in runs:
        trace = _trace(run)
        for field in trace.fields if trace else ():
            if field.steps:
                fields.append((trace.host, field.label, len(field.steps), sum(s.ms or 0 for s in field.steps),
                               field.outcome))
    return [run.started_at for run in runs], fields


def run_report(session: Session, args: argparse.Namespace) -> int:
    counters, since = _counter_rows(session)
    started, slow = _stored_runs(session)
    sections = [
        ("Wasted actions", render_wasted(counters["action"])),
        ("Calibration", render_calibration(counters["decision"])),
        ("First engine and second opinion", render_second(counters["first"], counters["second"])),
        ("Slowest fields", render_slowest(slow)),
        ("Suggestions", render_suggestions(counters["first"], counters["decision"])),
    ]
    print(render_window(since, started), render_legend(), sep="\n", end="\n\n")
    print("\n\n".join("\n".join([f"== {title} ==", *lines]) for title, lines in sections))
    return 0


# ---------- subcommands: each is `run(session, args) -> exit code`


def run_last(session: Session, args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.models.autofill_run import AutofillRun

    query = select(AutofillRun).order_by(AutofillRun.started_at.desc(), AutofillRun.created_at.desc())
    if args.host:
        query = query.where(AutofillRun.host == args.host)
    runs = session.scalars(query.limit(args.n)).all()
    if not runs:
        print("no stored run" + (f" for host {args.host}" if args.host else ""), file=sys.stderr)
        return 1
    for run in runs:
        print("\n".join(render_run(run)))
    return 0


def _positive(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _parser() -> argparse.ArgumentParser:
    # --db is accepted before or after the subcommand: SUPPRESS keeps the subparser's copy from
    # overwriting a value given before it. main() reports a missing one.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path, default=argparse.SUPPRESS,
                        help="a COPY of the database (never a file under a checkout's data/ or DATA_DIR)")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)
    p_last = sub.add_parser("last", parents=[common], help="the newest run(s), field by field")
    p_last.add_argument("--host", default=None, help="only runs on this host")
    p_last.add_argument("--n", type=_positive, default=1, help="how many runs, newest first (default 1)")
    p_last.set_defaults(run=run_last)
    sub.add_parser("report", parents=[common], help="counters and stored runs: wasted actions, calibration, "
                   "second-opinion value, slowest fields, floor suggestions").set_defaults(run=run_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    if not hasattr(args, "db"):
        ap.error("--db is required")
    if why := refusal(args.db):
        ap.error(why)
    # Before the app is imported: its settings read these once.
    open_copy(args.db, bind=bind_read_only)

    from app.db import SessionLocal

    with SessionLocal() as session:
        return args.run(session, args)


if __name__ == "__main__":
    sys.exit(main())
