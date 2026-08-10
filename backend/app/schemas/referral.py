from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class ReferralCreate(BaseModel):
    company: str
    careers_url: HttpUrl
    contact_name: str | None = None
    notes: str | None = None


class ReferralPatch(BaseModel):
    company: str | None = None
    careers_url: HttpUrl | None = None
    contact_name: str | None = None
    notes: str | None = None


class ReferralRead(BaseModel):
    id: UUID
    company: str
    careers_url: str
    contact_name: str | None = None
    notes: str | None = None
    applications_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
