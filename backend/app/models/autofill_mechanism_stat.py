from datetime import datetime

from sqlalchemy import Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, utcnow


class AutofillMechanismStat(Base):
    """Counters folded from run traces, one row per mechanism key.

    Privacy: the key and the counts name a mechanism (engine, route, outcome), never a host,
    a label or a value, so the table outlives clearing the runs. `created_at` is when the key was
    first counted, so the oldest one says how far back the counters reach.
    """

    __tablename__ = "autofill_mechanism_stats"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    counts: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )
