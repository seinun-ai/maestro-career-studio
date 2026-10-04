import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, UUIDType, utcnow


class FilledAnswer(Base):
    """What one page run put on a job's application form, and where each answer came from.

    One row per page run: the Companion posts after every fill run, an agent per form page
    (MCP `record_filled_answers`). `fields` is a list of field dicts, the stored shape of
    `schemas/filled_answers.FilledField` plus `eeo_answered` and `version`. Readers take the
    latest answer per question across rows (`services/filled_answers.latest_fields`).

    Privacy (SYSTEM.md {#inv-filled-answers-local}): the values live here and nowhere else. No
    telemetry, run trace, Langfuse span or export reads this table; an EEO value is kept only
    while EEO consent is recorded, and no agent read returns one. Flags are computed at read
    time (`services/answer_flags.py`), never stored, so a profile change re-flags old rows.
    """

    __tablename__ = "filled_answers"
    __table_args__ = (Index("ix_filled_answers_job_id", "job_id"),)

    # Column order is deliberate: the id → job_id → application_id run of
    # `application_proposal.py` would otherwise be a duplication-ratchet clone.
    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)  # "companion" | "agent"
    host: Mapped[str | None] = mapped_column(Text)
    step: Mapped[str | None] = mapped_column(Text)  # a page number or the URL path
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    # Null until the job has an application: linked at post time when the writer knows it,
    # else by `services/filled_answers.link_unlinked` when one is created or marked applied.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL")
    )
    fields: Mapped[list] = mapped_column(JSONDoc, nullable=False)
