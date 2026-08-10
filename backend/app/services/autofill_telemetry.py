"""Aggregation behind GET /api/autofill/telemetry/summary.

The response shape is FROZEN: the Analytics drill-down reads these exact keys,
and rates computed over a changed denominator are not comparable to any figure
already recorded. Add fields; do not rename or retype them.

The outcome vocabulary is three-way, and the third bucket is the load-bearing
one. SUCCESS_OUTCOMES and FAILURE_OUTCOMES below are the only values that move a
rate; NEUTRAL_OUTCOMES sits in neither numerator nor denominator. That is
deliberate: a field the rules correctly declined to touch is not a failure, and
counting it as one would make a well-behaved rule set look broken.

The neutral bucket is DERIVED from the Literal rather than listed, so adding an
outcome cannot silently leave it unclassified — which is how an outcome the
extension already emitted stayed missing from the contract for a whole round.

There is a second partition, over `kind`: this whole module answers questions
about FORM FIELDS, and the observation table now also carries rows that are not
fields (`NON_FORM_KINDS`). Those are dropped at the top of `summarize_rows`."""

from typing import Any, get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.autofill_field_observation import AutofillFieldObservation
from app.schemas.autofill_telemetry import ObservationOutcome

# Kinds that are not form controls. Every figure below answers a question about
# FORM FIELDS — how well the rules fill each control shape, how much of the
# user's form surface has been seen — so a row that is not a field is dropped
# before any of them is computed.
#
# `signal` is the retired applied-detection watcher's row (stored rows and
# older clients still carry it). Left in, ONE detection event
# per host would add a signature, an observation, possibly a host, a `by_kind`
# entry with no success and no failure, and a novelty mark — and that last one
# feeds `saturated`, which is what tells the user "coverage saturated, you can
# turn capture off". A page event is not coverage of anything.
#
# Listed as the EXCLUSIONS rather than as the allowed set on purpose: a kind
# this module has never heard of (an older or newer extension, a hand-inserted
# row) is a form control until someone says otherwise, which is the behaviour
# every row already had.
NON_FORM_KINDS = frozenset({"signal"})

# filled_normalized is a SUCCESS: the value landed, the site just reformatted
# it. missing_source and policy_blocked are neutral by omission — "the profile
# has no answer" and "we correctly declined to write this" are not rule
# failures, and scoring them as ones would tell the user to go fix rules that
# are working.
SUCCESS_OUTCOMES = frozenset({"filled", "corrected", "filled_normalized"})
FAILURE_OUTCOMES = frozenset(
    {
        "no_rule",
        "combobox_snap_failed",
        "not_stuck",
        "ai_unanswered",
        "ai_no_stick",
    }
)
# Everything the contract declares and neither set claims. Derived on purpose:
# a hand-maintained third list is a copy of a partition that drifts silently.
NEUTRAL_OUTCOMES = (
    frozenset(get_args(ObservationOutcome)) - SUCCESS_OUTCOMES - FAILURE_OUTCOMES
)
NOVELTY_SESSIONS = 10
SATURATION_STREAK = 3
SATURATION_THRESHOLD = 0.10
TOP_FAILURES_LIMIT = 10
RECOMMEND_KEEP = "keep capturing"
RECOMMEND_STOP = (
    "coverage saturated — capture adds little; you can turn it off in the extension panel"
)


def build_summary(db: Session) -> dict[str, Any]:
    rows = db.scalars(select(AutofillFieldObservation)).all()
    return summarize_rows(list(rows))


def summarize_rows(rows: list[AutofillFieldObservation]) -> dict[str, Any]:
    # Before anything is counted, and once — every block below reads `rows`, and
    # filtering per block is how one of them keeps a detection event.
    rows = [row for row in rows if row.kind not in NON_FORM_KINDS]

    totals = {
        "signatures": len(rows),
        "observations": sum(row.seen_count for row in rows),
        "hosts": len({row.host for row in rows}),
    }

    by_kind_acc: dict[str, dict[str, int]] = {}
    for row in rows:
        acc = by_kind_acc.setdefault(row.kind, {"success": 0, "failure": 0})
        for outcome, n in (row.outcomes or {}).items():
            if outcome in SUCCESS_OUTCOMES:
                acc["success"] += n
            elif outcome in FAILURE_OUTCOMES:
                acc["failure"] += n
    by_kind = [
        {
            "kind": kind,
            "success": acc["success"],
            "failure": acc["failure"],
            "success_rate": (
                acc["success"] / (acc["success"] + acc["failure"])
                if acc["success"] + acc["failure"]
                else None
            ),
        }
        for kind, acc in sorted(by_kind_acc.items())
    ]

    failures = []
    for row in rows:
        outcomes = row.outcomes or {}
        total = sum(outcomes.values())
        if not total:
            continue
        dominant = min(outcomes, key=lambda k: (-outcomes[k], k))
        if dominant not in FAILURE_OUTCOMES:
            continue
        failure_share = (
            sum(n for outcome, n in outcomes.items() if outcome in FAILURE_OUTCOMES)
            / total
        )
        failures.append(
            {
                # Stable identity for the web card's row keys — host+label+kind
                # collide across signatures that differ only by option texts.
                "signature_hash": row.signature_hash,
                "label": row.label,
                "kind": row.kind,
                "host": row.host,
                "rule_id": row.rule_id,
                "options_sample": (row.options or [])[:5],
                "seen_count": row.seen_count,
                "outcomes": outcomes,
                "failure_share": failure_share,
                "score": row.seen_count * failure_share,
            }
        )
    failures.sort(key=lambda failure: (-failure["score"], failure["label"]))
    top_failures = failures[:TOP_FAILURES_LIMIT]

    batches: dict[str, list[bool]] = {}
    for row in rows:
        for mark in row.session_marks or []:
            batches.setdefault(mark["at"], []).append(bool(mark.get("new")))
    novelty = [
        {
            "at": at,
            "new": sum(flags),
            "total": len(flags),
            "share": sum(flags) / len(flags),
        }
        for at, flags in sorted(batches.items())
    ][-NOVELTY_SESSIONS:]

    tail = novelty[-SATURATION_STREAK:]
    saturated = len(tail) == SATURATION_STREAK and all(
        point["share"] < SATURATION_THRESHOLD for point in tail
    )

    return {
        "totals": totals,
        "by_kind": by_kind,
        "top_failures": top_failures,
        "novelty": novelty,
        "saturated": saturated,
        "recommendation": RECOMMEND_STOP if saturated else RECOMMEND_KEEP,
    }
