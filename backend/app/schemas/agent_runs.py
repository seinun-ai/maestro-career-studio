"""The run log's wire shapes (MCP `record_run`, the Agent inbox's Recent runs panel).

Count keys and outcomes are a frozen vocabulary: the panel words them and phase 4 reads them.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

RunOutcome = Literal["ok", "partial", "failed"]
RunCountKey = Literal["found", "proposed", "skipped", "tailored", "updated", "needs_you"]
MAX_DIGEST = 2000
MAX_JOB_IDS = 50


class AgentRunCreate(BaseModel):
    """One finished run. A long digest or job list is trimmed, never refused."""

    model_config = ConfigDict(extra="forbid")

    automation: str = Field(min_length=1, max_length=40)
    outcome: RunOutcome
    counts: dict[RunCountKey, Annotated[StrictInt, Field(ge=0)]] = Field(default_factory=dict)
    digest: str = ""
    job_ids: list[UUID] = Field(default_factory=list)

    @field_validator("automation")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("an automation has a name")
        return value.strip()

    @field_validator("digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        value = value.strip()
        return value if len(value) <= MAX_DIGEST else value[: MAX_DIGEST - 1] + "…"

    @field_validator("job_ids")
    @classmethod
    def _jobs(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))[:MAX_JOB_IDS]


class AgentRunJob(BaseModel):
    id: UUID
    title: str | None = None
    company: str | None = None


class AgentRunRead(BaseModel):
    id: UUID
    automation: str
    title: str
    outcome: RunOutcome
    agent: str | None = None
    on_bot: bool = False
    finished_at: datetime
    counts: dict[str, int]
    digest: str
    jobs: list[AgentRunJob]


class RefusedJobRequest(BaseModel):
    """Browser-safe request outcome: never carries the request payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID | None = None
    reason: str | None = None
    answered_at: datetime | None = None


class AgentRunList(BaseModel):
    items: list[AgentRunRead]
