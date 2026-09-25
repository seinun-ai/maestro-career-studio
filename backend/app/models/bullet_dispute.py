from datetime import datetime

from sqlalchemy import Boolean, Integer, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, utcnow


class BulletDispute(Base):
    """User reading of one exact text, independent of its ordinary evaluation."""
    __tablename__ = "bullet_disputes"

    content_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    note: Mapped[str] = mapped_column(Text)
    original_json: Mapped[dict] = mapped_column(JSONDoc)
    revised_json: Mapped[dict] = mapped_column(JSONDoc)
    reply: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    metric_unavailable: Mapped[bool] = mapped_column(Boolean, server_default=false())
    rubric_version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
