import uuid
from datetime import datetime

from sqlalchemy import Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.types import UTCDateTime, UUIDType

from app.db import Base


class HealthGateWaiver(Base):
    """User-waived health gate; persists across re-analyses (design hatch #4)."""
    __tablename__ = "health_gate_waivers"
    __table_args__ = (
        UniqueConstraint("resume_kind", "resume_key", "gate_id", name="uq_health_waiver"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_kind: Mapped[str] = mapped_column(Text)   # 'base' | 'application'
    resume_key: Mapped[str] = mapped_column(Text)
    gate_id: Mapped[str] = mapped_column(Text)        # 'S1'..'S5', 'C1', 'C2'
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
