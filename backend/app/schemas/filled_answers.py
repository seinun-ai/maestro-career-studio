"""The answer receipt's wire shapes: what a page run filled, and what reads it back.

`source` says where an answer came from, in the words of the job page's pill: profile (the
autofill profile), resume (a work-history entry or the skills), custom (a saved answer),
written (prose the AI wrote), inferred (an AI choice no saved fact states, or a derived fact),
you (typed or changed by you), upload (a file put in an upload box). Phase 4's auto-submit rule
reads these values: they are a frozen vocabulary.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Source = Literal["profile", "resume", "custom", "written", "inferred", "you", "upload"]
Channel = Literal["companion", "agent"]
FlagId = Literal["guessed_screening", "ticked_everything", "differs_from_profile",
                 "eeo_without_saved_answer"]
UPLOAD_SLOTS = ("resume", "cover_letter")

MAX_FIELDS = 300
MAX_ANSWER_CHARS = 20000
MAX_ITEMS = 100
MAX_ITEM_CHARS = 500


class FilledField(BaseModel):
    """One field as a writer reports it. A multi-select's answer is a list."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    section: str | None = Field(default=None, max_length=200)
    required: bool = False
    answer: str | list[str] | None = None
    options_count: int | None = Field(default=None, ge=0, le=1000)
    source: Source
    slot: str | None = Field(default=None, max_length=120)
    eeo: bool = False
    edited_by_you: bool = False

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a question has words")
        return value

    @field_validator("answer", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        """A number a writer typed ("5") arrives as one: store its text rather than refuse the run."""
        def one(item: Any) -> Any:
            return str(item) if isinstance(item, (int, float)) and not isinstance(item, bool) else item
        return [one(item) for item in value] if isinstance(value, list) else one(value)

    @field_validator("answer")
    @classmethod
    def _bounded(cls, value: str | list[str] | None) -> str | list[str] | None:
        if isinstance(value, list):
            if len(value) > MAX_ITEMS or any(len(item) > MAX_ITEM_CHARS for item in value):
                raise ValueError(f"at most {MAX_ITEMS} items of {MAX_ITEM_CHARS} characters")
        elif isinstance(value, str) and len(value) > MAX_ANSWER_CHARS:
            raise ValueError(f"at most {MAX_ANSWER_CHARS} characters")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "FilledField":
        if self.source == "upload" and self.slot not in UPLOAD_SLOTS:
            raise ValueError("an upload's slot is resume or cover_letter")
        if self.options_count is not None and isinstance(self.answer, str):
            raise ValueError("options_count counts the options of a list answer")
        return self


class FilledAnswersCreate(BaseModel):
    """One page run. `host` defaults to the job's own when a writer sends none."""

    model_config = ConfigDict(extra="forbid")

    channel: Channel
    host: str | None = Field(default=None, max_length=255)
    step: str | None = Field(default=None, max_length=300)
    application_id: UUID | None = None
    base_resume: str | None = Field(default=None, max_length=120)
    fields: list[FilledField] = Field(min_length=1, max_length=MAX_FIELDS)


class FlagRead(BaseModel):
    id: FlagId
    reason: str


class FlaggedIndex(BaseModel):
    """A flagged field of the run just posted, by its place in the request's `fields`."""

    index: int
    question: str
    section: str | None = None
    flags: list[FlagRead]


class FilledAnswersPosted(BaseModel):
    id: UUID
    application_id: UUID | None = None
    flag_count: int
    flags: list[FlaggedIndex]


class FilledFieldRead(BaseModel):
    question: str
    section: str | None = None
    required: bool = False
    answer: str | list[str] | None = None
    options_count: int | None = None
    source: Source
    slot: str | None = None
    eeo: bool = False
    eeo_answered: bool = False
    edited_by_you: bool = False
    version: int | None = None
    flags: list[FlagRead] = []


class FilledSection(BaseModel):
    section: str | None = None
    fields: list[FilledFieldRead]


class FilledStep(BaseModel):
    step: str | None = None
    host: str | None = None
    channel: Channel
    captured_at: datetime
    sections: list[FilledSection]


class FilledAnswersRead(BaseModel):
    """The job's receipt: per question the latest answer, grouped by step and section."""

    job_id: UUID
    host: str | None = None
    pages: int = 0
    captured_at: datetime | None = None
    flag_count: int = 0
    steps: list[FilledStep] = []
