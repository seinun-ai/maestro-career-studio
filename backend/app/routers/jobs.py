import hashlib
import json
import logging
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.schemas.application import ApplicationRead, ApplicationSummary
from app.schemas.job import (
    JobCreate,
    JobExportRow,
    JobIngest,
    JobPatch,
    JobRead,
    JobSkillRead,
    JobSummary,
    QuickTailorCompare,
    QuickTailorRequest,
    QuickTailorResponse,
)
from app.schemas.job_detail import JobDetail
from app.schemas.job_match import JobMatchResult
from app.schemas.job_search_brief import JobSearchBriefResponse
from app.services import (
    artifacts,
    jd_extraction,
    job_search_brief,
    job_url_match,
    market_settings,
    quick_tailor,
    role_categories,
    tailoring_session,
)
from app.services.skill_normalize import canonicalize_skill_name, coerce_skill_category


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _hash_text(raw_text: str) -> str:
    return hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()


def _hash_extraction(extraction: dict[str, Any]) -> str:
    canonical = json.dumps(extraction, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _disqualifying_for_opt(extraction: dict[str, Any]) -> bool:
    return (
        extraction.get("work_authorization") in {"no_sponsorship", "citizen_or_gc_required"}
        or extraction.get("opt_accepted") == "no"
    )


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _apply_extraction(
    job: Job, extraction: dict[str, Any], session: Session | None = None
) -> None:
    """Map an extraction onto the job's promoted columns — the ONE place this
    ~20-field mapping lives (create and re-extract both go through it).

    `session` is only used to read the selected market for the currency default.
    Both call sites have one in scope and pass it; the default exists so the
    signature stays callable from tests. It must be THREADED rather than opened
    here — this runs inside the caller's transaction, and the settings reader
    lazy-seeds a row on first read, so a nested session would both write and
    deadlock-risk mid-capture.
    """
    location = extraction.get("location_raw") or extraction.get("location")
    job.extracted_json = extraction
    job.title = extraction.get("title")
    job.company = extraction.get("company")
    # Falsy-or-blank → None (not str(0)=="0"): requisition_id is half of the
    # G11 (lower(company), requisition_id) dedup key, so a numeric 0 must not
    # become a storable id. Do not switch this to _str_or_none.
    job.requisition_id = (str(extraction.get("requisition_id") or "").strip()) or None
    # Normalize against the vocabulary so an LLM answering "ML Engineer" or
    # "machine_learning_engineer" lands on one key instead of fragmenting
    # analytics. Unrecognized -> "other"; missing -> "unknown".
    job.role_category = role_categories.normalize(extraction.get("role_category"))
    job.level = extraction.get("level")
    job.employment_type = extraction.get("employment_type")
    job.work_mode = extraction.get("work_mode")
    job.location = location
    job.city = extraction.get("city")
    job.state = extraction.get("state")
    job.country = extraction.get("country")
    job.location_raw = location
    job.salary_min = _decimal_or_none(extraction.get("salary_min"))
    job.salary_max = _decimal_or_none(extraction.get("salary_max"))
    job.salary_period = extraction.get("salary_period")
    job.salary_currency = _salary_currency_for(job, extraction, session)
    job.salary_source_url = _str_or_none(extraction.get("salary_source_url"))
    job.work_authorization = extraction.get("work_authorization")
    job.opt_accepted = extraction.get("opt_accepted")
    job.disqualifying_for_opt = _disqualifying_for_opt(extraction)
    job.years_experience_min = _int_or_none(extraction.get("years_experience_min"))
    job.years_experience_max = _int_or_none(extraction.get("years_experience_max"))
    job.extracted_at = datetime.now(UTC)


def _salary_currency_for(
    job: Job, extraction: dict[str, Any], session: Session | None = None
) -> str | None:
    """ISO code from the posting, else the selected market's currency.

    Never invent a currency for a null salary — absent pay is the normal case
    (~40% of US postings and ~88% of German ones carry none, and an Illinois
    posting may legally just link to a pay page).

    The market setting is the answer when there is one: it is user-chosen and
    visible, whereas HOME_CURRENCY is an env var. Falling back to the env var
    when the market is unset keeps existing deployments working, but the two
    must never both be consulted for the same job — one source per answer.
    """
    currency = _str_or_none(extraction.get("salary_currency"))
    if currency:
        return currency.upper()
    if job.salary_min is None and job.salary_max is None:
        return None
    return market_settings.default_currency_for_capture(session)


def _job_from_extraction(
    raw_text: str,
    source_url: str | None,
    raw_text_hash: str,
    extraction: dict[str, Any],
    source: str = "user",
    session: Session | None = None,
) -> Job:
    job = Job(
        raw_text=raw_text,
        raw_text_hash=raw_text_hash,
        source_url=(source_url or "").strip() or None,
        source=source,
    )
    _apply_extraction(job, extraction, session)
    return job


def _find_existing(
    db: Session,
    source_url: str | None,
    raw_text_hash: str,
    *,
    url_fallback: bool,
) -> Job | None:
    """Dedup lookup: exact raw-text hash first; source_url only when asked.

    The URL fallback exists for the capture path with NO raw text: there the
    hash is of the extraction JSON, which is LLM output and not stable across
    re-captures of the same posting — the URL is the one stable identifier
    that path has. It must NOT apply when real raw text is present: careers
    pages and job boards reuse URLs across different postings, and a hash miss
    there means the text genuinely differs (review finding — a new JD pasted
    from a reused URL would otherwise be silently swallowed by the old job).
    """
    existing = db.scalar(select(Job).where(Job.raw_text_hash == raw_text_hash))
    if existing is not None:
        return existing
    url = (source_url or "").strip()
    if url_fallback and url:
        return db.scalar(
            select(Job)
            .where(Job.source_url == url)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    return None


def _insert_skills(session: Session, job_id: UUID, extraction: dict[str, Any]) -> None:
    # Dedupe by the canonical composite PK before merging. Under this app's
    # autoflush=False sessions (app/db.py, tests/conftest.py), session.merge does
    # NOT collapse two transient instances that canonicalize to the same PK in one
    # flush -- the second merge's existence check runs without flushing the first
    # pending row, so both become INSERTs and trip job_skills_pkey. Verified
    # empirically: with autoflush=False two same-PK merges raise IntegrityError.
    seen: set[tuple[str, str, str]] = set()
    for skill in extraction.get("skills", []):
        name = canonicalize_skill_name(skill["skill_name"])
        category = coerce_skill_category(skill.get("skill_category"))
        level = skill.get("requirement_level") or "mentioned"
        if (name, category, level) in seen:
            continue
        seen.add((name, category, level))
        session.merge(
            JobSkill(
                job_id=job_id,
                skill_name=name,
                skill_category=category,
                requirement_level=level,
            )
        )


def _persist_job(
    db: Session,
    raw_text: str,
    source_url: str | None,
    raw_text_hash: str,
    extraction: dict[str, Any],
    source: str = "user",
    session: Session | None = None,
) -> Job:
    existing = _find_existing(
        db, source_url, raw_text_hash, url_fallback=not raw_text.strip()
    )
    if existing is not None:
        # Transient flag read by JobRead: the caller gets the tracked row back,
        # but the UI must not claim a fresh extraction happened (audit C14).
        existing.already_existed = True
        return existing
    extraction = jd_extraction.apply_work_auth_backstop(raw_text, dict(extraction))
    # G11: the same requisition posted on two boards has a different URL AND
    # different page text, so hash/url dedup misses it. (company,
    # requisition_id) is identity when both are present — return the tracked
    # row instead of minting a twin that could be double-applied.
    company = str(extraction.get("company") or "").strip()
    rid = str(extraction.get("requisition_id") or "").strip()
    if company and rid:
        twin = db.scalar(
            select(Job)
            .where(
                func.lower(Job.company) == company.lower(),
                Job.requisition_id == rid,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if twin is not None:
            twin.already_existed = True
            return twin
    job = _job_from_extraction(
        raw_text, source_url, raw_text_hash, extraction, source=source, session=db
    )
    db.add(job)
    db.flush()
    _insert_skills(db, job.id, extraction)
    db.commit()
    db.refresh(job)
    return job


@router.post("", response_model=JobRead)
def create_job(payload: JobCreate, db: Annotated[Session, Depends(get_db)]):
    raw_text_hash = _hash_text(payload.raw_text)
    # Dedup BEFORE the LLM extraction spend; _persist_job re-checks after it.
    # Hash-only: pasted text that differs is a different posting even at a
    # reused URL.
    existing = _find_existing(db, payload.source_url, raw_text_hash, url_fallback=False)
    if existing is not None:
        existing.already_existed = True
        return existing
    extraction = jd_extraction.extract_jd(payload.raw_text, db)
    return _persist_job(db, payload.raw_text, payload.source_url, raw_text_hash, extraction)


@router.get("", response_model=list[JobSummary])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    without_application: bool = False,
    source_url: str | None = None,
    source: Literal["user", "agent"] | None = Query(default=None),
):
    stmt = select(Job)
    if source:
        stmt = stmt.where(Job.source == source)
    if without_application:
        has_application = (
            select(Application.id).where(Application.job_id == Job.id).correlate(Job)
        )
        stmt = stmt.where(~exists(has_application))
    normalized_url = (source_url or "").strip()
    if normalized_url:
        # Exact match only — the dedupe lookup for external capture agents.
        # (Substring/prefix matching would false-positive across postings that
        # share a careers-site path.) Strip first: every write path stores a
        # stripped source_url, so a trailing-whitespace query would otherwise
        # miss an already-captured job. An all-whitespace value strips to empty
        # and is treated as no filter.
        stmt = stmt.where(Job.source_url == normalized_url)
    stmt = stmt.order_by(Job.created_at.desc()).offset(offset).limit(limit)
    rows = list(db.scalars(stmt))
    # Annotate newest proposal status + id per job (transient attrs consumed by
    # JobSummary — same pattern as already_existed). One query for the whole
    # page; newest-first iteration keeps the first row seen per job.
    if rows:
        from app.models.application_proposal import ApplicationProposal

        newest: dict = {}
        proposal_rows = db.execute(
            select(
                ApplicationProposal.job_id,
                ApplicationProposal.id,
                ApplicationProposal.status,
            )
            .where(ApplicationProposal.job_id.in_([job.id for job in rows]))
            .order_by(ApplicationProposal.created_at.desc())
        ).all()
        for job_id, prop_id, status in proposal_rows:
            newest.setdefault(job_id, (prop_id, status))
        for job in rows:
            hit = newest.get(job.id)
            if hit is None:
                job.proposal_status = None
                job.proposal_id = None
            else:
                job.proposal_id, job.proposal_status = hit
    return rows


@router.get("/search-brief", response_model=JobSearchBriefResponse)
def get_search_brief(db: Annotated[Session, Depends(get_db)]):
    """Composed context brief for an agentic job-search session (profile
    constraints verbatim + warnings, persona, base-resume targets, role mix,
    top skills, build areas, referral crawl targets, 30-day capture ledger).
    Registered before /{job_id} so the literal path wins over UUID parsing."""
    return job_search_brief.build_brief(db)


@router.post("/ingest", response_model=JobRead)
def ingest_job(payload: JobIngest, db: Annotated[Session, Depends(get_db)]):
    extraction = payload.extracted_json.model_dump(mode="json")
    raw_text = (payload.raw_text or "").strip()
    # Dedup on raw_text when provided; otherwise fall back to a hash of the
    # extraction JSON so the NOT NULL/unique raw_text_hash constraint still holds.
    raw_text_hash = _hash_text(raw_text) if raw_text else _hash_extraction(extraction)
    return _persist_job(db, raw_text, payload.source_url, raw_text_hash, extraction, source=payload.source)


@router.get("/export", response_model=list[JobExportRow])
def export_jobs(
    db: Annotated[Session, Depends(get_db)],
    role_category: str | None = None,
    level: str | None = None,
    since: date | None = None,
    skill: str | None = None,
):
    stmt = select(Job)
    if role_category:
        stmt = stmt.where(Job.role_category == role_category)
    if level:
        stmt = stmt.where(Job.level == level)
    if since:
        stmt = stmt.where(Job.created_at >= since)
    if skill:
        stmt = stmt.where(
            Job.id.in_(
                select(JobSkill.job_id).where(JobSkill.skill_name.ilike(f"%{skill}%"))
            )
        )
    jobs = db.scalars(stmt.order_by(Job.created_at.desc())).all()

    skills_by_job: dict = defaultdict(list)
    job_ids = [j.id for j in jobs]
    if job_ids:
        for s in db.scalars(select(JobSkill).where(JobSkill.job_id.in_(job_ids))):
            skills_by_job[s.job_id].append(s)

    rows: list[JobExportRow] = []
    for j in jobs:
        row = JobExportRow.model_validate(j)
        row.skills = [JobSkillRead.model_validate(s) for s in skills_by_job[j.id]]
        rows.append(row)
    return rows


@router.get("/match", response_model=JobMatchResult)
def match_job_by_url(url: str, db: Annotated[Session, Depends(get_db)]):
    """The tracked job the browser extension is currently looking at, if any.

    Registered before /{job_id} so the literal path wins over UUID parsing —
    otherwise "match" is parsed as a job id and every call 422s.

    An empty url is answered with "none" rather than a 422. The endpoint fires
    on navigation, not on user intent, so a momentarily blank tab URL is an
    ordinary event and not a client error worth surfacing.

    Scans in newest-first order and takes the first hit, so overlapping saves
    resolve deterministically to the most recent capture. Overlap is a real
    state, not a theoretical one: job boards reuse a URL across successive
    postings (see _find_existing), so the same source_url can legitimately
    belong to several rows.
    """
    # Projected scan: the loop reads source_url only, and this fires on every
    # SPA route change. Selecting whole Job rows would hydrate raw_text (the
    # full JD) and extracted_json (JSONB) for every candidate, making the
    # payload scale with the size of the JD corpus rather than the job count.
    # The winner is re-fetched whole below. An O(n) Python scan is right at
    # this scale — a SQL LIKE over a raw source_url would be more fragile than
    # the thing it optimizes.
    #
    # is_not(None) narrows the scan only; it is not a safety guard, since
    # is_same_posting returns False for a null or unparseable link.
    stmt = (
        select(Job.id, Job.source_url)
        .where(Job.source_url.is_not(None))
        .order_by(Job.created_at.desc())
    )
    matched_id = next(
        (
            job_id
            for job_id, source_url in db.execute(stmt)
            if job_url_match.is_same_posting(source_url, url)
        ),
        None,
    )
    if matched_id is None:
        return JobMatchResult(match="none")

    job = db.get(Job, matched_id)
    application = db.scalar(
        select(Application)
        .where(Application.job_id == job.id)
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    summary = None
    if application is not None:
        # Same flat job-field join as list_applications: ApplicationSummary
        # carries job_title/job_company/job_location, not a nested job.
        summary = ApplicationSummary.model_validate(application)
        summary.job_title = job.title
        summary.job_company = job.company
        summary.job_location = job.location

    return JobMatchResult(
        match="exact",
        job=JobSummary.model_validate(job),
        application=summary,
    )


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=JobRead)
def patch_job(job_id: UUID, payload: JobPatch, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if payload.source_url is not None:
        job.source_url = payload.source_url.strip() or None
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}/detail", response_model=JobDetail)
def get_job_detail(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    application = db.scalar(
        select(Application)
        .where(Application.job_id == job_id)
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    # Same derived proposal_status / proposal_id as the list endpoint
    # (transient attrs) so the job page can triage and load proposal detail.
    from app.models.application_proposal import ApplicationProposal

    newest_prop = db.execute(
        select(ApplicationProposal.id, ApplicationProposal.status)
        .where(ApplicationProposal.job_id == job_id)
        .order_by(ApplicationProposal.created_at.desc())
        .limit(1)
    ).first()
    if newest_prop is None:
        job.proposal_id = None
        job.proposal_status = None
    else:
        job.proposal_id, job.proposal_status = newest_prop
    return JobDetail(
        job=JobRead.model_validate(job),
        application=ApplicationRead.model_validate(application) if application else None,
    )


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # DB cascades will clear applications, ats_scores,
    # tailoring_sessions, job_skills, qa_entries, but we still need to clean up
    # rendered PDF/tex artifacts for any applications attached to this job —
    # collected now, removed from disk only after the delete commits.
    files: list = []
    for app in db.scalars(select(Application).where(Application.job_id == job_id)):
        files.extend(artifacts.collect_application_files(app))
    db.delete(job)
    db.commit()
    artifacts.remove_files(files)


@router.post("/{job_id}/re-extract", response_model=JobRead)
def re_extract_job(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Capture-path jobs (MCP/extension) may have no raw JD text at all —
    # re-extracting would send an empty prompt to the LLM and destroy the
    # stored extraction (audit C12).
    if not (job.raw_text or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Job has no raw JD text to re-extract from (captured via "
            "pre-extracted ingest); re-ingest it instead.",
        )

    extraction = jd_extraction.extract_jd(job.raw_text, db)
    extraction = jd_extraction.apply_work_auth_backstop(job.raw_text, dict(extraction))
    _apply_extraction(job, extraction, db)

    db.execute(sa_delete(JobSkill).where(JobSkill.job_id == job_id))
    _insert_skills(db, job_id, extraction)
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/quick-tailor", response_model=QuickTailorResponse)
def quick_tailor_job(
    job_id: UUID, payload: QuickTailorRequest, db: Annotated[Session, Depends(get_db)]
):
    """One-shot tailor: create session -> preference-driven auto-resolution ->
    tailor -> render. Health gates apply untouched (409). Zero actionable gaps
    -> 200 with nothing_to_tailor=true, session left open for a custom pass.

    Thin adapter: quick_tailor.run_for_job owns the composition and the
    soft-fail policy; this function only maps typed exceptions to statuses.
    Clause order matters — every mapped exception except InProgressSessionError
    and LookupError subclasses ValueError, so the bare ValueError clause must
    stay last."""
    try:
        outcome = quick_tailor.run_for_job(job_id, payload.base_resume, session=db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except quick_tailor.InProgressSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except tailoring_session.HealthGateBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        tailoring_session.StaleSessionError,
        tailoring_session.SessionNotOpenError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except quick_tailor.SessionCreateInvalidError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    compare = None
    if outcome.compare is not None:
        compare = QuickTailorCompare(
            before=outcome.compare[0], after=outcome.compare[1]
        )
    return QuickTailorResponse(
        application_id=outcome.application_id,
        session_id=outcome.session_id,
        compare=compare,
        applied=outcome.applied,
        pdf_ready=outcome.pdf_ready,
        nothing_to_tailor=outcome.nothing_to_tailor,
        health_warning=outcome.health_warning,
    )
