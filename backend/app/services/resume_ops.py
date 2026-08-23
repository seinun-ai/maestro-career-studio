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
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.resume_version import ResumeVersion
from app.schemas.resume_edit import ResumeEdit
from app.services import artifacts, base_resume_render, pdf_render
from app.services.application_writes import stage_resume_update
from app.services.resume_edit import apply_edits

logger = logging.getLogger(__name__)


def edit_base(
    db: Session,
    row: BaseResume,
    ops: list[ResumeEdit],
    *,
    source: str,
    source_ref: str | None = None,
    template_id: str | None = None,
) -> tuple[BaseResume, ResumeVersion, str | None, list[dict]]:
    """Apply ops to a base resume: persist + version + file write + tolerant
    re-render. Returns (row, version, render_error, applied).

    Raises ValueError for invalid ops (callers map to 400 / ToolError) and
    LookupError for an unknown explicit template_id. Render failures NEVER
    fail the edit: the edit is committed first, and any compile/render
    problem — including an extras-incompatible template — degrades to a
    persisted render_error (stale-PDF banner). A 4xx after the commit would
    push clients to retry already-applied ops, double-applying additive ones.
    """
    applied: list[dict] = []
    data_dict = apply_edits(row.data_json, ops, applied=applied)  # ValueError propagates

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
        db.rollback()
        row = db.get(BaseResume, row.slug)
        row.render_error = pdf_render.extract_render_error(render_error)
        db.commit()
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
) -> tuple[Application, ResumeVersion, list[dict]]:
    """Apply ops to an application draft via the staged write-tail (version
    row + artifact refs cleared in-transaction, files removed only after the
    commit). ``baseline`` is what the ops apply against — the current draft,
    or the base snapshot on the REST fallback path. Returns (application,
    version, applied). ValueError (invalid ops) propagates for the caller to map.
    """
    applied: list[dict] = []
    customized = apply_edits(baseline, ops, applied=applied)  # ValueError propagates
    stale, version = stage_resume_update(
        db, application, customized, source=source, source_ref=source_ref
    )
    db.commit()
    db.refresh(application)
    artifacts.remove_files(stale)
    return application, version, applied
