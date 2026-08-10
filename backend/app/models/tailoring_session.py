import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TailoringSession(Base):
    __tablename__ = "tailoring_sessions"
    __table_args__ = (Index("ix_tailoring_sessions_job_id", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    base_resume: Mapped[str] = mapped_column(Text, nullable=False)
    # open | tailored | superseded (newer session created) | abandoned (closed)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    gaps_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resolutions_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Content hashes captured at creation (sha256 of canonical JSON). gaps_json
    # is frozen against these inputs; a mismatch later means the session is
    # STALE (base edited / JD re-extracted) and mutations must be rejected.
    # NULL on legacy rows = staleness unknown, treated as fresh.
    base_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_extraction_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional "how should this be tailored?" note that persists on the session
    # (survives reloads, prefills the gap page) and falls back into tailor().
    user_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    base_ats_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ats_scores.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
