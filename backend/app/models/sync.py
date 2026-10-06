"""Local sync clocks, job deletion receipts and requests for the other copy."""

import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, UUIDType, utcnow


class SyncState(Base):
    __tablename__ = "sync_state"

    name: Mapped[str] = mapped_column(String, primary_key=True)  # clock | profile_rev
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class SyncTombstone(Base):
    __tablename__ = "sync_tombstones"

    job_id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True)
    rev: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )


class SyncRequest(Base):
    __tablename__ = "sync_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # No FK: the referenced job may be absent or its replica may be replaced.
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    origin: Mapped[str] = mapped_column(String(8), nullable=False, default="local")
