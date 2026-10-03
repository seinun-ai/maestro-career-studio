import uuid
from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, UUIDType, utcnow


class AutofillRun(Base):
    """One stored trace per Companion fill run, keyed by the run id the extension minted.

    Privacy: the `trace` document is a validated `RunTrace`, value-free by schema (no answer,
    typed text, prompt or profile word; SYSTEM.md {#inv-autofill-telemetry-no-values}). `host`
    and the timestamps still record where and when you applied, so the table is clearable.
    """

    __tablename__ = "autofill_runs"
    __table_args__ = (UniqueConstraint("run_id", name="uq_autofill_runs_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    trace: Mapped[dict] = mapped_column(JSONDoc, nullable=False)
