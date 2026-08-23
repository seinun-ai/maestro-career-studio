"""Request/response models for base-resume → Career KB sync."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SyncItemOut(BaseModel):
    tier: str
    section: str
    entity_id: UUID | None = None
    entity_proposal: dict[str, Any] | None = None
    matched_point_id: UUID | None = None
    text: str


class SyncStatus(BaseModel):
    items: list[SyncItemOut] = Field(default_factory=list)
    skills_new: list[str] = Field(default_factory=list)
    # Open map, so the service owns the tier vocabulary. "recorded_drift" —
    # drift the KB already documents — rides here and is pinned by a wire test.
    counts: dict[str, int] = Field(default_factory=dict)
    last_kb_synced_at: datetime | None = None


class SyncResult(BaseModel):
    created: int
    drifted: int
    # Entities this sync RENAMED, because the base resume carried a strictly
    # richer form of a role title that near-matched. Empty on an ordinary sync;
    # here so the one write that changes an existing entity is not silent.
    renamed: list[str] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    # CATEGORY names, one per category written — the long-standing port-report
    # shape. Never count these: two new skills in one category is one entry.
    skills: list[str] = Field(default_factory=list)
    # The individual skills that landed in the profile — the one to count when
    # summarising a sync.
    skills_added: list[str] = Field(default_factory=list)
    last_kb_synced_at: datetime | None = None
