import hashlib
import json
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete as sa_delete
from sqlalchemy import exists, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.companion_origin import is_companion
from app.db import begin_write, get_db
from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.tailoring_session import TailoringSession
from app.schemas.application import ApplicationRead, ApplicationSummary
from app.schemas.job import (
    JobCorrection,
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
from app.schemas.job_extraction import JobExtraction
from app.schemas.job_match import JobMatchResult
from app.schemas.job_search_brief import JobSearchBriefResponse
from app.services import (
    application_writes,
    artifacts,
    ats_score,
    autofill_job,
    base_eligibility,
    base_resume_data,
    board_visits,
    countries,
    filled_answers,
    jd_extraction,
    job_search_brief,
    job_url_match,
    knockout,
    market_settings,
    quick_tailor,
    role_categories,
    stage,
    tailoring_session,
)
from app.services.skill_normalize import canonicalize_skill_name, coerce_skill_category
from app.services.sync import hooks as sync_hooks
from app.services.sync import ownership as sync_ownership
from app.services.sync import requests as sync_requests
from app.services.sync import status as sync_status


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
    job.country_code = countries.for_job(job.country, location)
    job.location_raw = location
    job.salary_min = _decimal_or_none(extraction.get("salary_min"))
    job.salary_max = _decimal_or_none(extraction.get("salary_max"))
    job.salary_period = extraction.get("salary_period")
    job.salary_currency, job.salary_currency_assumed = _salary_currency_for(job, extraction, session)
    job.salary_source_url = _str_or_none(extraction.get("salary_source_url"))
    job.work_authorization = extraction.get("work_authorization")
    job.opt_accepted = extraction.get("opt_accepted")
    job.disqualifying_for_opt = _disqualifying_for_opt(extraction)
    job.years_experience_min = _int_or_none(extraction.get("years_experience_min"))
    job.years_experience_max = _int_or_none(extraction.get("years_experience_max"))
    job.extracted_at = datetime.now(UTC)


def _salary_currency_for(
    job: Job, extraction: dict[str, Any], session: Session | None = None
) -> tuple[str | None, bool]:
    """(ISO code, assumed): the posting's own currency, else the job's country's, else the home
    currency. The last two are assumptions and say so; a bare "$" is no currency of its own
    (`JobExtraction.normalize_salary_currency`), so a Toronto job's "$" reads as CAD.

    Never invent a currency for a null salary — absent pay is the normal case
    (~40% of US postings and ~88% of German ones carry none, and an Illinois
    posting may legally just link to a pay page).

    The assumed one is `market_settings.default_currency_for_capture`: the job's country's
    currency, else where the user lives (the home market when chosen, else HOME_CURRENCY), one
    source per answer. `job.country_code` must be set first.
    """
    currency = _str_or_none(extraction.get("salary_currency"))
    if currency:
        return currency.upper(), False
    if job.salary_min is None and job.salary_max is None:
        return None, False
    return market_settings.default_currency_for_capture(session, job.country_code), True


def _job_from_extraction(
    raw_text: str,
    source_url: str | None,
    raw_text_hash: str,
    extraction: dict[str, Any],
    source: str = "user",
    session: Session | None = None,
    apply_url: str | None = None,
    referrer_board: str | None = None,
) -> Job:
    job = Job(
        raw_text=raw_text,
        raw_text_hash=raw_text_hash,
        source_url=(source_url or "").strip() or None,
        apply_url=apply_url,
        referrer_board=referrer_board,
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
        # Posting equality, not string equality (SYSTEM.md §4, Job): a
        # re-capture arriving through a referral link (?gh_src=, ?utm_*) or
        # from the posting's /apply sub-path names the job that is already
        # captured, and exact matching was how the library filled with
        # duplicates of the same role. Same projected scan and the same
        # directional containment as GET /api/jobs/match below.
        stmt = (
            select(Job.id, Job.source_url)
            .where(Job.source_url.is_not(None))
            .order_by(Job.created_at.desc())
        )
        matched_id = next(
            (
                job_id
                for job_id, stored_url in db.execute(stmt)
                if job_url_match.is_same_posting(stored_url, url)
            ),
            None,
        )
        return db.get(Job, matched_id) if matched_id is not None else None
    return None


def _skill_keys(extraction: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The extraction's skill rows as canonical (name, category, level) keys, deduplicated."""
    # Dedupe by the canonical composite PK before merging. Under this app's
    # autoflush=False sessions (app/db.py, tests/conftest.py), session.merge does
    # NOT collapse two transient instances that canonicalize to the same PK in one
    # flush -- the second merge's existence check runs without flushing the first
    # pending row, so both become INSERTs and trip job_skills_pkey. Verified
    # empirically: with autoflush=False two same-PK merges raise IntegrityError.
    return list(dict.fromkeys(
        (
            canonicalize_skill_name(skill["skill_name"]),
            coerce_skill_category(skill.get("skill_category")),
            skill.get("requirement_level") or "mentioned",
        )
        for skill in extraction.get("skills", [])
    ))


def _insert_skills(session: Session, job_id: UUID, extraction: dict[str, Any]) -> None:
    for name, category, level in _skill_keys(extraction):
        session.merge(
            JobSkill(
                job_id=job_id,
                skill_name=name,
                skill_category=category,
                requirement_level=level,
            )
        )


def _replace_extraction(db: Session, job: Job, extraction: dict[str, Any]) -> None:
    """A saved job takes a new extraction: the promoted columns and the skill rows a new capture
    writes. Refresh details (re-extract) and a corrected capture share it; the caller commits."""
    _apply_extraction(job, extraction, db)
    sync_hooks.touch_job(db, job.id)
    db.execute(sa_delete(JobSkill).where(JobSkill.job_id == job.id))
    _insert_skills(db, job.id, extraction)


# Read back, never compared: the extraction itself (its parts are compared) and when it was read.
_UNCOMPARED = frozenset({"extracted_json", "extracted_at"})


def _stored_fields(job: Job) -> dict[str, Any]:
    return {
        attr.key: getattr(job, attr.key)
        for attr in sa_inspect(Job).column_attrs
        if attr.key not in _UNCOMPARED
    }


def _changed_lists(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """The extraction's own fields with no column (responsibilities, qualifications) that changed;
    an empty list and a missing one are the same."""
    columns = {attr.key for attr in sa_inspect(Job).column_attrs}
    return [
        key
        for key in JobExtraction.model_fields
        if key not in columns and key != "skills" and (old.get(key) or None) != (new.get(key) or None)
    ]


def _clear_scores(db: Session, job_id: UUID) -> int:
    """Delete the job's saved match scores (a Core write, so the job is touched for sync)."""
    sync_hooks.touch_job(db, job_id)
    return db.execute(sa_delete(AtsScore).where(AtsScore.job_id == job_id)).rowcount


def _left_alone(db: Session, job_id: UUID) -> dict[str, list[UUID]]:
    """What a correction names and never rewrites: the job's applications holding a tailored
    resume, its open gap analyses and its proposals holding a stored fit."""
    from app.models.application_proposal import ApplicationProposal

    applications = db.execute(
        select(Application.id, Application.customized_json)
        .where(Application.job_id == job_id)
        .order_by(Application.created_at)
    ).all()
    sessions = db.scalars(
        select(TailoringSession.id)
        .where(TailoringSession.job_id == job_id, TailoringSession.status == "open")
        .order_by(TailoringSession.created_at)
    )
    proposals = db.execute(
        select(ApplicationProposal.id, ApplicationProposal.fit_json)
        .where(ApplicationProposal.job_id == job_id)
        .order_by(ApplicationProposal.created_at)
    ).all()
    # Truthiness, not IS NOT NULL: a cleared JSON column is stored as JSON null (services/stage.py
    # reads a draft so).
    return {
        "tailored_applications": [app_id for app_id, draft in applications if draft],
        "open_sessions": list(sessions),
        "proposals_fit_stale": [proposal_id for proposal_id, fit in proposals if fit],
    }


def _scored_bases(db: Session, job_id: UUID) -> list[str]:
    """The bases the job holds a match score for, read before a correction deletes them."""
    return list(db.scalars(
        select(AtsScore.target_id)
        .where(AtsScore.job_id == job_id, AtsScore.target_type == "base_resume", AtsScore.phase == "base")
        .order_by(AtsScore.target_id)
    ))


def _rescore(db: Session, job: Job, scored: list[str], tailored: list[UUID]) -> list[str]:
    """Score a corrected job again after its commit: the bases as a new capture scores them, then
    every other base in `scored` that is still there (archived, or marked for another country since:
    an application on it keeps its Match), then each tailored resume, each in a commit of its own.
    Deterministic, no AI. A failure rolls back only that score and is named ("bases" or the
    application id) for score_ats to compute later."""
    failed = [] if _score_new_job(db, job) else ["bases"]
    if not (job.extracted_json or {}).get("skills"):
        return failed  # nothing to score against, as for the bases (`_scorable_now`)
    offered = set(base_eligibility.candidates(db, job).slugs)
    present = set(base_resume_data.active_base_resume_slugs(db))
    for slug in scored:
        if slug in offered or slug not in present or not base_resume_data.base_resume_path(slug).exists():
            continue
        try:
            ats_score.score_target(job.id, "base_resume", slug, phase="base", session=db)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Rescoring base %s after a job correction failed", slug, exc_info=True)
            failed += [] if "bases" in failed else ["bases"]
    for application_id in tailored:
        try:
            ats_score.score_target(job.id, "application", str(application_id), phase="tailored", session=db)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Rescoring application %s after a job correction failed", application_id,
                           exc_info=True)
            failed.append(str(application_id))
    return failed


def _correct_job(
    db: Session, job: Job, raw_text: str, extraction: dict[str, Any], apply_url: str | None
) -> Job:
    """`update` on a saved posting: this extraction replaces the job's fields and skill rows through
    the mapping a capture uses, and a given apply link replaces the stored one; the id, status,
    applications, proposals, source and raw text stay. A job another copy owns is refused before
    any write.

    When `changed` names anything scoring reads (every field but the apply link), the job's match
    scores of both phases are deleted, since a base and a tailored score must read the same job
    text, and after the commit `_rescore` scores the bases (every one scored before and still
    there) and each tailored resume again; a failed rescore never undoes the correction. Deleting a base score clears an open gap
    analysis's link to it (ON DELETE SET NULL) and leaves the analysis to read as out of date. A
    tailored resume, an open gap analysis and a proposal's stored fit are named in `correction`,
    never rewritten."""
    sync_hooks.require_owned(db, job.id)
    extraction = jd_extraction.apply_work_auth_backstop(raw_text or job.raw_text, dict(extraction))
    old_extraction = job.extracted_json or {}
    old_skills = {
        tuple(row)
        for row in db.execute(
            select(JobSkill.skill_name, JobSkill.skill_category, JobSkill.requirement_level)
            .where(JobSkill.job_id == job.id)
        )
    }
    before = _stored_fields(job)
    _replace_extraction(db, job, extraction)
    if apply_url:
        job.apply_url = apply_url
    after = _stored_fields(job)
    changed = [key for key in before if before[key] != after[key]]
    changed += _changed_lists(old_extraction, extraction)
    if set(_skill_keys(extraction)) != old_skills:
        changed.append("skills")
    rescore = any(field != "apply_url" for field in changed)  # scoring never reads the apply link
    scored = _scored_bases(db, job.id) if rescore else []
    cleared = _clear_scores(db, job.id) if rescore else 0
    named = _left_alone(db, job.id)
    if not rescore:
        named["proposals_fit_stale"] = []
    db.commit()
    failed = _rescore(db, job, scored, named["tailored_applications"]) if rescore else []
    db.refresh(job)
    job.already_existed = True
    job.correction = JobCorrection(
        changed=changed,
        scores_cleared=cleared,
        rescored=rescore and not failed,
        rescore_failed=failed,
        **named,
    )
    return _with_newest_proposal(db, job)


def _fill_apply_url(db: Session, job: Job, apply_url: str | None) -> None:
    """A job saved again gains the apply link it lacked; a link it already has is never replaced.
    A job another copy owns is left alone: writing it would raise NotOwnedHere and turn a plain
    dedup hit into a 409, and its owner records the link."""
    if apply_url and job.apply_url is None and sync_hooks.owned_here(db, job.id):
        job.apply_url = apply_url
        db.commit()
        db.refresh(job)


def _persist_job(
    db: Session,
    raw_text: str,
    source_url: str | None,
    raw_text_hash: str,
    extraction: dict[str, Any],
    source: str = "user",
    session: Session | None = None,
    apply_url: str | None = None,
    referrer_board: str | None = None,
    update: bool = False,
) -> Job:
    """Save a job, or return the tracked row on a dedup hit (with `update`, corrected by this
    extraction: `_correct_job`). Only a NEW job is scored, after its own commit."""
    existing = _find_existing(
        db, source_url, raw_text_hash, url_fallback=not raw_text.strip()
    )
    if existing is not None and update:
        return _correct_job(db, existing, raw_text, extraction, apply_url)
    if existing is not None:
        _fill_apply_url(db, existing, apply_url)
        # Transient flag read by JobRead: the caller gets the tracked row back,
        # but the UI must not claim a fresh extraction happened (audit C14).
        existing.already_existed = True
        return _with_ownership(db, existing)
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
        if twin is not None and update:
            return _correct_job(db, twin, raw_text, extraction, apply_url)
        if twin is not None:
            _fill_apply_url(db, twin, apply_url)
            twin.already_existed = True
            return _with_ownership(db, twin)
    job = _job_from_extraction(
        raw_text, source_url, raw_text_hash, extraction, source=source, session=db,
        apply_url=apply_url, referrer_board=referrer_board,
    )
    db.add(job)
    db.flush()
    _insert_skills(db, job.id, extraction)
    db.commit()
    db.refresh(job)
    _score_new_job(db, job)
    return _with_ownership(db, job)


def _scorable_now(db: Session, job: Job) -> bool:
    """The two expected no-score cases, checked before the engine runs: no base resume yet
    (the job page's Resume and gaps step scores on its first visit once there is one) and no
    extracted skills."""
    if not base_eligibility.candidates(db, job).slugs:
        return False
    if not (job.extracted_json or {}).get("skills"):
        logger.info("Job %s saved with no extracted skills; not scored", job.id)
        return False
    return True


def _score_new_job(db: Session, job: Job) -> bool:
    """Score a just-saved (or just-corrected) job against every selectable base, inline, so the
    Jobs list's Match column is filled from the save on. All bases or none: a real fault (a
    corrupt base file) rolls back only the scores, never the already-committed job, logs a
    warning and returns False; the expected no-score cases return True."""
    if not _scorable_now(db, job):
        return True
    scored = True
    try:
        ats_score.score_all_bases(job.id, session=db)
        db.commit()
    except Exception:
        db.rollback()
        scored = False
        logger.warning("Scoring job %s at save failed; it saves unscored", job.id, exc_info=True)
    # Both commit and rollback expire the job the response serializes.
    db.refresh(job)
    return scored


@router.post("", response_model=JobRead)
def create_job(payload: JobCreate, db: Annotated[Session, Depends(get_db)]):
    raw_text_hash = _hash_text(payload.raw_text)
    # Dedup BEFORE the LLM extraction spend; _persist_job re-checks after it.
    # Hash-only: pasted text that differs is a different posting even at a
    # reused URL.
    existing = _find_existing(db, payload.source_url, raw_text_hash, url_fallback=False)
    if existing is not None:
        _fill_apply_url(db, existing, payload.apply_url)
        existing.already_existed = True
        return _with_ownership(db, existing)
    extraction = jd_extraction.extract_jd(payload.raw_text, db)
    # The extension saves from the page the user is on. On the employer's own page (not a board's) the board page
    # opened just before it is where the job was found (services/board_visits).
    referrer = None if autofill_job.board_of_url(payload.source_url) else board_visits.recent()
    return _persist_job(
        db, payload.raw_text, payload.source_url, raw_text_hash, extraction, apply_url=payload.apply_url,
        referrer_board=referrer,
    )


def _newest_proposal_columns():
    """The newest-proposal fields the job projections carry, in the order
    _stamp_newest_proposal unpacks them."""
    from app.models.application_proposal import ApplicationProposal

    return (ApplicationProposal.id, ApplicationProposal.status, ApplicationProposal.proposed_by)


def _stamp_newest_proposal(job: Job, newest) -> None:
    """Transient attrs read by JobRead/JobSummary (same pattern as
    already_existed): the newest proposal's id, status and filer, or None."""
    job.proposal_id, job.proposal_status, job.proposal_proposed_by = newest or (None, None, None)


def _with_ownership(db: Session, job: Job) -> Job:
    sync_ownership.stamp(db, [job])
    return job


def _with_newest_proposal(db: Session, job: Job) -> Job:
    """One job, stamped as the list stamps each row. Every single-job JobRead goes through here:
    without it the fields read null while the list and `/detail` named the proposal."""
    from app.models.application_proposal import ApplicationProposal

    newest = db.execute(
        select(*_newest_proposal_columns())
        .where(ApplicationProposal.job_id == job.id)
        .order_by(ApplicationProposal.created_at.desc())
        .limit(1)
    ).first()
    _stamp_newest_proposal(job, newest)
    sync_ownership.stamp(db, [job])
    return job


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
    # Annotate newest proposal id, status + filer per job (transient attrs consumed by
    # JobSummary — same pattern as already_existed). One query for the whole
    # page; newest-first iteration keeps the first row seen per job.
    if rows:
        from app.models.application_proposal import ApplicationProposal

        newest: dict = {}
        proposal_rows = db.execute(
            select(ApplicationProposal.job_id, *_newest_proposal_columns())
            .where(ApplicationProposal.job_id.in_([job.id for job in rows]))
            .order_by(ApplicationProposal.created_at.desc())
        ).all()
        for job_id, *fields in proposal_rows:
            newest.setdefault(job_id, fields)
        best = ats_score.best_base_scores(db, [job.id for job in rows])
        stages = stage.for_job_rows(db, rows, scored=set(best))
        for job in rows:
            _stamp_newest_proposal(job, newest.get(job.id))
            job.best_ats_score = best.get(job.id)
            stage.stamp(job, stages[job.id])
    sync_ownership.stamp(db, rows)
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
    return _persist_job(
        db, raw_text, payload.source_url, raw_text_hash, extraction, source=payload.source,
        apply_url=payload.apply_url, update=payload.update,
    )


@router.get("/export", response_model=list[JobExportRow])
def export_jobs(
    db: Annotated[Session, Depends(get_db)],
    role_category: str | None = None,
    level: str | None = None,
    since: date | None = None,
    skill: str | None = None,
    # Paging is opt-in: no limit is the whole export, as before. The MCP tool
    # always passes one (a full library is ~1.7M chars).
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = select(Job)
    if role_category:
        stmt = stmt.where(Job.role_category == role_category)
    if level:
        stmt = stmt.where(Job.level == level)
    if since:
        # created_at is UTCDateTime, which refuses a bare date at bind time.
        # Bind the instant Postgres used to imply for a date: midnight UTC.
        stmt = stmt.where(Job.created_at >= datetime.combine(since, time.min, tzinfo=UTC))
    if skill:
        stmt = stmt.where(
            Job.id.in_(
                select(JobSkill.job_id).where(JobSkill.skill_name.ilike(f"%{skill}%"))
            )
        )
    # id is a deterministic tiebreak so pages never overlap or skip.
    stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    jobs = db.scalars(stmt).all()
    sync_ownership.stamp(db, jobs)

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
def match_job_by_url(url: str, request: Request, db: Annotated[Session, Depends(get_db)]):
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
    if is_companion(request):   # the user's own browsing, not an agent's lookup
        board_visits.seen(url)
    # Projected scan: the loop reads source_url only, and this fires on every
    # SPA route change. Selecting whole Job rows would hydrate raw_text (the
    # full JD) and extracted_json (JSONB) for every candidate, making the
    # payload scale with the size of the JD corpus rather than the job count.
    # The winner is re-fetched whole below. An O(n) Python scan is right at
    # this scale — a SQL LIKE over a raw source_url would be more fragile than
    # the thing it optimizes.
    #
    # The saved link and the employer's apply link both name the job: a posting saved from a board
    # is matched on the employer's own form, once the Companion has remembered that page as the
    # apply link. An apply link counts only when it names a posting (an id in the path or query):
    # one that does not is a prefix of every posting of that employer. is_not(None) narrows the scan only; it is not a safety guard, since
    # is_same_posting returns False for a null or unparseable link.
    stmt = (
        select(Job.id, Job.source_url, Job.apply_url)
        .where(or_(Job.source_url.is_not(None), Job.apply_url.is_not(None)))
        .order_by(Job.created_at.desc())
    )
    matched_id = next(
        (
            job_id
            for job_id, source_url, apply_url in db.execute(stmt)
            if job_url_match.is_same_posting(source_url, url)
            or (job_url_match.names_posting(apply_url) and job_url_match.is_same_posting(apply_url, url))
        ),
        None,
    )
    if matched_id is None:
        return JobMatchResult(match="none")

    job = db.get(Job, matched_id)
    sync_ownership.stamp(db, [job])
    # The same newest as stage.newest_applications, so the rung is this application's.
    application = application_writes.newest_for_job(db, job.id)
    # The job's rung is its newest application's, so both summaries carry the same one.
    st = stage.for_job_rows(db, [job])[job.id]
    stage.stamp(job, st)
    summary = None
    if application is not None:
        # Same flat job-field join as list_applications: ApplicationSummary
        # carries job_title/job_company/job_location, not a nested job.
        summary = ApplicationSummary.model_validate(application)
        summary.job_title = job.title
        summary.job_company = job.company
        summary.job_location = job.location
        summary.ownership = job.ownership
        summary.base_resume_name = base_resume_data.display_name_of(db, application.base_resume)
        summary.has_draft = bool(application.customized_json)
        summary.has_pdf = bool(application.pdf_path)
        summary.stage = st.rung
        summary.open_session_id = st.open_session_id
        summary.gaps_done = st.gaps_done
        summary.gaps_total = st.gaps_total

    return JobMatchResult(
        match="exact",
        job=JobSummary.model_validate(job),
        application=summary,
        knockout=knockout.scan_for(db, job),
    )


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _with_newest_proposal(db, job)


def _home_job(db: Session, job_id: UUID) -> Job:
    if not sync_status.enabled():
        raise HTTPException(status_code=404, detail="Sync isn't set up.")
    if sync_status.is_remote():
        raise HTTPException(status_code=409, detail="Make this change on your laptop.")
    begin_write(db)
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/keep-here", response_model=JobRead)
def keep_job_here(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = _home_job(db, job_id)
    if job.owner_machine not in (None, sync_status.machine_id(db)):
        raise HTTPException(status_code=409, detail=sync_hooks.WITH_BOT_MESSAGE)
    if job.handover == "offered":
        with sync_hooks.standing_aside(db):
            job.handover = None
            db.commit()
    return _with_newest_proposal(db, job)


@router.post("/{job_id}/work-here", status_code=202)
def work_on_job_here(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = _home_job(db, job_id)
    if not sync_requests.is_other_copys(db, job.id):
        raise HTTPException(status_code=409, detail="This job is already on your laptop.")
    sync_requests.enqueue_take_over(db, job.id)
    return sync_requests.queued_response()


@router.patch("/{job_id}", response_model=JobRead)
def patch_job(job_id: UUID, payload: JobPatch, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if payload.source_url is not None:
        job.source_url = payload.source_url.strip() or None
    if payload.apply_url is not None:
        job.apply_url = payload.apply_url
    db.commit()
    db.refresh(job)
    return _with_newest_proposal(db, job)


@router.get("/{job_id}/detail", response_model=JobDetail)
def get_job_detail(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # The same newest as stage.newest_applications, so the rung is this application's.
    application = application_writes.newest_for_job(db, job_id)
    # Same derived proposal_status / proposal_id / proposal_proposed_by as the list endpoint
    # (transient attrs) so the job page can triage and load proposal detail.
    _with_newest_proposal(db, job)
    scan = knockout.scan_for(db, job)
    st = stage.for_job_rows(db, [job])[job.id]
    return JobDetail(
        job=JobRead.model_validate(job),
        application=ApplicationRead.model_validate(application) if application else None,
        knockout=scan,
        has_filled_answers=filled_answers.has_any(db, job_id),
        base_resume_name=(
            base_resume_data.display_name_of(db, application.base_resume) if application else None
        ),
        stage=st.rung,
        open_session_id=st.open_session_id,
        gaps_done=st.gaps_done,
        gaps_total=st.gaps_total,
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
            detail="This job was saved without its original text, so it can't be read "
            "again. Add the job again from its job page.",
        )

    extraction = jd_extraction.extract_jd(job.raw_text, db)
    extraction = jd_extraction.apply_work_auth_backstop(job.raw_text, dict(extraction))
    _replace_extraction(db, job, extraction)
    db.commit()
    db.refresh(job)
    return _with_newest_proposal(db, job)


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
