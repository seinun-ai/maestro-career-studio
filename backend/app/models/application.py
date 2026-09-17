import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.types import JSONDoc, UTCDateTime, UUIDType
from app.db import Base

if TYPE_CHECKING:
    from app.models.qa_entry import QAEntry


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_job_id_base_resume", "job_id", "base_resume"),
        Index("ix_applications_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    base_resume: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    status: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    notes: Mapped[str | None] = mapped_column(Text)
    customized_json: Mapped[dict | None] = mapped_column(JSONDoc)
    formatting_json: Mapped[dict | None] = mapped_column(JSONDoc)
    template_id: Mapped[str | None] = mapped_column(Text)
    pdf_pages: Mapped[int | None] = mapped_column(Integer)
    render_error: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    tex_path: Mapped[str | None] = mapped_column(Text)
    artifact_dir: Mapped[str | None] = mapped_column(Text)
    referral_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(as_uuid=True),
        ForeignKey("referrals.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_prompt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    qa_entries: Mapped[list["QAEntry"]] = relationship(
        "QAEntry",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
