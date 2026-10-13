"""The known-gaps list: write sightings, read the summary Settings and the trace report show.

The summary names no host: Settings shows how many sites, never which ones.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.autofill_widget_gap import AutofillWidgetGap
from app.models.types import utcnow
from app.schemas.autofill_gaps import GapIn

TOP_SHOWN = 10


def _row(db: Session, key: tuple[str, str, str, str]) -> AutofillWidgetGap | None:
    family, host, shape, outcome = key
    return db.scalar(
        select(AutofillWidgetGap).where(
            AutofillWidgetGap.family == family,
            AutofillWidgetGap.host == host,
            AutofillWidgetGap.shape == shape,
            AutofillWidgetGap.outcome == outcome,
        )
    )


def record(db: Session, gaps: list[GapIn]) -> None:
    """Add each sighting to its row's count, creating the row on first sight. Does not commit."""
    # Count within the batch BEFORE touching the session: with autoflush off, two pending inserts
    # for one unique key would both INSERT and collide at flush (SYSTEM.md §12).
    seen = Counter((g.family, g.host, g.shape, g.outcome) for g in gaps)
    now = utcnow()
    for key, n in seen.items():
        row = _row(db, key)
        if row is None:
            # A concurrent request can insert the same key between the SELECT and the flush:
            # insert in a SAVEPOINT and, on the unique violation, add to the winner's row.
            try:
                with db.begin_nested():
                    db.add(AutofillWidgetGap(
                        family=key[0], host=key[1], shape=key[2], outcome=key[3],
                        count=n, first_seen_at=now, last_seen_at=now,
                    ))
                    db.flush()
                continue
            except IntegrityError:
                row = _row(db, key)
        row.count += n
        row.last_seen_at = now


def build_summary(db: Session) -> dict:
    """`kinds`: distinct widget kinds (family + shape); `sites`: distinct hosts; `user_fixed`: the
    kinds you fixed by hand. `top` ranks (family, shape, outcome) by count across hosts, with the
    number of sites each was seen on and no host."""
    rows = db.scalars(select(AutofillWidgetGap)).all()
    kinds = {(r.family, r.shape) for r in rows}
    fixed = {(r.family, r.shape) for r in rows if r.outcome == "user_fixed"}
    grouped: dict[tuple[str, str, str], list[AutofillWidgetGap]] = {}
    for r in rows:
        grouped.setdefault((r.family, r.shape, r.outcome), []).append(r)
    ranked = sorted(
        ((sum(r.count for r in group), key, len({r.host for r in group})) for key, group in grouped.items()),
        key=lambda item: (-item[0], item[1]),
    )
    return {
        "kinds": len(kinds),
        "sites": len({r.host for r in rows}),
        "user_fixed": len(fixed),
        "top": [
            {"family": family, "shape": shape, "outcome": outcome, "count": count, "sites": sites}
            for count, (family, shape, outcome), sites in ranked[:TOP_SHOWN]
        ],
    }
