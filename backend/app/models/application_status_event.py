import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import UTCDateTime, UUIDType, utcnow


class ApplicationStatusEvent(Base):
    """One status change on an application: what it became, when, and who said so. Read by Analytics
    (funnel, time to hear back) and Today (quiet for 14 days). `backfilled` rows were made by the
    migration from the status an application already had: their `at` is its last update, not when the
    status changed, so timing metrics skip them (they still count for status).

    Written only by `services/application_status.set_status`, which lists the `source` words. The rows
    belong to their application's job: they travel in its sync bundle and leave with it (ON DELETE
    CASCADE, and `Application.status_events`)."""

    __tablename__ = "application_status_events"
    __table_args__ = (Index("ix_status_events_app_at", "application_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    backfilled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
