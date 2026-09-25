"""The fill loop's asks, keyed by `fid` both ways."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Shape = Literal["text", "date", "select", "group", "search", "popup"]
Route = Literal["slot", "free_text", "low_stakes", "none", "blocked"]
Reason = Literal["matched", "closest", "assumed", "abstained"]
MAX_FIELDS = 40
MAX_MAP_OPTIONS = 30
MAX_PICK_OPTIONS = 250  # Jev Choice ceiling 255 incl. `none`
# The no-match key every pick question adds (autofill_choose.NO_OPTION). A page
# option may never be offered under it, or "no option states it" and that
# option would be one answer.
RESERVED_OID = "none"


class Selector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: UUID | None = None
    base: str | None = Field(default=None, max_length=200)
    # e.g. "rec_linkedin" read from the apply page's ?source= by the extension.
    source_hint: str | None = Field(default=None, max_length=60)


class MapField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(min_length=1, max_length=64)
    question: str = Field(max_length=300)
    section: str | None = Field(default=None, max_length=200)
    repeat_index: int = Field(default=0, ge=0, le=20)
    shape: Shape
    multi: bool = False
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=MAX_MAP_OPTIONS)


class MapRequest(Selector):
    fields: list[MapField] = Field(min_length=1, max_length=MAX_FIELDS)


class Mapped(BaseModel):
    route: Route
    slot: str | None = None
    value: str | list[str] | None = None  # to the LOCAL extension only


class MapResponse(BaseModel):
    fields: dict[str, Mapped]


class PickOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    oid: str = Field(min_length=1, max_length=16)
    text: str = Field(max_length=300)

    @field_validator("oid")
    @classmethod
    def _not_the_no_match_key(cls, oid: str) -> str:
        if oid == RESERVED_OID:
            raise ValueError(f'"{RESERVED_OID}" is reserved for "no option states it"')
        return oid


class PickField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(min_length=1, max_length=64)
    question: str = Field(max_length=300)
    route: Literal["slot", "low_stakes"]
    slot: str | None = Field(default=None, max_length=120)
    item: str | None = Field(default=None, max_length=300)  # one member of a set slot
    options: list[PickOption] = Field(min_length=1, max_length=MAX_PICK_OPTIONS)
    complete: bool = True


class PickRequest(Selector):
    fields: list[PickField] = Field(min_length=1, max_length=MAX_FIELDS)


class Picked(BaseModel):
    oids: list[str]
    reason: Reason


class PickResponse(BaseModel):
    picks: dict[str, Picked]


# ---------- /step: the next move for a field the generic path could not finish

MAX_STEP_CANDIDATES = 60
MAX_STEP_HISTORY = 8
# The structural injection guard: only ids shaped like the ones the page's code
# generates get in — never an option's text, never a free-form instruction.
MOVE_ID = r"^(click:o\d+|search:value|search:word:\d|open|scroll|close|give_up)$"


class StepCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mid: str = Field(max_length=40, pattern=MOVE_ID)
    describe: str = Field(max_length=320)


class StepRequest(Selector):
    fid: str = Field(min_length=1, max_length=64)
    question: str = Field(max_length=300)
    route: Literal["slot", "low_stakes"]
    slot: str | None = Field(default=None, max_length=120)
    item: str | None = Field(default=None, max_length=300)  # one member of a set slot
    history: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=MAX_STEP_HISTORY)
    candidates: list[StepCandidate] = Field(min_length=1, max_length=MAX_STEP_CANDIDATES)
    # True only when every option is in view (the page says so) — a closest
    # match over a capped, unscrolled or filtered list is never allowed.
    complete: bool = False

    @field_validator("candidates")
    @classmethod
    def _one_of_each(cls, candidates: list[StepCandidate]) -> list[StepCandidate]:
        mids = [c.mid for c in candidates]
        if len(set(mids)) != len(mids):
            raise ValueError("each move id is offered once")
        return candidates


class StepResponse(BaseModel):
    mid: str | None
    # A click that commits: matched / closest / assumed. Any other move that
    # clears the progress floor: matched. `abstained` (mid None) = give up.
    reason: Reason
