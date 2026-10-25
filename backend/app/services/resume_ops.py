"""The ONE apply-typed-ops pipeline for every surface (SYSTEM.md §11 #2).

Four surfaces apply typed edit ops to a resume: the REST edit endpoints
(base_resumes PATCH /{slug}/edits, applications PATCH /{id}/edits), the MCP
tools that wrap those endpoints, and the in-app chat's edit tool. They used
to carry three hand-rolled copies of the persist → version → render/artifact
tail (audit C37), which drifted (chat swallowed render errors silently; the
pre-commit-unlink bug had to be fixed twice). This module is now the single
implementation.

Boundary responsibilities stay at the boundary: pydantic op validation,
scope/authorization checks, and HTTP/ToolError mapping. Everything from
apply_edits onward lives here.
"""
import json
import logging
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.resume_version import ResumeVersion
from app.schemas.resume_edit import ResumeEdit
from app.services import artifacts, base_resume_render, resume_voice
from app.services.application_writes import stage_resume_update
from app.services.resume_edit import apply_edits

logger = logging.getLogger(__name__)


def refuse_third_person(before: dict, after: dict) -> None:
    """Agent or model text never stores a blocking third-person line (§6 inv-resume-voice):
    what the edit wrote or changed is checked, the owner's own lines are not. changed_hits
    compares by position, so an owner line that a removal moved up a slot is excused: it
    appears no more often than before. A copy of it into another bullet is not excused."""
    held = Counter(text for _, text in resume_voice.slots(before))
    now = Counter(text for _, text in resume_voice.slots(after))
    problems = [
        problem
        for problem in resume_voice.changed_hits(before, after, summary_always=False)
        if now[problem[1]] > held[problem[1]]
    ]
    if problems:
        raise ValueError(resume_voice.ops_error(problems))


def edit_base(
    db: Session,
    row: BaseResume,
    ops: list[ResumeEdit],
    *,
    source: str,
    source_ref: str | None = None,
    template_id: str | None = None,
    refuse_voice: bool = False,
) -> tuple[BaseResume, ResumeVersion, str | None, list[dict]]:
    """Apply ops to a base resume: persist + version + file write + tolerant
    re-render. Returns (row, version, render_error, applied).

    Raises ValueError for invalid ops (callers map to 400 / ToolError) and
    LookupError for an unknown explicit template_id. Render failures NEVER
    fail the edit: the edit is committed first, and any compile/render
    problem — including an extras-incompatible template — degrades to a
    persisted render_error (stale-PDF banner). A 4xx after the commit would
    push clients to retry already-applied ops, double-applying additive ones.
    `refuse_voice` (agent and model text) raises ValueError, before any write, on a
    third-person line the ops wrote.
    """
    applied: list[dict] = []
    data_dict = apply_edits(row.data_json, ops, applied=applied)  # ValueError propagates
    if refuse_voice:
        refuse_third_person(row.data_json, data_dict)

    from app.services.resume_versions import record_version

    row.data_json = data_dict
    version = record_version(
        db, "base", row.slug, data_dict, source=source, source_ref=source_ref
    )
    db.commit()
    db.refresh(row)

    base_dir = Path(settings.base_resumes_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"{row.slug}.json").write_text(
        json.dumps(data_dict, indent=2), encoding="utf-8"
    )

    render_error: str | None = None
    try:
        base_resume_render.render_base_resume(row.slug, db, template_id=template_id)
    except LookupError:
        raise  # unknown explicit template_id -> caller's 404
    except Exception as e:  # noqa: BLE001 — the data write succeeded; PDF goes stale
        logger.warning(
            "PDF re-render failed after %s edits for %s", source, row.slug, exc_info=True
        )
        render_error = str(e)
    if render_error is not None:
        row = base_resume_render.record_render_error(db, row.slug, render_error)
    db.refresh(row)
    return row, version, render_error, applied


def edit_application(
    db: Session,
    application: Application,
    ops: list[ResumeEdit],
    *,
    baseline: dict,
    source: str,
    source_ref: str | None = None,
    refuse_voice: bool = False,
) -> tuple[Application, ResumeVersion, list[dict]]:
    """Apply ops to an application draft via the staged write-tail (version
    row + artifact refs cleared in-transaction, files removed only after the
    commit). ``baseline`` is what the ops apply against — the current draft,
    or the base snapshot on the REST fallback path. Returns (application,
    version, applied). ValueError (invalid ops, or a third-person line under
    `refuse_voice`) propagates for the caller to map.
    """
    applied: list[dict] = []
    customized = apply_edits(baseline, ops, applied=applied)  # ValueError propagates
    if refuse_voice:
        refuse_third_person(baseline, customized)
    stale, version = stage_resume_update(
        db, application, customized, source=source, source_ref=source_ref
    )
    db.commit()
    db.refresh(application)
    artifacts.remove_files(stale)
    return application, version, applied
