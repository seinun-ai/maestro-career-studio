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


class ResumeVersionLabelPatch(BaseModel):
    label: str | None = None
