from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BaseResume(Base):
    __tablename__ = "base_resumes"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    # The role this resume targets — same vocabulary as Job.role_category
    # (services/role_categories), so the two axes cross-tab with `=`.
    # NOT NULL with an 'unknown' default rather than a required create field:
    # the documented onboarding path drops JSON straight into base_resumes/ and
    # reaches seeding.py without ever touching the API, so a REST-only validator
    # would not hold. "unknown" is a visible state the UI offers to fix, never a
    # silent guess.
    role_category: Mapped[str] = mapped_column(
        Text, nullable=False, default="unknown", server_default="unknown"
    )
    data_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    tex_path: Mapped[str | None] = mapped_column(Text)
    pdf_rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    formatting_json: Mapped[dict | None] = mapped_column(JSONB)
    template_id: Mapped[str | None] = mapped_column(Text)
    pdf_pages: Mapped[int | None] = mapped_column(Integer)
    render_error: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Hidden from every PICK surface but fully resolvable: archiving a stale
    # career track must never break its editor, its version history, or an
    # application that already references it. See
    # services/base_resume_data.active_ vs selectable_base_resume_slugs.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
