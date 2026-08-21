"""Score every active base resume against every stored job; print a ranking table.

Usage (from backend/, dev DB running):
    DATABASE_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs python scripts/ats_snapshot.py

For a machine-readable before/after comparison, use scripts/ats_calibration.py.
"""
from sqlalchemy import select

from app.db import SessionLocal
from app.models.job import Job
from app.services.ats import score_resume
from app.services.base_resume_data import active_base_resume_slugs, load_base_resume


def main() -> None:
    with SessionLocal() as session:
        jobs = list(session.scalars(select(Job).where(Job.extracted_json.isnot(None))))
        slugs = active_base_resume_slugs(session)
        for job in jobs:
            print(f"\n=== {job.title} @ {job.company} ({job.id}) ===")
            scored = []
            for slug in slugs:
                try:
                    resume = load_base_resume(slug, session)
                    result = score_resume(resume, job.extracted_json)
                    scored.append((result.composite, slug, result))
                except ValueError as exc:
                    print(f"  {slug}: SKIP ({exc})")
            for composite, slug, result in sorted(scored, reverse=True):
                subs = " ".join(f"{k}={v:.2f}" for k, v in result.subscores.items())
                print(f"  {composite:5.1f}  {slug:20s} {subs}  warnings={len(result.gate_warnings)}")


if __name__ == "__main__":
    main()
