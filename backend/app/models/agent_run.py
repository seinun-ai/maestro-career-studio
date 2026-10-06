import uuid
from datetime import datetime

from sqlalchemy import Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, UUIDType, utcnow


class AgentRun(Base):
    """One automation run an agent reported (MCP `record_run`): what it was, how it ended, its
    counts, its digest and the jobs it touched. Read by the Agent inbox's Recent runs panel and
    the Automations page's Last ran line. Only the newest `services/agent_runs.MAX_RUNS` rows
    are kept. The digest is the agent's own text: Maestro cannot check what it holds
    (docs/entities/agent-runs.md)."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_finished_at", "finished_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    automation: Mapped[str] = mapped_column(Text, nullable=False)  # card id or a custom name
    outcome: Mapped[str] = mapped_column(Text, nullable=False)  # "ok" | "partial" | "failed"
    agent: Mapped[str | None] = mapped_column(Text)  # the MCP client's name, raw
    machine: Mapped[str | None] = mapped_column(String(32))  # NULL means it ran here
    finished_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    counts: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)
    digest: Mapped[str] = mapped_column(Text, nullable=False, default="")
    job_ids: Mapped[list] = mapped_column(JSONDoc, nullable=False, default=list)
