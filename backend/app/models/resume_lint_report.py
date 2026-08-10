import uuid

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ResumeLintReport(Base):
    """A stored health-check run for one resume; newest row is the live report."""

    __tablename__ = "resume_lint_reports"
    __table_args__ = (
        Index("ix_resume_lint_reports_resume", "resume_kind", "resume_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resume_kind: Mapped[str] = mapped_column(Text, nullable=False)  # 'base' | 'application'
    resume_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Version of the resume content that was analyzed (null if none recorded yet).
    resume_version_number: Mapped[int | None] = mapped_column(Integer)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)      # e.g. "health-v2"
    features_json: Mapped[dict | None] = mapped_column(JSONB)    # levels/tier/zones for band re-tuning
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
