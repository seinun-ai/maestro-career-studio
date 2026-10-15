"""Compare reasoning models on the Companion's reasoning step (maintainer-run, never in CI, never a test's model).

The reasoning step shows one model a value-free page snapshot and takes 1 to 3 actions back, which the server checks
(services/autofill_reason.check). The fill log keeps each round's snapshot (RunTrace.reasoning[].snapshot, error lines
already stripped of saved answers), so any model can be asked the same question again. This replays them against the
models named on the command line and prints, per model:

    valid=      replies that parsed AND passed the checker with no rejection, out of all snapshots
    parsed=     replies that were JSON in the reply schema (the rest are `model_error` / `bad_reply`)
    ask_user=   responses that end in ask_user: the model's own ask, or the checker's turn of a bad reply into one
    actions     how many of each action type came back
    latency     median / p95 / mean, in ms, as the server measures it
    tokens=     input/output, summed, as the provider reports them
    cost=       the estimate for those tokens, only for a model whose price per million tokens is known (`--price`)
    rejected    the codes the checker turned replies down for

It calls the real models you name: it spends your keys' money, so keep `--limit` small. A snapshot is the page as the step
saw it; "valid" does not say the action was RIGHT, only that the server would have let it through. Read a sample of the notes
and actions before trusting a cheaper model.

Sources of snapshots (exactly one):
    --snapshots FILE   JSON: a list of reasoning requests ({why, round, fields, buttons, errors, tabs, history,
                       excluded}), `{"snapshots": [...]}`, a list of {request: ...} (tests/fixtures/autofill_reason/
                       reason_replies.json), or a list of run traces holding `reasoning` rounds.
    --db COPY          a COPY of the database (never a file under a checkout's data/ or DATA_DIR): the newest stored runs'
                       reasoning rounds. Answer types come from its profile unless --present names them.

Run from backend/, with the model keys in the environment (the same .env the app reads):

    set -a; source <main-checkout>/.env; set +a
    .venv/bin/python -m scripts.eval_reason --db <scratch>/maestro_cs.sqlite3 --limit 12 \\
        --models claude-sonnet-5-5,claude-haiku-5-5,gpt-6-luna --price claude-sonnet-5-5=3,15

Prices are USD per million tokens as `--price model=in,out`; only gpt-6.1-sol's is built in (the 2026-10 freshness
check). A model without one prints tokens and `cost=n/a`.
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.db_copy import bind_read_only, open_copy, refusal

if TYPE_CHECKING:  # the app is imported only after open_copy sets its environment
    from app.models.autofill_run import AutofillRun
    from app.schemas.autofill_reason import ReasonRequest

PRICES: dict[str, tuple[float, float]] = {"gpt-6.1-sol": (2.0, 10.0)}   # USD per million tokens, in and out
DEFAULT_PRESENT = ("personal.first_name", "personal.last_name", "personal.email", "personal.phone", "personal.city",
                   "personal.country", "education.0.school", "education.0.degree", "education.0.discipline",
                   "preferences.how_heard", "preferences.earliest_start_date", "skills")
NOT_PARSED = frozenset({"model_error", "bad_reply"})


class BadSnapshot(ValueError):
    """A snapshot the reasoning request schema refuses: named by its place in the file, never by what it holds."""


@dataclass
class ModelStats:
    model: str
    n: int = 0
    parsed: int = 0
    valid: int = 0
    asked: int = 0
    actions: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)
    latencies: list[int] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    notes: list[str] = field(default_factory=list)


# ---------- snapshots in


def _request(item: Any, place: str) -> "ReasonRequest":
    from pydantic import ValidationError

    from app.schemas.autofill_reason import ReasonRequest

    try:
        return ReasonRequest.model_validate(item)
    except ValidationError as e:
        loc = ".".join(str(part) for part in e.errors(include_input=False)[0]["loc"])
        raise BadSnapshot(f"{place} is not a reasoning request (first problem at {loc or '<root>'})") from None


def _rounds(trace: dict) -> list[dict]:
    """The requests a stored trace's rounds make: the ones that kept the snapshot the model was shown."""
    return [{"why": r["why"], "round": r["round"], **r["snapshot"]} for r in trace.get("reasoning") or []
            if isinstance(r, dict) and r.get("snapshot") is not None]


def requests_from_json(data: Any) -> "list[ReasonRequest]":
    items = data.get("snapshots", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise BadSnapshot("the file is not a list of snapshots")
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict) and "reasoning" in item:
            out.extend(_rounds(item))
        else:
            out.append(item["request"] if isinstance(item, dict) and "request" in item else item)
    return [_request(item, f"snapshot {i}") for i, item in enumerate(out, 1)]


def requests_from_runs(runs: "list[AutofillRun]") -> "list[ReasonRequest]":
    return requests_from_json([run.trace for run in runs if isinstance(run.trace, dict)])


# ---------- one model over every snapshot


def evaluate(requests: "list[ReasonRequest]", model: str, *, present: list[str], level: str) -> ModelStats:
    """`model` asked every request, each answer judged by the server's own checker (`autofill_reason.reason`). The profile is
    stood in for by `present`: answer types by NAME, no value (a saved answer's value is not in a stored snapshot)."""
    from app.services import autofill_catalog, autofill_reason, llm

    facts = {name: autofill_catalog.make_fact(name, "saved") for name in present}
    stats = ModelStats(model)
    real = llm._call_model

    def tap(*args: Any, **kwargs: Any) -> Any:
        text, usage = real(*args, **kwargs)
        stats.input_tokens += (usage or {}).get("input", 0)
        stats.output_tokens += (usage or {}).get("output", 0)
        return text, usage

    llm._call_model = tap
    try:
        for request in requests:
            reply = autofill_reason.reason(request, facts, level, None, model=model)
            stats.n += 1
            stats.latencies.append(reply.ms)
            stats.parsed += not NOT_PARSED & set(reply.rejected)
            stats.valid += not reply.rejected
            stats.asked += reply.actions[0].type == "ask_user"
            stats.actions.update(a.type for a in reply.actions)
            stats.rejected.update(reply.rejected)
            stats.notes.append(reply.note)
    finally:
        llm._call_model = real
    return stats


# ---------- the report


def cost(stats: ModelStats, prices: dict[str, tuple[float, float]]) -> float | None:
    if stats.model not in prices:
        return None
    price_in, price_out = prices[stats.model]
    return (stats.input_tokens * price_in + stats.output_tokens * price_out) / 1_000_000


def _frac(part: int, whole: int) -> str:
    return f"{part}/{whole}({100 * part / whole:.0f}%)" if whole else f"{part}/{whole}(—)"


def _percentile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))] if ordered else 0


def render_row(stats: ModelStats, prices: dict[str, tuple[float, float]]) -> str:
    spent = cost(stats, prices)
    lat = stats.latencies
    parts = [
        stats.model,
        f"valid={_frac(stats.valid, stats.n)}", f"parsed={_frac(stats.parsed, stats.n)}",
        f"ask_user={_frac(stats.asked, stats.n)}",
        f"latency={int(statistics.median(lat)) if lat else 0}/{_percentile(lat, 0.95)}/{int(statistics.fmean(lat)) if lat else 0}ms",
        f"tokens={stats.input_tokens}/{stats.output_tokens}",
        f"cost=${spent:.4f}" if spent is not None else "cost=n/a",
    ]
    if stats.actions:
        parts.append("actions " + " ".join(f"{k}={v}" for k, v in sorted(stats.actions.items())))
    if stats.rejected:
        parts.append("rejected " + " ".join(f"{k}={v}" for k, v in sorted(stats.rejected.items())))
    return "  ".join(parts)


def render(stats: list[ModelStats], prices: dict[str, tuple[float, float]] | None = None) -> str:
    prices = {**PRICES, **(prices or {})}
    head = ("== reasoning models, same snapshots ==\n"
            "legend: valid = parsed and passed the checker; ask_user = response ends in ask_user (own ask or the "
            "checker's); latency = median/p95/mean; tokens = in/out; cost = estimate at the price given")
    return "\n".join([head, *(render_row(one, prices) for one in stats)])


# ---------- command line


def _price(text: str) -> tuple[str, tuple[float, float]]:
    try:
        model, rest = text.split("=", 1)
        price_in, price_out = (float(part) for part in rest.split(","))
        return model, (price_in, price_out)
    except ValueError:
        raise argparse.ArgumentTypeError("use --price model=in,out (USD per million tokens)") from None


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--models", required=True, help="comma-separated model ids, e.g. claude-sonnet-5-5,claude-haiku-5-5,gpt-6-luna")
    ap.add_argument("--snapshots", type=Path, help="a JSON file of snapshots (see the module doc)")
    ap.add_argument("--db", type=Path, help="a COPY of the database; its stored reasoning rounds are replayed")
    ap.add_argument("--present", help="comma-separated answer types the profile holds (default: the --db profile, else a "
                    "typical set)")
    ap.add_argument("--level", choices=("facts", "history", "queued"), default="history", help="the Screening answers level")
    ap.add_argument("--limit", type=int, default=0, help="replay only the newest N snapshots (0: all)")
    ap.add_argument("--price", action="append", type=_price, default=[], help="model=in,out USD per million tokens (repeatable)")
    ap.add_argument("--out", type=Path, help="also write the numbers as JSON")
    return ap


def _stored_requests(session: Any, limit: int) -> "list[ReasonRequest]":
    from sqlalchemy import select

    from app.models.autofill_run import AutofillRun

    runs = session.scalars(select(AutofillRun).order_by(AutofillRun.started_at.desc())).all()
    found = requests_from_runs([run for run in runs if (run.trace or {}).get("reasoning")])
    return found[:limit] if limit else found


def _profile_answer_types(session: Any) -> list[str]:
    from app.services import autofill_catalog, autofill_profile, autofill_reason, eeo_consent

    # PEEKED, as the fill evaluation does: get_profile / get_consent lazily seed a row, and the copy is read-only.
    profile = eeo_consent.withhold_unconsented(autofill_profile.peek_profile(session),
                                               eeo_consent.peek_consent(session).model_dump(mode="json"))
    return autofill_reason.present_slots(autofill_catalog.build(profile, [], []))


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    if bool(args.snapshots) == bool(args.db):
        ap.error("give exactly one of --snapshots and --db")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        ap.error("--models names no model")
    present = [p.strip() for p in args.present.split(",") if p.strip()] if args.present else None
    session = None
    try:
        if args.db:
            if why := refusal(args.db):
                ap.error(why)
            open_copy(args.db, bind=bind_read_only)   # before the app is imported: its settings read these once
            from app.db import SessionLocal

            session = SessionLocal()
            requests = _stored_requests(session, args.limit)
            present = present if present is not None else _profile_answer_types(session)
        else:
            requests = requests_from_json(json.loads(args.snapshots.read_text(encoding="utf-8")))
            if args.limit:
                requests = requests[-args.limit:]
            present = present if present is not None else list(DEFAULT_PRESENT)
    except (BadSnapshot, OSError, json.JSONDecodeError) as e:
        ap.error(str(e))
    finally:
        if session is not None:
            session.close()
    if not requests:
        ap.error("no snapshot to replay (the fill log keeps one per reasoning round, when it is on)")
    stats = [evaluate(requests, model, present=present, level=args.level) for model in models]
    print(render(stats, dict(args.price)))
    if args.out:
        args.out.write_text(json.dumps({s.model: {
            "n": s.n, "parsed": s.parsed, "valid": s.valid, "asked": s.asked, "actions": dict(s.actions),
            "rejected": dict(s.rejected), "latencies_ms": s.latencies, "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens, "notes": s.notes} for s in stats}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
