import uuid

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ResumeVersion(Base):
    """Append-only snapshot history of resume content.

    One row per write to a base resume's data_json or an application's
    customized_json. `resume_key` is a soft reference (slug or application UUID
    string) so soft-deleted resumes keep their history.
    """

    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint(
            "resume_kind", "resume_key", "version_number", name="uq_resume_versions_identity"
        ),
        Index("ix_resume_versions_resume", "resume_kind", "resume_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resume_kind: Mapped[str] = mapped_column(Text, nullable=False)  # 'base' | 'application'
    resume_key: Mapped[str] = mapped_column(Text, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    # 'create' | 'form_edit' | 'edit_ops' | 'chat' | 'tailor' | 'import' | 'restore'
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
