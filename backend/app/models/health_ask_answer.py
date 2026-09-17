import uuid
from datetime import datetime

from sqlalchemy import Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.types import UTCDateTime, UUIDType
from app.db import Base


class HealthAskAnswer(Base):
    """Typed health-report answers, persisted before the rewrite LLM call.

    Upserted on (resume_kind, resume_key, finding_id). ``suggestion`` is null
    until a guarded rewrite succeeds; a 422 still keeps the answer.
    """

    __tablename__ = "health_ask_answers"
    __table_args__ = (
        UniqueConstraint(
            "resume_kind",
            "resume_key",
            "finding_id",
            name="uq_health_ask_answer",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resume_kind: Mapped[str] = mapped_column(Text)  # 'base' | 'application'
    resume_key: Mapped[str] = mapped_column(Text)
    finding_id: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
