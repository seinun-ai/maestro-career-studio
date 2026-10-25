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
    # Each apply-in market's work-permit answers ("UK"), summed in groups["work_auth"].
    work_auth_by_country: dict[str, GroupCompleteness] = {}


class SetupStep(BaseModel):
    done: bool
    detail: dict[str, Any] = {}


class SuggestedBase(BaseModel):
    role_category: str
    label: str


class EngineProbe(BaseModel):
    model_config = {"from_attributes": True}

    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    reason: str | None = None
    warning: str | None = None


class EnginesProbe(BaseModel):
    model_config = {"from_attributes": True}

    pdflatex: EngineProbe
    typst: EngineProbe


class SetupStatus(BaseModel):
    # First because it blocks everything: with no provider key there is no
    # extraction, no tailoring and no chat.
    model_key: SetupStep
    import_resumes: SetupStep
    autofill: AutofillStep
    job_preferences: SetupStep
    persona: SetupStep
    template: SetupStep
    # Which PDF engines this backend can run. Informational: never part of
    # `complete` (Typst is always shipped, so a PDF is always possible).
    engines: EnginesProbe
    suggested_bases: list[SuggestedBase]
    # The shipped demo resume's slug while it is still offered: a starting point, never the
    # user's own resume, so no agent or screen recommends tailoring it.
    demo_bases: list[str] = []
    complete: bool
