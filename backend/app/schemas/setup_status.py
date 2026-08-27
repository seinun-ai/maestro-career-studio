from typing import Any

from pydantic import BaseModel


class GroupCompleteness(BaseModel):
    answered: int
    answerable: int


class AutofillStep(BaseModel):
    done: bool
    readiness: float  # 0.0-1.0 over required groups
    groups: dict[str, GroupCompleteness]
    blocking: list[str]  # group keys whose gaps are knockout-grade (work_auth)


class SetupStep(BaseModel):
    done: bool
    detail: dict[str, Any] = {}


class SuggestedBase(BaseModel):
    role_category: str
    label: str


class SetupStatus(BaseModel):
    # First because it blocks everything: with no provider key there is no
    # extraction, no tailoring and no chat.
    model_key: SetupStep
    import_resumes: SetupStep
    autofill: AutofillStep
    job_preferences: SetupStep
    persona: SetupStep
    template: SetupStep
    suggested_bases: list[SuggestedBase]
    complete: bool
