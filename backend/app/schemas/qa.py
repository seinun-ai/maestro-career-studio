from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CoverLetterRequest(BaseModel):
    tone: str = "balanced"


class QARequest(BaseModel):
    model_config = {"extra": "forbid"}

    application_id: UUID | None = None
    job_id: UUID | None = None
    #: Which base resume a JOB-level answer is written from. Ignored when
    #: `application_id` is given — an application already names the resume it
    #: was tailored from, and a second opinion about that is not the caller's to
    #: hold. Absent, the job path falls back to its generic default.
    base: str | None = None
    questions: list[str] | None = None
    cover_letter: CoverLetterRequest | None = None


class QAResponse(BaseModel):
    answers: list[str] | None = None
    cover_letter: str | None = None


class QARegenerateRequest(BaseModel):
    tone: str | None = None


class QAEntryUpdate(BaseModel):
    answer: str


class QAEntryRead(BaseModel):
    id: UUID
    application_id: UUID
    kind: str
    prompt: str | None = None
    answer: str | None = None
    model_used: str | None = None
    pdf_path: str | None = None
    # Transient, never a column: the render route sets it on the ORM row after
    # commit (the `resolved_engine` precedent on base resumes). Non-null ONLY
    # when the cover letter's engine was substituted because TeX is absent;
    # says why, in the words the user sees.
    render_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
