from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ResumeVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resume_kind: str
    resume_key: str
    version_number: int
    parent_version_id: UUID | None = None
    summary: str | None = None
    source: str
    source_ref: str | None = None
    label: str | None = None
    created_at: datetime


class ResumeVersionDetail(ResumeVersionSummary):
    snapshot: dict[str, Any]
    diff: list[dict[str, Any]]


class ResumeVersionRestoreResult(ResumeVersionSummary):
    """POST /restore — the new version, plus how the live resume was rendered.

    A base restore re-renders the PDF, so this is a render response; an
    application restore renders nothing (the PDF comes on an explicit Render)
    and leaves the note null.
    """

    # Transient, see BaseResumeDetail.render_note.
    render_note: str | None = None
    # The restore is committed before the render, so a render failure is
    # reported here (and persisted on the row) instead of failing the call.
    # The two are alternatives: a failed render substituted nothing.
    render_error: str | None = None


class ResumeVersionLabelPatch(BaseModel):
    label: str | None = None
