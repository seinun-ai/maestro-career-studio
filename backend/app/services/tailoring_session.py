"""Tailoring session workflow: freeze a gap list at creation, accumulate resolutions,
then turn resolutions into LLM-generated typed edit ops and an auto-scored application."""
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.application import Application
from app.models.career_kb import KBPoint, KBPortLog
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.schemas.resume_edit import (
    AddBullet,
    AddSkillItem,
    ResumeEdit,
    ResumeEditRequest,
    ToggleEntry,
)
from app.services import (
    application_writes,
    artifacts,
    ats_score,
    gap_analysis,
    gap_enrichment,
    kb_resolver,
    llm,
    model_settings,
    persona,
    placement_targets,
    prompt_assembly,
    resume_edit,
    resume_lint,
    resume_versions,
)
from app.services.ats import normalize_term, score_resume, term_in_text
from app.services.resume_projects import extra_entry_live, extra_section_live
from app.services.base_resume_data import load_base_resume

logger = logging.getLogger(__name__)

# Archived KB entity that holds user_cannot_confirm claims with no matching
# entity. Archived on purpose: invisible to compose_resume_data, the resolver
# snapshot, and consolidation's non-archived surfaces, yet queryable so the
# suppression lookup (and the user, via the KB page's archived view) can see it.
CANNOT_CONFIRM_HOLDER_TITLE = "Unconfirmed claims"


def _content_hash(data) -> str:
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def staleness_reason(tailoring: "TailoringSession", session: Session) -> str | None:
    """None when the session's frozen inputs still match reality; otherwise a
    human sentence naming what changed. Legacy rows without hashes are treated
    as fresh (staleness unknown)."""
    reasons = []
    if tailoring.base_content_hash:
        try:
            current = load_base_resume(tailoring.base_resume, session)
        except ValueError:
            return "the base resume no longer exists"
        if _content_hash(current) != tailoring.base_content_hash:
            reasons.append("the base resume was edited")
    if tailoring.jd_extraction_hash:
        job = session.get(Job, tailoring.job_id)
        if job is None or not job.extracted_json:
            return "the job no longer exists"
        if _content_hash(job.extracted_json) != tailoring.jd_extraction_hash:
            reasons.append("the job description was re-extracted")
    if not reasons:
        return None
    return " and ".join(reasons)


def _require_fresh(tailoring: "TailoringSession", session: Session) -> None:
    reason = staleness_reason(tailoring, session)
    if reason:
        raise StaleSessionError(
            f"This gap analysis is stale — {reason} since it was created. "
            "Start a new analysis (it will supersede this one)."
        )


class SessionNotOpenError(ValueError):
    """Resolutions submitted to a non-open session (router maps this to 409)."""


class StaleSessionError(ValueError):
    """The session's frozen gaps no longer match the current base resume / JD
    (router maps this to 409). Mutating a stale session would tailor a
    different document than the one the user reviewed."""


class HealthGateBlockedError(ValueError):
    """A fresh fatal, unwaived health gate is failing on the base resume —
    tailoring reweights a healthy document; it cannot repair a broken one."""


def _plan_auto_resolutions(session: Session, gaps: dict) -> list[dict]:
    """Deterministic auto-resolutions for a fresh session, two passes in order.

    Pass 1 — evidence autos: candidates are stamped UNCONDITIONALLY (not only
    when enrichment ran), and mirror_wording gaps plan their exact-token skills
    add even unenriched — the token, not the LLM, is the fix.
    Pass 2 — "I can't confirm this" suppression (inv-provenance-no-decay's user
    face): a claim the user disconfirmed before arrives pre-resolved as
    cannot_confirm instead of being re-asked. Runs AFTER the evidence autos and
    only over gaps they left open — real evidence the resolver verified always
    beats an old "don't know".
    """
    every_gap = [
        gap
        for category in gaps.get("categories", [])
        for gap in category.get("gaps", [])
    ]
    autos = [
        resolution
        for gap in every_gap
        if (resolution := kb_resolver.auto_resolution_for_gap(gap)) is not None
    ]
    suppressed = kb_resolver.cannot_confirm_texts(session)
    if suppressed:
        resolved_ids = {r["gap_id"] for r in autos}
        autos.extend(
            resolution
            for gap in every_gap
            if gap.get("gap_id") not in resolved_ids
            and (resolution := kb_resolver.cannot_confirm_resolution(gap, suppressed))
            is not None
        )
    return autos


def create_session(
    job_id: UUID,
    base_resume: str,
    *,
    enrich: bool = True,
    session: Session | None = None,
) -> TailoringSession:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        # Health gate FIRST (opt-in): a FRESH failing fatal, unwaived gate on the
        # base resume blocks tailoring outright — tailoring reweights a healthy
        # document, it cannot repair a broken one. A stale report behaves like
        # no report for blocking and carries a re-analyze warning; a fresh low
        # score only warns. It's a cheap DB read, so a block fails fast before
        # any engine run or enrichment spend (audit C18). No report at all →
        # proceed silently (health is opt-in).
        health_warning = None
        health = resume_lint.latest_report(session, "base", base_resume)
        if health is not None:
            current_version = resume_versions.latest_version(
                session, "base", base_resume
            )
            current_number = (
                current_version.version_number if current_version else None
            )
            if health.resume_version_number != current_number:
                report_version = health.resume_version_number
                health_warning = (
                    "Health report is stale "
                    f"(ran against v{report_version if report_version is not None else '?'}; "
                    f"resume is now v{current_number if current_number is not None else '?'}) "
                    "— re-analyze."
                )
            else:
                rj = health.report_json
                # Waivers come off the TABLE, never off the report's own statuses:
                # waiving writes a row and nothing else, so the stored snapshot
                # still reads "fail" until the next health-check RUN folds waivers
                # in. Reading statuses alone left MCP's documented escape hatch shut
                # — waive, retry, same 409 — while the web path only worked because
                # its waive button re-runs the check.
                waived = resume_lint.gate_waivers(session, "base", base_resume)
                failed_fatal = [
                    g
                    for g in rj.get("gates", [])
                    if g.get("tier") == "fatal"
                    and g.get("status") == "fail"
                    and g.get("id") not in waived
                ]
                if failed_fatal:
                    raise HealthGateBlockedError(
                        "Base resume has failing structural gate(s): "
                        + ", ".join(g["id"] for g in failed_fatal)
                        + ". Fix or waive them in the health check before tailoring."
                    )
                if rj.get("score", 100) < 55:
                    health_warning = (
                        f"Base resume health is {rj.get('score')} ({rj.get('grade')}); "
                        "tailoring a weak base produces weak output."
                    )

        # Run the engine ONCE: gaps are built from this result and the same
        # result is persisted as the "before" score row (audit C18 — this used
        # to be two identical engine runs plus a divergence warning).
        job = ats_score.get_scorable_job(session, job_id)
        resume_json = load_base_resume(base_resume, session)
        result = score_resume(resume_json, job.extracted_json)
        # score_target STAGES on our session (flush, no commit): the score row,
        # the supersede update, and the new session row all ride the ONE commit
        # below — a failure anywhere before it leaves no committed trace. The
        # transaction stays open across the enrichment LLM call; acceptable for
        # a single-user app, and the alternative was an orphanable score row.
        row = ats_score.score_target(
            job_id, "base_resume", base_resume, phase="base", session=session, result=result
        )

        # A new session supersedes any prior open one for this (job, base): the
        # UI only ever resumes the newest open session, so older ones were
        # permanent orphans (audit C24).
        session.execute(
            update(TailoringSession)
            .where(
                TailoringSession.job_id == job_id,
                TailoringSession.base_resume == base_resume,
                TailoringSession.status == "open",
            )
            .values(status="superseded")
        )

        gaps = gap_analysis.build_gaps(result)
        # Snapshot load is OUTSIDE the enrich branch: the gating pass below is
        # deterministic and must run whether or not enrichment does.
        try:
            kb_snapshot = kb_resolver.load_kb_snapshot(session)
        except Exception:
            kb_snapshot = None
            logger.warning(
                "Career KB snapshot failed for job %s; continuing without library evidence",
                job_id,
                exc_info=True,
            )
        if enrich:
            try:
                gaps = gap_enrichment.enrich_gaps(
                    gaps,
                    resume_json,
                    job.extracted_json,
                    kb_snapshot=kb_snapshot,
                    session=session,
                )
            except Exception:
                logger.warning(
                    "Gap enrichment failed for job %s; storing unenriched gaps",
                    job_id,
                    exc_info=True,
                )
        # Called UNCONDITIONALLY (kb_snapshot may be None): stamp_library_candidates
        # itself decides what "no snapshot" means (pop the private stash, write no
        # library_candidates), so there is no second place that has to agree with
        # it on when gating ran — the correctness argument used to be spread across
        # this call site AND enrich_gaps' stash guard both reading kb_snapshot, and
        # a single missed guard leaked a private key into frozen gaps_json.
        #
        # KB library evidence is an ENHANCEMENT, not a requirement, and this point
        # has already paid for a full engine run — losing the whole session because
        # one malformed KB detail_json blew up the merge is the wrong trade, so this
        # degrades like its two neighbors above rather than failing loud.
        try:
            gaps = gap_enrichment.stamp_library_candidates(gaps, resume_json, kb_snapshot)
        except Exception:
            logger.warning(
                "Library candidate gating failed for job %s; storing ungated gaps",
                job_id,
                exc_info=True,
            )
            # Scrub, don't re-stamp: pop_stash shares the deepcopy/category/gap
            # walk with the path that just raised, but has no verify_candidate
            # call in it, so the malformed-KB failure class above cannot recur
            # here (a malformed `gaps` SHAPE would take both paths down alike —
            # not reachable with real data, since gaps comes from in-house
            # build_gaps). Calling stamp_library_candidates(None) here would
            # "stamp" nothing and make the name a lie at this call site.
            gaps = gap_enrichment.pop_stash(gaps)
        auto_resolutions = _plan_auto_resolutions(session, gaps)

        tailoring = TailoringSession(
            job_id=job_id,
            base_resume=base_resume,
            status="open",
            gaps_json=gaps,
            resolutions_json=auto_resolutions,
            base_ats_score_id=row.id,
            # Freeze the inputs the gaps were built from (SYSTEM.md §11 #1).
            base_content_hash=_content_hash(resume_json),
            jd_extraction_hash=_content_hash(job.extracted_json),
        )
        session.add(tailoring)
        session.commit()
        session.refresh(tailoring)
        # Non-persisted, transient instance attribute surfaced by TailoringSessionRead.
        # Set AFTER refresh so the reload doesn't clear it.
        tailoring.health_warning = health_warning
        return tailoring
    finally:
        if owns_session:
            session.close()


def close_session(session_id: UUID, *, session: Session | None = None) -> TailoringSession:
    """Abandon an open session (terminal state).

    The other exits from "open" are a successful tailor ("tailored") and being
    superseded by a newer session for the same (job, base). Non-open sessions
    409 via SessionNotOpenError — closing is not an undo.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        tailoring = session.get(TailoringSession, session_id)
        if tailoring is None:
            raise ValueError(f"Tailoring session not found: {session_id}")
        if tailoring.status != "open":
            raise SessionNotOpenError(
                f"Tailoring session {session_id} is not open (status={tailoring.status!r})"
            )
        tailoring.status = "abandoned"
        session.commit()
        session.refresh(tailoring)
        return tailoring
    finally:
        if owns_session:
            session.close()


def _gap_index(gaps_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        gap["gap_id"]: gap
        for category in gaps_json.get("categories", [])
        for gap in category["gaps"]
    }


def _is_missing_skill(gap: dict[str, Any]) -> bool:
    # "absent" = the deterministic engine found no evidence of the skill anywhere;
    # such an add_keyword add is unverified and must stay in the skills list only.
    return (gap.get("diagnostic") or {}).get("fix_hint") == "absent"


def _validate_placement_target(
    placement_target: dict[str, Any],
    resume_targets: dict[str, Any],
    gap_id: str,
    *,
    missing_skill: bool = False,
) -> None:
    """Reject an add_keyword/user_input placement_target that does not point at a
    real destination on the base resume.

    Uses ``placement_targets.canonicalize`` for the exact rules shared
    with best-effort enrichment coercion: a skills category, an enabled core
    entry index, or an enabled custom-section destination identified by stable
    ``section_key``. This strict wrapper raises rather than dropping malformed
    caller input so it never reaches the tailor LLM. The web UI only sends valid
    chips, so this mainly guards MCP/API callers (findings F#10, F#7, F#4).

    ``missing_skill`` (the add_keyword-only honesty guard) is threaded through by
    the caller; user_input passes it False (see save_resolutions).
    """
    try:
        placement_targets.canonicalize(
            placement_target, resume_targets, missing_skill=missing_skill
        )
    except ValueError as exc:
        raise ValueError(
            f"placement target for gap {gap_id!r} {exc}"
        ) from exc


def _validate_attach_project(
    project_name: Any, enabled_project_names: set[str], gap_id: str
) -> None:
    """An attach_project resolution must name an ENABLED project on the base
    resume (case-insensitive) — a disabled project never renders, and a typo'd
    name would otherwise reach the tailor LLM as a phantom attachment."""
    names = {n.lower() for n in enabled_project_names}
    if not isinstance(project_name, str) or project_name.lower() not in names:
        raise ValueError(
            f"attach_project for gap {gap_id!r} names {project_name!r}, which is not "
            f"an enabled project on the base resume "
            f"(enabled: {sorted(enabled_project_names)})"
        )


def _validate_enable_entry(
    payload: dict[str, Any], resume_json: dict[str, Any], gap_id: str, jd_skill: str | None
) -> tuple[str, int]:
    section = payload.get("section")
    index = payload.get("index")
    if section not in ("experience", "projects"):
        raise ValueError(
            f"enable_entry for gap {gap_id!r} must target experience or projects"
        )
    entries = resume_json.get(section)
    if (
        not isinstance(entries, list)
        or isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
        or index >= len(entries)
    ):
        raise ValueError(
            f"enable_entry for gap {gap_id!r} names an out-of-range {section} index"
        )
    entry = entries[index]
    if not isinstance(entry, dict) or entry.get("enabled") is not False:
        raise ValueError(
            f"enable_entry for gap {gap_id!r} must target an explicitly disabled entry"
        )
    # Evidence gate: the skills-only honesty exemption for this action rests on the
    # entry actually evidencing the gap's JD skill. Same literal-containment check
    # the enrichment gate uses, re-run here because save_resolutions is the
    # chokepoint for MCP/API callers who never went through enrichment.
    if not kb_resolver.evidence_match(
        jd_skill or "", kb_resolver.entry_evidence_texts(section, entry)
    ):
        raise ValueError(
            f"enable_entry for gap {gap_id!r} targets an entry with no literal "
            f"evidence of {jd_skill!r}; enable it in the editor instead if intended"
        )
    return section, index


def _validate_port_kb_point(
    payload: dict[str, Any],
    resume_targets: dict[str, Any],
    db_session: Session,
    gap_id: str,
    jd_skill: str | None,
) -> None:
    raw_point_id = payload.get("kb_point_id")
    try:
        point_id = UUID(str(raw_point_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"port_kb_point for gap {gap_id!r} names an invalid KB point id"
        ) from exc
    point = db_session.get(KBPoint, point_id)
    if point is None or point.state != "approved":
        raise ValueError(
            f"port_kb_point for gap {gap_id!r} requires an approved KB point"
        )
    wording = payload.get("wording")
    if not isinstance(wording, str) or not wording.strip():
        raise ValueError(
            f"port_kb_point for gap {gap_id!r} requires non-empty wording"
        )
    # Evidence gate (the honesty bypass is earned, not assumed): the approved
    # point's own text must literally evidence the gap's JD skill, and the
    # wording that will land on the resume must carry it too — otherwise this
    # action would let any caller write arbitrary prose into a dated entry
    # using an unrelated approved point as cover.
    if not kb_resolver.evidence_match(jd_skill or "", [point.text]):
        raise ValueError(
            f"port_kb_point for gap {gap_id!r}: the KB point does not literally "
            f"evidence {jd_skill!r}"
        )
    if not kb_resolver.evidence_match(jd_skill or "", [wording]):
        raise ValueError(
            f"port_kb_point for gap {gap_id!r}: wording must contain the JD skill "
            f"term {jd_skill!r}"
        )
    placement_target = payload.get("placement_target")
    if not isinstance(placement_target, dict) or placement_target.get("section") not in (
        "experience",
        "projects",
    ):
        raise ValueError(
            f"port_kb_point for gap {gap_id!r} must target experience or projects"
        )
    _validate_placement_target(
        placement_target, resume_targets, gap_id, missing_skill=False
    )


def _target_check_needed(item: dict[str, Any]) -> bool:
    """Whether this item's target has to be checked against the base resume.

    A pure skip/user_input batch reads nothing, so the resume load stays lazy.
    add_keyword AND user_input can both carry a placement_target (phase-2 chips
    include custom sections); either must be validated (finding F#4).
    """
    if item["action"] in ("attach_project", "enable_entry", "port_kb_point"):
        return True
    if item["action"] in ("add_keyword", "user_input"):
        return bool((item.get("payload") or {}).get("placement_target"))
    return False


def _load_resume_context(
    tailoring: TailoringSession, session: Session, *, needed: bool
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, set[str]]:
    """Load the base resume ONCE and derive everything the validators need.

    The resume-targets shape and the enabled project names come from the same
    read. Reuses C4's helper so both placement validators agree on what a valid
    destination is (real skills categories + ENABLED experience/project counts).
    """
    if not needed:
        return None, None, set()
    resume_json = load_base_resume(tailoring.base_resume, session)
    enabled_project_names = {
        entry["name"]
        for entry in resume_json.get("projects", [])
        if isinstance(entry, dict) and entry.get("enabled", True) and entry.get("name")
    }
    return resume_json, placement_targets.build_targets(resume_json), enabled_project_names


def _assert_actions_allowed(
    resolutions: list[dict[str, Any]], gaps: dict[str, dict[str, Any]]
) -> None:
    """Validate gap/action membership for the WHOLE incoming batch first.

    The target phase may compose multiple items, so no item may lend authority
    to another until its own action is known to be legal.
    """
    for item in resolutions:
        gap = gaps.get(item["gap_id"])
        if gap is None:
            raise ValueError(f"Unknown gap_id: {item['gap_id']}")
        actions = set(gap["actions"])
        # cannot_confirm is legal wherever a claim question was asked. Frozen
        # pre-Phase-C sessions never list it in their actions, so it piggybacks
        # on user_input (the question-asking action) for those.
        if item["action"] == "cannot_confirm":
            if "cannot_confirm" in actions or "user_input" in actions:
                continue
        if item["action"] not in actions:
            raise ValueError(
                f"Action {item['action']!r} is not allowed for gap {item['gap_id']!r} "
                f"(allowed: {sorted(actions)})"
            )


def _project_resolutions(
    stored: list[dict[str, Any]], incoming: list[dict[str, Any]], replace: bool
) -> dict[str, dict[str, Any]]:
    """The resolution set as it will be STORED, keyed by gap_id.

    replace=True: the batch is the whole truth — deduped by gap_id (last wins),
    so omitted gap_ids are deleted. Otherwise merge by gap_id: existing order is
    preserved, new gaps append, re-submitted gaps are overwritten in place
    (idempotent per batch).

    Computed ONCE and used for both validation and persistence. These were two
    separate identical blocks; a change to merge semantics in one would have let
    the function validate a different set than the one it wrote.
    """
    if replace:
        return {item["gap_id"]: item for item in incoming}
    projected = {existing["gap_id"]: existing for existing in stored}
    for item in incoming:
        projected[item["gap_id"]] = item
    return projected


def _collect_pending_enables(
    projected: dict[str, dict[str, Any]],
    resume_json: dict[str, Any],
    gaps: dict[str, dict[str, Any]],
) -> set[tuple[str, int]]:
    """Entries a port may target because a projected item enables them.

    Reads the PROJECTED set, not the incoming batch: a port may target an entry
    enabled by another projected item, including a prior merge-mode save. Under
    replace=True, omitted stored enables are gone and therefore cannot authorize
    a port in the replacement batch.
    """
    pending: set[tuple[str, int]] = set()
    for item in projected.values():
        if item.get("action") == "enable_entry":
            pending.add(
                _validate_enable_entry(
                    item.get("payload") or {},
                    resume_json,
                    item["gap_id"],
                    gaps.get(item["gap_id"], {}).get("jd_skill"),
                )
            )
    return pending


@dataclass
class _ResolutionContext:
    """Everything a resolution's target/honesty checks need, built once per
    batch by save_resolutions.

    Carries the invariant the old six-argument signature left to caller
    discipline: `resume_targets` validates add_keyword/user_input placements,
    while `port_targets` is the WIDENED view for port_kb_point — it also
    admits entries a projected enable_entry in the same batch will turn on.
    Passing the unwidened view to a port would silently reject a legal port
    that depends on a co-submitted enable."""

    gaps: dict[str, dict[str, Any]]
    resume_targets: dict[str, Any] | None
    port_targets: dict[str, Any] | None
    enabled_project_names: set[str]


def _assert_resolution_valid(
    item: dict[str, Any],
    ctx: _ResolutionContext,
    session: Session,
) -> None:
    """Target and honesty checks for one resolution (defense in depth).

    A bad target — an out-of-range index, an unknown skills category, or a
    typo'd project — must be rejected here so it never reaches the tailor LLM.
    The web UI already restricts to valid chips; this mainly guards MCP/API
    callers.
    """
    payload = item.get("payload") or {}
    gap = ctx.gaps[item["gap_id"]]

    if item["action"] in ("add_keyword", "user_input"):
        placement_target = payload.get("placement_target")
        if placement_target:
            # The add_keyword HONESTY guard (an engine-unverified skill may only
            # land in the skills list) stays add_keyword-ONLY: user_input is
            # user-authored evidence, not an unverified keyword add, so target
            # existence is checked but missing_skill never applies to it (F#4).
            _validate_placement_target(
                placement_target,
                ctx.resume_targets,
                item["gap_id"],
                missing_skill=(item["action"] == "add_keyword" and _is_missing_skill(gap)),
            )
    elif item["action"] == "attach_project":
        _validate_attach_project(
            payload.get("project_name"), ctx.enabled_project_names, item["gap_id"]
        )
    elif item["action"] == "port_kb_point":
        _validate_port_kb_point(
            payload, ctx.port_targets, session, item["gap_id"], gap.get("jd_skill")
        )

    # Honesty invariant (defense in depth): an add_keyword on a MISSING skill is
    # an unverified add — it may only land in the skills list, never as a
    # fabricated experience/project bullet. Enforced here so no UI or MCP caller
    # can bypass the prompt-level rule. enable_entry and port_kb_point are
    # evidence-carrying actions whose referenced content was validated above;
    # they are exempt from this rule by construction.
    if item["action"] == "add_keyword" and _is_missing_skill(gap):
        target = payload.get("placement_target") or {}
        if target.get("section") != "skills":
            raise ValueError(
                "Unverified skill additions must target the skills section "
                f"(gap {item['gap_id']!r}, got section={target.get('section')!r})"
            )


def _claim_for_gap(gap: dict[str, Any]) -> str:
    """The claim/skill a cannot_confirm answer disconfirms — the same field the
    suppression lookup in create_session normalizes against."""
    return str(gap.get("jd_skill") or gap.get("detail") or "").strip()


def _entity_for_entry_ref(
    db_session: Session, base: dict[str, Any], target: dict[str, Any]
) -> Any:
    """Resolve a placement_target entry reference to a KB entity by title —
    the same case-insensitive, non-archived match the flywheel write-back uses.
    None for anything that is not a valid experience/projects entry ref."""
    from sqlalchemy import func as sa_func

    from app.models.career_kb import KBEntity

    section = target.get("section")
    index = target.get("index_or_category")
    if section not in ("experience", "projects") or isinstance(index, bool) or not isinstance(index, int):
        return None
    entries = base.get(section) or []
    if index < 0 or index >= len(entries) or not isinstance(entries[index], dict):
        return None
    entry = entries[index]
    title = str(
        entry.get("name") or entry.get("role") or entry.get("company") or ""
    ).strip()
    if not title:
        return None
    return db_session.scalar(
        select(KBEntity).where(
            sa_func.lower(KBEntity.title) == title.lower(),
            KBEntity.status != "archived",
        )
    )


def _cannot_confirm_holder(db_session: Session) -> Any:
    """The archived holder entity for entity-less cannot_confirm claims,
    created on first use."""
    from app.models.career_kb import KBEntity

    holder = db_session.scalar(
        select(KBEntity).where(
            KBEntity.kind == "extra",
            KBEntity.title == CANNOT_CONFIRM_HOLDER_TITLE,
        )
    )
    if holder is None:
        holder = KBEntity(
            kind="extra",
            title=CANNOT_CONFIRM_HOLDER_TITLE,
            status="archived",
            origin="gap_elicitation",
            detail_json={"holder": "cannot_confirm"},
        )
        db_session.add(holder)
        db_session.flush()
    return holder


def _record_cannot_confirm(
    db_session: Session,
    tailoring: "TailoringSession",
    resolutions: list[dict[str, Any]],
    gaps: dict[str, dict[str, Any]],
    resume_json: dict[str, Any] | None,
) -> None:
    """Stage the durable suppression record for each incoming cannot_confirm.

    Written at SAVE time (not tailor time, unlike the flywheel): "saved so you
    won't be asked again" must hold even when the session is later abandoned.
    Idempotent by normalized claim text, so autosave's replace=true re-sends
    are no-ops. Bound to the entity a placement_target names when one matches;
    otherwise to the archived holder entity — never skipped, or the web flow
    (which sends no placement) would produce no record at all. Undoing the
    resolution does NOT delete the point; the KB page is the management surface.
    """
    items = [i for i in resolutions if i.get("action") == "cannot_confirm"]
    if not items:
        return
    existing = {
        normalize_term(text)
        for text in db_session.scalars(
            select(KBPoint.text).where(KBPoint.provenance == "user_cannot_confirm")
        )
        if text
    }
    for item in items:
        gap = gaps.get(item["gap_id"]) or {}
        claim = _claim_for_gap(gap)
        if not claim:
            continue
        key = normalize_term(claim)
        if not key or key in existing:
            continue
        entity = None
        target = (item.get("payload") or {}).get("placement_target")
        if isinstance(target, dict):
            if resume_json is None:
                resume_json = load_base_resume(tailoring.base_resume, db_session)
            entity = _entity_for_entry_ref(db_session, resume_json, target)
        if entity is None:
            entity = _cannot_confirm_holder(db_session)
        db_session.add(
            KBPoint(
                entity_id=entity.id,
                text=claim,
                state="retired",
                origin="gap_elicitation",
                origin_detail=f"tailoring_session:{tailoring.id}",
                provenance="user_cannot_confirm",
            )
        )
        existing.add(key)


def save_resolutions(
    session_id: UUID,
    resolutions: list[dict[str, Any]],
    *,
    session: Session | None = None,
    replace: bool = False,
    user_prompt: str | None = None,
) -> TailoringSession:
    """Merge a resolution batch into the session by gap_id (new wins).

    With replace=True the batch is the whole truth: resolutions_json becomes
    exactly the validated incoming list (deduped by gap_id, last wins), so
    omitted gap_ids are deleted — a retracted resolution cannot silently
    resurrect and reach the tailor LLM.

    The whole batch is validated before anything is saved: one bad item
    rejects the batch. Merge semantics hold for serial requests; concurrent
    whole-list writes are last-write-wins (single-user app, per design non-goals).

    ``user_prompt`` is the optional per-session tailoring note: None leaves the
    stored value untouched, a whitespace-only string clears it back to None, and
    any other value is stored (stripped). Persisted in the same commit as the
    resolutions so a UI autosave carries both.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        tailoring = session.get(TailoringSession, session_id)
        if tailoring is None:
            raise ValueError(f"Tailoring session not found: {session_id}")
        if tailoring.status != "open":
            raise SessionNotOpenError(
                f"Tailoring session {session_id} is not open (status={tailoring.status!r})"
            )
        _require_fresh(tailoring, session)

        gaps = _gap_index(tailoring.gaps_json)

        resume_json, resume_targets, enabled_project_names = _load_resume_context(
            tailoring, session, needed=any(_target_check_needed(i) for i in resolutions)
        )

        _assert_actions_allowed(resolutions, gaps)

        projected = _project_resolutions(tailoring.resolutions_json, resolutions, replace)

        pending_enables: set[tuple[str, int]] = set()
        if any(item.get("action") == "enable_entry" for item in projected.values()):
            if resume_json is None:
                resume_json, resume_targets, enabled_project_names = _load_resume_context(
                    tailoring, session, needed=True
                )
            pending_enables = _collect_pending_enables(projected, resume_json, gaps)

        ctx = _ResolutionContext(
            gaps=gaps,
            resume_targets=resume_targets,
            port_targets=placement_targets.widen_for_enables(
                resume_targets, pending_enables
            ),
            enabled_project_names=enabled_project_names,
        )

        for item in resolutions:
            _assert_resolution_valid(item, ctx, session)

        # Durable "I can't confirm this" records ride this same commit. The
        # incoming batch is enough: every cannot_confirm passes through a save
        # at least once, and the write is idempotent by normalized claim text.
        _record_cannot_confirm(session, tailoring, resolutions, gaps, resume_json)

        # `projected` IS the stored set — see _project_resolutions.
        tailoring.resolutions_json = list(projected.values())

        # None = omitted, leave the stored note untouched; an empty/whitespace
        # string clears it back to None so the UI can wipe the field.
        if user_prompt is not None:
            tailoring.user_prompt = user_prompt.strip() or None

        session.commit()
        session.refresh(tailoring)
        return tailoring
    finally:
        if owns_session:
            session.close()


# Gap fields forwarded to the ops LLM alongside each non-skip resolution: the
# diagnostic carries the match evidence and the enrichment carries the helper
# text the user's payload may refer to (suggested wording, project candidates).
_GAP_CONTEXT_FIELDS = ("kind", "jd_skill", "requirement_level", "detail", "diagnostic", "enrichment")


def _deterministic_pre_ops(
    resolutions: list[dict[str, Any]],
) -> tuple[list[ResumeEdit], list[dict[str, Any]], list[str]]:
    """Materialize library actions before the LLM and describe what was done."""
    ops: list[ResumeEdit] = []
    handled: list[dict[str, Any]] = []
    lines: list[str] = []
    seen_enables: set[tuple[str, int]] = set()
    seen_ports: set[tuple[str, str, int]] = set()
    for item in resolutions:
        payload = item.get("payload") or {}
        if item.get("action") == "enable_entry":
            enable_key = (payload["section"], payload["index"])
            if enable_key in seen_enables:
                continue
            seen_enables.add(enable_key)
            ops.append(
                ToggleEntry(
                    kind="toggle_entry",
                    section=payload["section"],
                    index=payload["index"],
                    enabled=True,
                )
            )
            handled.append(item)
            name = payload.get("name") or f"{payload['section']} entry {payload['index']}"
            section_label = "project" if payload["section"] == "projects" else "experience"
            lines.append(f"Enabled {section_label} {name!r}")
        elif item.get("action") == "port_kb_point":
            target = payload["placement_target"]
            # One bullet per (point, destination): two gaps whose JD terms both
            # live in the same approved point would otherwise append the same
            # bullet twice — the single bullet already evidences both terms.
            port_key = (
                str(payload.get("kb_point_id")),
                target["section"],
                target["index_or_category"],
            )
            if port_key in seen_ports:
                continue
            seen_ports.add(port_key)
            ops.append(
                AddBullet(
                    kind="add_bullet",
                    section=target["section"],
                    index=target["index_or_category"],
                    text=payload["wording"],
                )
            )
            handled.append(item)
            lines.append(
                "Ported KB point into "
                f"{target['section']} entry {target['index_or_category']}"
            )
    return ops, handled, lines


def _resolution_bundle(
    tailoring: TailoringSession, already_applied: list[str]
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Split resolutions into actionable, skipped, and already-applied lines.

    Skipped gaps are excluded from the LLM's mandate entirely: they surface only
    as a name list under the prompt's do-not-touch heading. ``already_applied``
    is the pre-op line list the caller computed when it materialized them.
    """
    gaps_by_id = {
        gap["gap_id"]: gap
        for category in tailoring.gaps_json.get("categories", [])
        for gap in category["gaps"]
    }
    actionable: list[dict[str, Any]] = []
    skipped: list[str] = []
    for item in tailoring.resolutions_json:
        # save_resolutions validated every gap_id against gaps_json; .get() is defensive
        gap = gaps_by_id.get(item["gap_id"], {})
        # cannot_confirm is a skip for the DOCUMENT (its KB record was already
        # written at save time); the LLM must leave the gap untouched.
        if item["action"] in ("skip", "cannot_confirm"):
            skipped.append(gap.get("jd_skill") or gap.get("detail") or item["gap_id"])
            continue
        if item["action"] in ("enable_entry", "port_kb_point"):
            continue
        actionable.append(
            {
                "gap_id": item["gap_id"],
                "action": item["action"],
                "payload": item.get("payload", {}),
                "gap": {
                    key: gap[key]
                    for key in _GAP_CONTEXT_FIELDS
                    if gap.get(key) is not None
                },
            }
        )
    return actionable, skipped, already_applied


_WRITE_BACK_MIN_CHARS = 40
_WRITE_BACK_DEDUP_COSINE = 0.90


def _write_back_elicited_points(
    db_session: Session, tailoring: TailoringSession, base: dict[str, Any]
) -> list[dict[str, Any]]:
    """The flywheel (design §4.6): a substantive user_input answer targeting a
    dated entry becomes a DRAFT KB point on the matching entity, so the next
    session's resolver can surface it. Draft state means suggest-only until the
    user approves it in the KB. Rows are STAGED only — they ride score_target's
    single commit; a failed tailor writes nothing. No entity match → skip,
    never guess.

    Returns the SKIP list `[{gap_id, skill, reason, detail}]` (Phase C Task
    11): every drop travels up through the tailor response instead of dying in
    a backend log. Only claim-carrying gaps (skill/requirement) are reported —
    a summary/title rewrite is presentation, not evidence, and flagging every
    one as "not saved to your Career KB" would drown the real drops.
    """
    from sqlalchemy import func as sa_func

    from app.models.career_kb import KBEntity

    gaps_by_id = _gap_index(tailoring.gaps_json)
    skips: list[dict[str, Any]] = []

    def _skip(item: dict[str, Any], reason: str, detail: str) -> None:
        gap = gaps_by_id.get(item["gap_id"]) or {}
        if gap.get("kind") not in ("skill", "requirement"):
            return
        skips.append(
            {
                "gap_id": item["gap_id"],
                "skill": gap.get("jd_skill"),
                "reason": reason,
                "detail": detail,
            }
        )

    for item in tailoring.resolutions_json:
        if item.get("action") != "user_input":
            continue
        payload = item.get("payload") or {}
        text = (payload.get("text") or "").strip()
        if len(text) < _WRITE_BACK_MIN_CHARS:
            _skip(
                item,
                "too_short",
                f"the answer is under {_WRITE_BACK_MIN_CHARS} characters — "
                "too short to keep as evidence",
            )
            continue
        target = payload.get("placement_target") or {}
        section = target.get("section")
        index = target.get("index_or_category")
        if section not in ("experience", "projects") or isinstance(index, bool) or not isinstance(index, int):
            _skip(
                item,
                "wrong_section",
                "the answer isn't attached to an experience or project entry",
            )
            continue
        entries = base.get(section) or []
        if index < 0 or index >= len(entries) or not isinstance(entries[index], dict):
            _skip(
                item,
                "wrong_section",
                "the answer isn't attached to an experience or project entry",
            )
            continue
        entry = entries[index]
        title = str(
            entry.get("name") or entry.get("role") or entry.get("company") or ""
        ).strip()
        if not title:
            _skip(
                item,
                "no_entity_match",
                "the target entry has no title to match a Career KB entity",
            )
            continue
        entity = db_session.scalar(
            select(KBEntity).where(
                sa_func.lower(KBEntity.title) == title.lower(),
                KBEntity.status != "archived",
            )
        )
        if entity is None:
            _skip(
                item,
                "no_entity_match",
                f"no Career KB entity titled “{title}”",
            )
            continue
        existing_texts = [
            point.text for point in entity.points if point.state != "retired"
        ]
        if _is_duplicate_point(text, existing_texts):
            _skip(
                item,
                "duplicate",
                f"an equivalent point already exists on “{title}”",
            )
            continue
        db_session.add(
            KBPoint(
                entity_id=entity.id,
                text=text,
                state="draft",
                origin="gap_elicitation",
                origin_detail=f"tailoring_session:{tailoring.id}",
                provenance="user_stated",
            )
        )
    return skips


def _is_duplicate_point(text: str, existing_texts: list[str]) -> bool:
    """Cosine dedup with an exact-normalized fallback when embeddings are
    unavailable — write-back must never block a tailor."""
    if not existing_texts:
        return False
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([text] + existing_texts)
        return any(
            cosine(vectors[0], vector) >= _WRITE_BACK_DEDUP_COSINE
            for vector in vectors[1:]
        )
    except Exception:
        normalized = text.strip().casefold()
        return any(normalized == item.strip().casefold() for item in existing_texts)


def _validation_summary(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )


def _live_text_fragments(document: dict[str, Any]) -> list[str]:
    """Every text fragment the ATS engine can actually see, one string each.

    Disabled entries, dead extra sections, education, and contact are excluded:
    a keyword that survives only there earns no engine credit, so counting it
    would let the survival check silently pass on a de-tailored resume. Kept as
    separate fragments (not one joined dump) so adjacent values can't fuse into
    a phantom multi-word match.
    """
    fragments: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            fragments.append(value)

    _add(document.get("summary"))
    for group in document.get("skills") or []:
        if isinstance(group, dict):
            _add(group.get("category"))
            for item in group.get("items") or []:
                _add(item)
    for section in ("experience", "projects"):
        for entry in document.get(section) or []:
            if not isinstance(entry, dict) or entry.get("enabled", True) is False:
                continue
            for text in kb_resolver.entry_evidence_texts(section, entry):
                _add(text)
    for cert in document.get("certifications") or []:
        _add(cert)
    for extra in document.get("extra_sections") or []:
        if not isinstance(extra, dict) or not extra_section_live(extra):
            continue
        _add(extra.get("title"))
        for bullet in extra.get("bullets") or []:
            _add(bullet)
        for entry in extra.get("entries") or []:
            if not isinstance(entry, dict) or not extra_entry_live(entry):
                continue
            _add(entry.get("heading"))
            _add(entry.get("subheading"))
            for bullet in entry.get("bullets") or []:
                _add(bullet)
    return fragments


def _missing_keywords(
    customized: dict[str, Any], resolutions: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any]]]:
    """Return requested keyword placements absent from the tailored document.

    Containment is checked per LIVE fragment (see _live_text_fragments), never
    against a whole-document JSON dump: a dump counts disabled entries the
    engine ignores (false survival) and fuses adjacent values into phantom
    multi-word matches.
    """
    normalized_fragments = [
        normalized
        for fragment in _live_text_fragments(customized)
        if (normalized := normalize_term(fragment))
    ]
    missing: list[tuple[str, dict[str, Any]]] = []
    for item in resolutions:
        if item.get("action") != "add_keyword":
            continue
        payload = item.get("payload") or {}
        wording = payload.get("wording")
        if not isinstance(wording, str) or not wording.strip():
            continue
        normalized_wording = normalize_term(wording)
        if normalized_wording and not any(
            term_in_text(normalized_wording, fragment)
            for fragment in normalized_fragments
        ):
            placement = payload.get("placement_target")
            missing.append(
                (wording.strip(), placement if isinstance(placement, dict) else {})
            )
    return missing


def _reject_stale_placements(tailoring: TailoringSession, base: dict[str, Any]) -> None:
    """F#5: re-validate EVERY non-skip resolution's placement_target against the
    CURRENT base resume at the point of no return — before the LLM call. A
    placement valid at save time can go stale (its target section/entry was
    deleted or disabled afterward) and would otherwise reach the tailor LLM
    through the resolution bundle. _require_fresh (base_content_hash) normally
    catches a base edit first; this is the SECOND net for same-hash edge cases —
    notably LEGACY sessions saved without hashes, where staleness is unknowable.
    Existence-only (missing_skill=False): the add_keyword honesty invariant was
    already enforced at save time and is base-independent."""
    current_targets = placement_targets.build_targets(base)
    stale_gap_ids: list[str] = []
    for item in tailoring.resolutions_json:
        if item.get("action") in ("skip", "cannot_confirm", "enable_entry"):
            continue
        placement_target = (item.get("payload") or {}).get("placement_target")
        if not placement_target:
            continue
        try:
            placement_targets.canonicalize(
                placement_target, current_targets, missing_skill=False
            )
        except ValueError:
            stale_gap_ids.append(item.get("gap_id"))
    if stale_gap_ids:
        raise ValueError(
            "Placement target(s) no longer point at a valid destination on the "
            f"base resume (gap_ids: {sorted(stale_gap_ids)}). The base resume "
            "changed after these resolutions were saved — start a new analysis."
        )


def _llm_customized(
    session: Session,
    tailoring: TailoringSession,
    base: dict[str, Any],
    actionable: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    already_applied: list[dict[str, Any]],
    user_prompt: str | None,
) -> dict[str, Any]:
    """tailor()'s LLM phase: build the gap-tailor prompt, generate typed ops,
    apply them, then enforce keyword survival — one corrective retry, then the
    add_skill_item fallback so a required wording can never silently vanish.
    Returns the customized resume dict; raises ValueError on invalid ops."""
    job = session.get(Job, tailoring.job_id)
    if job is None or not job.extracted_json:
        raise ValueError(
            f"Job not found or has no extracted data: {tailoring.job_id}"
        )

    prompt = prompt_assembly.build_gap_tailor_prompt(
        base,
        job.extracted_json,
        actionable,
        skipped,
        user_prompt=user_prompt,
        persona=persona.get_persona(session),
        already_applied=already_applied,
    )
    result = llm.call_openai(
        prompt=prompt,
        model=model_settings.get_smart_model(session),
        response_format="json",
        trace_name="tailoring",
    )

    try:
        llm_ops = ResumeEditRequest.model_validate(result).ops
    except ValidationError as exc:
        raise ValueError(
            f"Tailoring produced invalid edit ops: {_validation_summary(exc)}"
        ) from exc
    try:
        customized = resume_edit.apply_edits(base, llm_ops)
    except ValueError as exc:
        raise ValueError(f"Tailoring produced invalid edit ops: {exc}") from exc

    missing = _missing_keywords(customized, tailoring.resolutions_json)
    if missing:
        missing_wordings = [wording for wording, _ in missing]
        retry_prompt = (
            f"{prompt}\n\nCORRECTION REQUIRED: the prior edit set dropped these "
            "required keyword wordings. Return a complete corrected ops list "
            "that preserves each wording verbatim: "
            f"{json.dumps(missing_wordings)}"
        )
        retry_result = llm.call_openai(
            prompt=retry_prompt,
            model=model_settings.get_smart_model(session),
            response_format="json",
            trace_name="tailoring",
        )
        try:
            retry_ops = ResumeEditRequest.model_validate(retry_result).ops
        except ValidationError as exc:
            raise ValueError(
                "Tailoring produced invalid edit ops: "
                f"{_validation_summary(exc)}"
            ) from exc
        try:
            customized = resume_edit.apply_edits(base, retry_ops)
        except ValueError as exc:
            raise ValueError(
                f"Tailoring produced invalid edit ops: {exc}"
            ) from exc
        missing = _missing_keywords(customized, tailoring.resolutions_json)
        if missing:
            fallback_ops: list[ResumeEdit] = []
            for wording, placement in missing:
                category = placement_targets.ADDITIONAL_SKILLS
                if placement.get("section") == "skills" and isinstance(
                    placement.get("index_or_category"), str
                ):
                    category = placement["index_or_category"]
                fallback_ops.append(
                    AddSkillItem(
                        kind="add_skill_item",
                        category=category,
                        item=wording,
                    )
                )
            logger.warning(
                "keyword-survival fallback engaged: %s",
                [wording for wording, _ in missing],
            )
            try:
                customized = resume_edit.apply_edits(customized, fallback_ops)
            except ValueError as exc:
                raise ValueError(
                    "Tailoring produced invalid keyword-survival fallback ops: "
                    f"{exc}"
                ) from exc
    return customized


def tailor(
    session_id: UUID,
    *,
    session: Session | None = None,
    user_prompt: str | None = None,
    ops: list[ResumeEdit] | None = None,
) -> TailoringSession:
    """Resolutions -> edit ops -> Application -> tailored ATS score, atomically.

    Two ways to produce the edit ops, then a shared mechanical tail:
      - Default (``ops=None``): the backend builds the tailor prompt from the
        session's actionable resolutions and calls the LLM to generate the ops.
      - Caller-supplied (``ops`` non-empty): Claude (via MCP) has already produced
        its own typed edit ops. The backend skips the resolution bundle, the
        actionable guard, the prompt build, and its own LLM call entirely, and
        applies the caller's ops directly. Claude's judgment IS the tailor.
    Both paths converge on the same apply -> application reuse-or-insert -> score
    tail below.

    Nothing is committed before this function's OWN commit at the end: the
    application is only flushed, the session-row mutations are staged, and
    score_target stages the tailored score row on the same session, so the
    explicit commit below is the single transaction boundary. Any failure up to
    and including scoring leaves no application row and the session open with
    its resolutions intact (the caller's rollback discards the staged state).

    Op-to-resolution correspondence is enforced by prompt only; the compare view
    and the raw editor are the user's audit surface for edits beyond the mandate.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        tailoring = session.get(TailoringSession, session_id)
        if tailoring is None:
            raise ValueError(f"Tailoring session not found: {session_id}")
        if tailoring.status != "open":
            raise SessionNotOpenError(
                f"Tailoring session {session_id} is not open (status={tailoring.status!r})"
            )
        _require_fresh(tailoring, session)

        # Both paths edit the base resume; load it once up front.
        base = load_base_resume(tailoring.base_resume, session)
        pre_ops, handled_pre_ops, already_applied = _deterministic_pre_ops(
            tailoring.resolutions_json
        )
        if pre_ops:
            try:
                base = resume_edit.apply_edits(base, pre_ops)
            except ValueError as exc:
                raise ValueError(
                    f"Tailoring produced invalid deterministic pre-ops: {exc}"
                ) from exc

        # LLM path only: the caller-ops path never consults resolutions to
        # build its ops (Claude's ops are authoritative), so a stale stored
        # resolution there is inert.
        if not ops:
            _reject_stale_placements(tailoring, base)

        # Explicit request value wins; the note stored on the session is the
        # fallback (finding F#12), so a tailor with no request prompt still
        # honors what the user typed on the gap page. Resolved for both paths so
        # the application row records the effective prompt either way.
        user_prompt = (
            (user_prompt or "").strip()
            or (tailoring.user_prompt or "").strip()
            or None
        )

        if ops:
            # Caller supplied its own already-validated typed ops: skip the
            # resolution bundle, the actionable guard, the prompt build, and the
            # backend LLM call. Apply them through the SAME error mapping the LLM
            # path uses so a bad op surfaces as a clean 400, not a raw traceback.
            try:
                customized = resume_edit.apply_edits(base, list(ops))
            except ValueError as exc:
                raise ValueError(f"Tailoring produced invalid edit ops: {exc}") from exc
        else:
            actionable, skipped, already_applied = _resolution_bundle(
                tailoring, already_applied
            )
            if not actionable and not pre_ops:
                raise ValueError("No actionable resolutions to tailor")

            if not actionable:
                customized = base
            else:
                customized = _llm_customized(
                    session,
                    tailoring,
                    base,
                    actionable,
                    skipped,
                    already_applied,
                    user_prompt,
                )

        # Re-tailoring must REUSE the job's existing application for this base
        # rather than orphan it: the job page surfaces only the newest application,
        # so a second INSERT would strand the prior application's studio edits,
        # rendered PDF, Q&A, and applied-status (finding F#4). Update the stored
        # draft (customized_json + user_prompt) and drop the now-stale rendered
        # artifacts, but PRESERVE status, applied_at, notes,
        # referral_id, and the Q&A rows keyed to this application_id.
        existing = session.scalar(
            select(Application)
            .where(
                Application.job_id == tailoring.job_id,
                Application.base_resume == tailoring.base_resume,
            )
            .order_by(Application.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            existing.user_prompt = user_prompt
            application = existing
        else:
            application = Application(
                job_id=tailoring.job_id,
                base_resume=tailoring.base_resume,
                status="draft",
                user_prompt=user_prompt,
            )
            session.add(application)
        # Shared write-tail: stages the draft + version row and hands back the
        # stale artifact paths — disk removal waits until after the commit below.
        stale, _ = application_writes.stage_resume_update(
            session,
            application,
            customized,
            source="tailor",
            source_ref=str(session_id),
        )
        for item in handled_pre_ops:
            if item.get("action") != "port_kb_point":
                continue
            payload = item.get("payload") or {}
            point = session.get(KBPoint, UUID(str(payload["kb_point_id"])))
            if point is None:
                raise ValueError(
                    f"KB point no longer exists: {payload['kb_point_id']}"
                )
            target = payload["placement_target"]
            session.add(
                KBPortLog(
                    entity_id=point.entity_id,
                    point_id=point.id,
                    resume_kind="application",
                    resume_key=str(application.id),
                    section=target["section"],
                    ported_text=payload["wording"],
                    # Model contract (career_kb.py): NULL = verbatim port, where
                    # ported_text doubles as the snapshot; set only when adapted.
                    source_text=None if payload["wording"] == point.text else point.text,
                    direction="to_resume",
                )
            )

        # Flywheel write-back: staged here so it rides the same single commit.
        # The skip list travels up on the response (transient attribute below).
        writeback_skips = _write_back_elicited_points(session, tailoring, base)

        # Stage the session transition BEFORE scoring, then commit ONCE:
        # application + session update + score row land in one transaction.
        tailoring.status = "tailored"
        tailoring.application_id = application.id

        ats_score.score_target(
            tailoring.job_id,
            "application",
            str(application.id),
            phase="tailored",
            session=session,
        )
        session.commit()

        session.refresh(tailoring)
        # Non-persisted, transient instance attribute (same pattern as
        # create_session's health_warning): the router folds it into
        # TailorResponse.kb_writeback_skips. Set AFTER refresh so the reload
        # doesn't clear it.
        tailoring.kb_writeback_skips = writeback_skips
        artifacts.remove_files(stale)
        return tailoring
    finally:
        if owns_session:
            session.close()
