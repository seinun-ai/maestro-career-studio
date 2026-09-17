import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.types import JSONDoc, UTCDateTime, UUIDType
from app.db import Base


class AutofillFieldObservation(Base):
    """One row per unique form-field signature seen by the extension.

    Privacy: there is deliberately NO value/answer column — the schema itself
    is the backstop (design doc 2026-07-22, 'Privacy line (hard)').
    """

    __tablename__ = "autofill_field_observations"
    __table_args__ = (
        UniqueConstraint(
            "signature_hash",
            name="uq_autofill_field_observations_signature_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSONDoc)
    rule_id: Mapped[str | None] = mapped_column(Text)
    outcomes: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_marks: Mapped[list] = mapped_column(JSONDoc, nullable=False, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
