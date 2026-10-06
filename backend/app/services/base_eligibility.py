"""Which base resumes may be scored, recommended or auto-submitted for a job.

The ONE owner of the country rule. A base resume's `countries` anchor says
where it is written for ([] means "anywhere"); a job's `country` says where it
is. A base for another country is not a candidate for that job. Scoring
(`ats_score`), analytics (`explore_gaps`) and the inbox readiness gate all ask
here, so the rule cannot drift between them.

Two escape hatches keep the filter from ever leaving a job with nothing:
`include_other_countries` (the user asked for every base) and the fallback (the
filter would leave no base at all, so every selectable base stays a candidate
and the caller says so).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.job import Job
from app.services import countries
from app.services.base_resume_data import selectable_filter


def country_eligible(base_countries: list[str], job_country: str | None) -> bool:
    """True when a base with these countries may serve a job in `job_country`.

    An empty list (no filter) and an unknown job country both pass."""
    return not base_countries or job_country is None or job_country in base_countries


@dataclass(frozen=True)
class Candidates:
    """The selectable bases for one job, split by the country rule.

    `slugs` and `skipped` keep selectable order (by slug). `fallback` means the
    filter would have left nothing, so `slugs` is every selectable base."""

    slugs: list[str]
    job_country: str | None
    fallback: bool
    skipped: list[str]


def candidates_for_country(
    session: Session, job_country: str | None, *, include_other_countries: bool = False
) -> Candidates:
    """Selectable bases eligible for `job_country`; one query for the countries.

    `job_country` is normalized here (a code in any case, "UK", an English
    name); text naming no country, like "Remote", counts as unknown."""
    code = countries.normalize(job_country)
    rows = session.execute(
        select(BaseResume.slug, BaseResume.countries)
        .where(selectable_filter())
        .order_by(BaseResume.slug)
    ).all()
    everything = [slug for slug, _ in rows]
    if include_other_countries or code is None:
        return Candidates(slugs=everything, job_country=code, fallback=False, skipped=[])

    kept = [slug for slug, base_countries in rows if country_eligible(base_countries or [], code)]
    if not kept:
        # Never strand a job: with a known country and nothing eligible, every
        # selectable base stays on the table and the caller is told.
        return Candidates(slugs=everything, job_country=code, fallback=True, skipped=[])
    skipped = [slug for slug in everything if slug not in set(kept)]
    return Candidates(slugs=kept, job_country=code, fallback=False, skipped=skipped)


def candidates(session: Session, job: Job, **kw) -> Candidates:
    """`candidates_for_country` for a job's own country."""
    return candidates_for_country(session, job.country, **kw)


def is_eligible(session: Session, job: Job, slug: str) -> bool:
    """Whether `slug` may serve `job`: its own countries pass, or the job is in
    fallback. Reads the row whatever its state (an archived base keeps its
    countries). A slug with no row has no anchors, so like `countries == []` it
    is usable anywhere."""
    if candidates(session, job).fallback:
        return True
    row = session.get(BaseResume, slug)
    if row is None:
        return True
    return country_eligible(row.countries or [], countries.normalize(job.country))
