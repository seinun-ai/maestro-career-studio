from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BulletRewrite(Base):
    """Unattended (context="") rewrite cache, keyed by the same content hash
    as BulletClassification.

    A row means the unattended rewrite was attempted. ``rewrite_text`` is the
    passing rewrite, or NULL when the guard rejected both attempts ("tried,
    ask"). Absence of a row is "never tried". Invalidation is free: new text
    → new hash → miss.
    """

    __tablename__ = "bullet_rewrites"

    content_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    rewrite_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
