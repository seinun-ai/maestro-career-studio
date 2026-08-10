from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class AtsRunRequest(BaseModel):
    job_id: UUID
    target_type: Literal["base_resume", "application"] | None = None
    target_id: str | None = None
    phase: Literal["base", "tailored"] | None = None


class AtsScoreRead(BaseModel):
    id: UUID
    job_id: UUID
    target_type: str
    target_id: str
    application_id: UUID | None = None
    phase: str
    composite: float
    subscores_json: dict[str, Any]
    skill_table_json: list[dict[str, Any]]
    config_version: str
    engine_version: str
    created_at: datetime
    jd_skills_extracted_count: int = 0
    jd_skills_matched_count: int = 0
    coverage_ratio: float = 0.0
    coverage_warning: str | None = None

    model_config = {"from_attributes": True}


class AtsCompareRead(BaseModel):
    application_id: UUID
    base: AtsScoreRead
    tailored: AtsScoreRead
    delta: dict[str, Any]
    skill_diff: list[dict[str, Any]]
