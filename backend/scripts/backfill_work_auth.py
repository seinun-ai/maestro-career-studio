"""Backfill `work_authorization` and `disqualifying_for_opt` on existing jobs.

Re-applies the regex work-auth backstop (jd_extraction.apply_work_auth_backstop)
to rows whose `work_authorization` is still 'unstated' but which have a non-empty
`raw_text`, and recomputes `disqualifying_for_opt` for every row from the final
auth + opt_accepted. No LLM calls — pure regex/derivation. Re-ingest dedups on
raw_text_hash, so this script is the only way to repair stored rows.

Usage:
    python -m scripts.backfill_work_auth            # process every row
    python -m scripts.backfill_work_auth --dry-run  # report, no writes
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.models.job import Job
from app.services.jd_extraction import apply_work_auth_backstop


def compute_updates(
    work_authorization: str | None,
    opt_accepted: str | None,
    raw_text: str | None,
) -> tuple[str | None, bool]:
    """Return the (possibly backstopped) work_authorization and the derived
    disqualifying_for_opt flag for a single row. Pure; no DB access.
    """
    extraction = {
        "work_authorization": work_authorization or "unstated",
        "opt_accepted": opt_accepted,
    }
    apply_work_auth_backstop(raw_text, extraction)
    final_auth = extraction["work_authorization"]
    disqualifying = (
        final_auth in {"no_sponsorship", "citizen_or_gc_required"}
        or opt_accepted == "no"
    )
    return final_auth, disqualifying


def _candidates_query():
    # Touch any row that might change: an unstated+raw_text row (backstop may
    # flip it) or any row at all (disqualifying flag may need (re)computing).
    # Selecting everything is fine — the dataset is small and writes are gated.
    return select(Job).order_by(Job.created_at.asc())


def run(dry_run: bool) -> int:
    changed = 0
    with SessionLocal() as session:  # type: Session
        jobs = list(session.scalars(_candidates_query()))
        print(f"Scanning {len(jobs)} job(s).")
        for job in jobs:
            new_auth, new_disq = compute_updates(
                job.work_authorization, job.opt_accepted, job.raw_text
            )
            if new_auth == job.work_authorization and new_disq == job.disqualifying_for_opt:
                continue
            label = f"{job.id}  {(job.company or '—')[:30]:<30}  {(job.title or '—')[:40]}"
            print(
                f"  {'[dry-run] ' if dry_run else ''}{label}  "
                f"auth {job.work_authorization!r}->{new_auth!r}  disq->{new_disq}"
            )
            if not dry_run:
                job.work_authorization = new_auth
                job.disqualifying_for_opt = new_disq
            changed += 1
        if not dry_run:
            session.commit()
    print(f"\n{'Would change' if dry_run else 'Changed'} {changed} row(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would change without writing.",
    )
    args = parser.parse_args(argv)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
