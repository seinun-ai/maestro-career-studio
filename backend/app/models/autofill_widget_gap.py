import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import UTCDateTime, UUIDType, utcnow


class AutofillWidgetGap(Base):
    """A kind of widget the engine could not operate, or that the user filled by hand.

    The engine's to-do list, kept apart from the run traces so it outlives their 50-run limit.
    Privacy: a recipe-book family hash, a shape, an outcome word and a count. NO label, value or
    option text, by schema ({#inv-autofill-telemetry-no-values}). `host` and the timestamps still
    record where and when you applied, so the table is cleared with the telemetry rows.
    """

    __tablename__ = "autofill_widget_gaps"
    __table_args__ = (
        UniqueConstraint("family", "host", "shape", "outcome", name="uq_autofill_widget_gaps_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    family: Mapped[str] = mapped_column(String(24), nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    shape: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
