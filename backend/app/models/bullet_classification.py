from datetime import datetime

from sqlalchemy import DateTime, Float, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BulletClassification(Base):
    """Evidence-ladder classification cache, keyed by content hash.

    Editing a bullet changes its hash, so stale judgments (and stale user
    overrides) simply stop matching — no invalidation logic needed.
    """
    __tablename__ = "bullet_classifications"

    content_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    level: Mapped[str] = mapped_column(Text)  # direct|analogue|adjacent|implied|unaddressed
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    override_level: Mapped[str | None] = mapped_column(Text)  # user override wins
    override_reason: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
