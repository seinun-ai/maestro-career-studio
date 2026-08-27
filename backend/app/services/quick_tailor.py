"""Quick Tailor: the profile-planned tailor and its orchestration seam.

Three parts: the preference profile (which auto-resolution moves quick tailor
may make, plus a standing instruction — a typed `JsonSetting`, so callers
always see the full frozen shape),
the per-gap resolution planner, and the two orchestration entry points the
routers adapt (one-shot from a job; fill-from-checkpoint on an open session)."""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclasses_field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.schemas.quick_tailor import QuickTailorProfile
from app.services import (
    application_render,
    ats_score,
    kb_resolver,
    placement_targets,
    tailoring_session,
)
from app.services.json_settings import JsonSetting

logger = logging.getLogger(__name__)

QUICK_TAILOR = JsonSetting(
    "quick_tailor_profile", "quick_tailor.json", QuickTailorProfile
)
QUICK_TAILOR_KEY = QUICK_TAILOR.key
QUICK_TAILOR_FILE = QUICK_TAILOR.filename
# DERIVED from the model, never a second list. The planner and its tests take a
# plain dict, and this is the full default profile in that form.
DEFAULTS: dict[str, Any] = QuickTailorProfile().model_dump()


def get_profile(session: Session | None = None) -> dict[str, Any]:
    """The stored profile, as a dict.

    Storage and shape are typed (`QuickTailorProfile`); the planner below and
    its tests still read the profile with `.get(...)`, so the boundary hands
    back a plain dict rather than rippling a model through the tailoring
    engine. Field defaults do the work the old DEFAULTS dict did, and
    pydantic's default `extra="ignore"` drops the retired `default_base_resume`
    key without a hand-maintained list of removals.
    """
    return QUICK_TAILOR.get(session).model_dump()


def set_profile(
    profile: dict[str, Any], session: Session | None = None
) -> dict[str, Any]:
    return QUICK_TAILOR.set(
        QuickTailorProfile.model_validate(profile), session
    ).model_dump()


def plan_resolutions(
    gaps_json: dict[str, Any], profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Preference-driven auto-resolution over a session's frozen gaps_json.

    Returns (resolutions covering EVERY gap — undecided ones as skip, so the
    tailor prompt's do-not-touch list is complete), plus human-readable lines
    for the moves actually planned. Honesty invariant: a missing (absent) skill
    is only ever planned into the skills section, regardless of enrichment —
    save_resolutions re-enforces this server-side as defense in depth.
    """
    resolutions: list[dict[str, Any]] = []
    applied: list[str] = []
    for category in gaps_json.get("categories", []):
        for gap in category.get("gaps", []):
            resolution, line = _plan_gap(category.get("key"), gap, profile)
            resolutions.append(resolution)
            if line:
                applied.append(line)
    return resolutions, applied


def _skip(gap: dict[str, Any]) -> dict[str, Any]:
    return {"gap_id": gap["gap_id"], "action": "skip"}


def _plan_gap(
    category_key: str | None, gap: dict[str, Any], profile: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    actions = set(gap.get("actions") or [])
    enrichment = gap.get("enrichment") or {}

    auto_resolution = kb_resolver.auto_resolution_for_gap(gap)
    if auto_resolution is not None:
        payload = auto_resolution.get("payload") or {}
        source = (payload.get("provenance") or {}).get("source")
        # Which user switch governs an auto keyword add: a wording_auto is the
        # mirror-wording hygiene move, so the mirror_wording switch owns it; a
        # kb_profile auto adds an unevidenced-on-resume keyword into skills, so
        # keywords_into_skills owns it. enable/port autos carry dated-entry
        # evidence and are not what either switch is about.
        if auto_resolution["action"] != "add_keyword":
            allowed = True
        elif source == "wording_auto":
            allowed = bool(profile.get("mirror_wording"))
        else:
            allowed = bool(profile.get("keywords_into_skills"))
        if allowed:
            action = auto_resolution["action"]
            skill = gap.get("jd_skill") or ""
            if action == "enable_entry":
                line = f"Enabled library entry '{payload.get('name') or skill}'"
            elif action == "port_kb_point":
                line = f"Ported library evidence for '{skill}'"
            elif source == "wording_auto":
                target = (payload.get("placement_target") or {}).get(
                    "index_or_category"
                )
                line = f"Mirrored JD wording '{skill}' in skills ({target})"
            else:
                line = f"Added verified profile skill '{skill}'"
            return auto_resolution, line

    if (
        category_key == "missing_skills"
        and profile.get("keywords_into_skills")
        and "add_keyword" in actions
    ):
        # ALWAYS section=skills (honesty invariant). Enrichment is consulted only
        # for WHICH skills category; anything else falls back to the frontend's
        # literal "Additional Skills" bucket (always a valid skills placement).
        target = placement_targets.ADDITIONAL_SKILLS
        suggested = enrichment.get("suggested_placement") or {}
        if suggested.get("section") == "skills" and isinstance(
            suggested.get("index_or_category"), str
        ):
            target = suggested["index_or_category"]
        skill = gap.get("jd_skill") or ""
        return (
            {
                "gap_id": gap["gap_id"],
                "action": "add_keyword",
                "payload": {
                    "placement_target": {
                        "section": "skills",
                        "index_or_category": target,
                    },
                    "wording": skill,
                },
            },
            f"Added '{skill}' to skills ({target})",
        )

    # In practice this branch now serves dual_place: a mirror_wording gap plans
    # its deterministic skills add via the wording_auto path above (same switch),
    # so only dual_place — whose fix is prose corroboration at the enriched
    # placement — still needs the enrichment-placed keyword injection.
    if (
        category_key in ("mirror_wording", "dual_place")
        and profile.get("mirror_wording")
        and "add_keyword" in actions
    ):
        placement = enrichment.get("suggested_placement")
        if not placement:
            return _skip(gap), None
        if placement.get("section") == "projects" and not profile.get(
            "project_keyword_injection"
        ):
            return _skip(gap), None
        skill = gap.get("jd_skill") or ""
        return (
            {
                "gap_id": gap["gap_id"],
                "action": "add_keyword",
                "payload": {"placement_target": placement, "wording": skill},
            },
            f"Mirrored JD wording '{skill}' in {placement.get('section')}",
        )

    if (
        gap.get("kind") in ("summary", "title")
        and profile.get("summary_rename")
        and "user_input" in actions
    ):
        wording = enrichment.get("suggested_wording")
        if isinstance(wording, str) and wording.strip():
            return (
                {
                    "gap_id": gap["gap_id"],
                    "action": "user_input",
                    "payload": {"text": wording},
                },
                "Refreshed the summary/title toward the JD",
            )
        return _skip(gap), None

    return _skip(gap), None


# --- Orchestration ----------------------------------------------------------
# The Quick Tailor seam: both entry points below own the composition the two
# routers used to hand-roll separately (jobs.quick_tailor_job and the gap
# page's apply_profile branch). Routers translate typed exceptions to HTTP and
# nothing else. Commit topology: save_resolutions commits, then tailor()
# commits once at its own end — one user action, two commits, a pinned
# contract (the gap page's refetch behavior depends on the fill landing
# even when the tailor then fails).


class InProgressSessionError(Exception):
    """An open session for (job, base) carries hand-made resolutions.

    System-planned auto-resolutions (payload.provenance set by the KB resolver
    at session creation) are NOT user work: an untouched-but-enriched session
    must not permanently block quick tailor. Only hand-made resolutions count —
    create_session unconditionally supersedes prior open sessions, so a user's
    in-progress custom session would be permanently orphaned even if quick
    tailor then failed. Block instead and let them decide."""


class SessionCreateInvalidError(ValueError):
    """create_session rejected the request (unknown base resume and kin).

    A distinct subclass because the one-shot endpoint maps the create phase to
    422 while tailor-phase ValueErrors stay 400 — without the split, the router
    could not tell the phases apart."""


@dataclass
class QuickTailorOutcome:
    session_id: UUID
    nothing_to_tailor: bool = False
    application_id: UUID | None = None
    compare: tuple[float, float] | None = None  # (before, after) composites
    applied: list[str] = dataclasses_field(default_factory=list)
    pdf_ready: bool = False
    health_warning: str | None = None


def _is_user_work(res: dict[str, Any]) -> bool:
    return res.get("action") != "skip" and not (res.get("payload") or {}).get(
        "provenance"
    )


def _instruction_fallback(profile: dict[str, Any]) -> str | None:
    """The profile's standing instruction, as a FALLBACK user prompt only.

    tailor() lets an explicit request prompt beat the session's stored note, so
    the instruction must never override either — the extension's Fast tailor
    and the gap page's quick tailor share this one saved setting, and it must
    not mean two different things depending on where it was invoked."""
    return (profile.get("instruction") or "").strip() or None


def run_for_job(
    job_id: UUID, base_resume: str, *, session: Session
) -> QuickTailorOutcome:
    """One-shot Quick Tailor: guard -> create session -> plan from the saved
    profile -> save -> tailor -> compare -> render.

    The failure policy lives here, not in the routers: compare and render
    failures only DEGRADE the outcome (the tailor is already committed by
    then); everything before the tailor propagates as a typed exception."""
    if session.get(Job, job_id) is None:
        raise LookupError("Job not found")

    open_sessions = session.scalars(
        select(TailoringSession).where(
            TailoringSession.job_id == job_id,
            TailoringSession.base_resume == base_resume,
            TailoringSession.status == "open",
        )
    ).all()
    if any(
        any(_is_user_work(res) for res in (s.resolutions_json or []))
        for s in open_sessions
    ):
        raise InProgressSessionError(
            "An in-progress tailoring session with saved resolutions exists for "
            "this job and base resume. Finish or close it in the web app, or run "
            "quick tailor after discarding it."
        )

    profile = get_profile(session)
    try:
        created = tailoring_session.create_session(job_id, base_resume, session=session)
    except tailoring_session.HealthGateBlockedError:
        raise
    except ValueError as exc:
        raise SessionCreateInvalidError(str(exc)) from exc

    # Transient instance attribute set by create_session after refresh (SYSTEM.md
    # §12); capture it once so BOTH return paths surface it.
    health_warning = getattr(created, "health_warning", None)

    resolutions, applied = plan_resolutions(created.gaps_json, profile)
    # A pre-stored cannot_confirm is the user's standing "I can't confirm this"
    # — the profile plan must not resurrect the claim it suppresses, and the
    # replace=True save below would otherwise wipe it.
    suppressed = {
        r["gap_id"]: r
        for r in (created.resolutions_json or [])
        if r.get("action") == "cannot_confirm"
    }
    if suppressed:
        resolutions = [suppressed.get(item["gap_id"], item) for item in resolutions]
    if not any(
        item["action"] not in ("skip", "cannot_confirm") for item in resolutions
    ):
        return QuickTailorOutcome(
            session_id=created.id,
            nothing_to_tailor=True,
            health_warning=health_warning,
        )

    tailoring_session.save_resolutions(
        created.id, resolutions, session=session, replace=True
    )
    row = tailoring_session.tailor(
        created.id, session=session, user_prompt=_instruction_fallback(profile)
    )

    compare: tuple[float, float] | None = None
    try:
        result = ats_score.compare(row.application_id, session=session)
        compare = (
            float(result["base"].composite),
            float(result["tailored"].composite),
        )
    except Exception as exc:
        # Tailor is already committed; a compare failure only degrades the
        # outcome (compare stays None), mirroring the render degradation below.
        logger.warning("quick-tailor compare failed for job %s: %s", job_id, exc)

    pdf_ready = True
    try:
        application_render.render_resume(session, row.application_id)
    except Exception:
        # Tailor is already committed; a render failure only degrades the
        # outcome. render_resume persisted application.render_error itself,
        # which is where the UI reads the failure.
        pdf_ready = False

    return QuickTailorOutcome(
        session_id=row.id,
        application_id=row.application_id,
        compare=compare,
        applied=applied,
        pdf_ready=pdf_ready,
        health_warning=health_warning,
    )


def fill_checkpoint_session(
    row: TailoringSession, *, session: Session, request_prompt: str | None = None
) -> str | None:
    """Quick tailor from the review checkpoint: fill every UNRESOLVED gap from
    the saved profile, then hand back the prompt tailor() should receive.

    Deliberately runs BEFORE tailor() and not inside it — save_resolutions
    commits, and tailor() owns its own separate commit. Routing the
    fill through save_resolutions (rather than writing resolutions_json
    directly) is what keeps the honesty gate on this path. Existing resolutions
    always win: a stored decision, whether the user's or a pre-stored auto, is
    never overwritten or retracted.

    The returned prompt applies the instruction fallback only when neither the
    request nor the session carries a note (see _instruction_fallback)."""
    profile = get_profile(session)
    planned, _ = plan_resolutions(row.gaps_json, profile)
    resolved_ids = {item.get("gap_id") for item in (row.resolutions_json or [])}
    fill = [item for item in planned if item.get("gap_id") not in resolved_ids]
    if fill:
        tailoring_session.save_resolutions(row.id, fill, session=session)
    if not (request_prompt or "").strip() and not (row.user_prompt or "").strip():
        return _instruction_fallback(profile)
    return request_prompt
