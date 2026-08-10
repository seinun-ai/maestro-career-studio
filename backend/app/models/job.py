import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from app.db import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("raw_text_hash", name="uq_jobs_raw_text_hash"),
        Index("ix_jobs_role_category_level", "role_category", "level"),
        Index("ix_jobs_state", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    extracted_json: Mapped[dict | None] = mapped_column(JSONB)
    title: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    # ATS requisition/job identifier (Workday R-…/JR…, Greenhouse/Lever ids).
    # (company, requisition_id) identifies a posting across job boards (G11).
    requisition_id: Mapped[str | None] = mapped_column(Text)
    role_category: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(Text)
    work_mode: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    location_raw: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric)
    salary_period: Mapped[str | None] = mapped_column(Text)
    # ISO 4217 (USD/GBP/EUR/…). Nullable: ~40%+ of US and ~88% of German
    # postings carry no pay at all, and a posting may legally hyperlink a pay
    # page (IL 820 ILCS 112/10(b-25)) instead of stating numbers.
    salary_currency: Mapped[str | None] = mapped_column(Text)
    salary_source_url: Mapped[str | None] = mapped_column(Text)
    work_authorization: Mapped[str | None] = mapped_column(Text)
    opt_accepted: Mapped[str | None] = mapped_column(Text)
    years_experience_min: Mapped[int | None] = mapped_column(Integer)
    years_experience_max: Mapped[int | None] = mapped_column(Integer)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disqualifying_for_opt: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=expression.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
