import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.types import JSONDoc, UTCDateTime, UUIDType
from app.db import Base


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    __table_args__ = (
        Index("ix_consent_events_proposal_id", "proposal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("application_proposals.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_manifest_json: Mapped[list | None] = mapped_column(JSONDoc)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
