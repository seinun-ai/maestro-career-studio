from datetime import datetime

from sqlalchemy import Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.types import JSONDoc, UTCDateTime, utcnow
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
    # The user's own words for the role this resume targets, when the tag is
    # free text. NULL means the tag IS role_category (a catalog pick), so
    # existing rows need no backfill. Display prefers this; machines keep
    # joining on role_category, which becomes the projection: the confirmed
    # mapping, `other` for deliberately-unmapped free text (the YAML defines
    # `other` as "a real role that matches no category"), `unknown` only for
    # never-tagged. See the round-2 design doc for the four-state table.
    role_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_json: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    tex_path: Mapped[str | None] = mapped_column(Text)
    pdf_rendered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    formatting_json: Mapped[dict | None] = mapped_column(JSONDoc)
    template_id: Mapped[str | None] = mapped_column(Text)
    pdf_pages: Mapped[int | None] = mapped_column(Integer)
    render_error: Mapped[str | None] = mapped_column(Text)
    # render_note is deliberately NOT a column: a transient set by
    # base_resume_render after commit (see schemas/base_resume.py).
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Hidden from every PICK surface but fully resolvable: archiving a stale
    # career track must never break its editor, its version history, or an
    # application that already references it. See
    # services/base_resume_data.active_ vs selectable_base_resume_slugs.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_kb_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )
