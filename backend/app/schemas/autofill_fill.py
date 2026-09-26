"""The fill loop's asks, keyed by `fid` both ways."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Shape = Literal["text", "date", "select", "group", "search", "popup"]
Route = Literal["slot", "free_text", "low_stakes", "none", "blocked"]
# How a written value compares with what the page shows: decided by the fact's
# SLOT (autofill_map.format_of), never by what the value looks like.
Format = Literal["phone", "money"]
Reason = Literal["matched", "closest", "assumed", "abstained"]
MAX_FIELDS = 40
MAX_MAP_OPTIONS = 30
MAX_PICK_OPTIONS = 250  # Jev Choice ceiling 255 incl. `none`
# The no-match key every pick question adds (autofill_choose.NO_OPTION). A page
# option may never be offered under it, or "no option states it" and that
# option would be one answer.
RESERVED_OID = "none"
# The extension's field id, `<frame>-<n>` (content/inventory.js).
FID = r"^[A-Za-z0-9_-]{1,64}$"


class Selector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: UUID | None = None
    base: str | None = Field(default=None, max_length=200)
    # e.g. "rec_linkedin" read from the apply page's ?source= by the extension.
    source_hint: str | None = Field(default=None, max_length=60)
    # The browser's own date: "today" is the applicant's, and the server may
    # run on UTC. Taken only within a day of the server's (routers/autofill).
    today: date | None = None


class MapField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(min_length=1, max_length=64, pattern=FID)
    question: str = Field(max_length=300)
    section: str | None = Field(default=None, max_length=200)
    repeat_index: int = Field(default=0, ge=0, le=20)
    # The profile entry /sections placed this field's entry at (its `order`),
    # by what the page's entries hold. ABSENT: no placement, page order stands.
    # NULL: an entry holding something the profile does not have, or past the
    # profile's entries — nothing of the profile's goes into it.
    entry_slot: int | None = Field(default=None, ge=0, le=20)
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
    format: Format | None = None


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
    fid: str = Field(min_length=1, max_length=64, pattern=FID)
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
MOVE_ID = r"^(click:o\d+|search:value|search:word:\d|open|scroll|give_up)$"
# A history entry is built by the loop from a move id (or the generic `choose`)
# and its outcome, with an optional reason — never from page text.
HISTORY_ENTRY = (r"^(click:o\d+|search:value|search:word:\d|open|scroll|close|give_up|choose)"
                 r" -> [a-z_]+( \([a-z_]+\))?$")
# Reasons a /step answer can carry: /pick's, plus `progress` for a move that is
# not an answer (open, search, scroll, or opening a group of options).
StepReason = Literal["matched", "closest", "assumed", "progress", "abstained"]


class StepCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mid: str = Field(max_length=40, pattern=MOVE_ID)
    describe: str = Field(min_length=1, max_length=320)


class StepRequest(Selector):
    fid: str = Field(min_length=1, max_length=64, pattern=FID)
    question: str = Field(max_length=300)
    route: Literal["slot", "low_stakes"]
    slot: str | None = Field(default=None, max_length=120)
    item: str | None = Field(default=None, max_length=300)  # one member of a set slot
    history: list[Annotated[str, Field(max_length=80, pattern=HISTORY_ENTRY)]] = Field(
        default_factory=list, max_length=MAX_STEP_HISTORY)
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
    # A click on an answer: matched / closest / assumed. A move that is not an
    # answer (open, search, scroll, open a group) and clears the progress
    # floor: progress. `abstained` (mid None) = give up.
    reason: StepReason


# ---------- /sections: what each repeating section lists, and how many entries the profile can fill

MAX_SECTIONS = 20
MAX_ENTRIES = 50
MAX_HELD = 10  # committed values read per entry
HELD_CHARS = 200
# The profile lists a repeating section can hold; `none` for anything else
# (Skills, Resume/CV, a section the model is unsure of).
SectionKind = Literal["experience", "education", "languages", "websites", "certifications", "none"]


class PageSection(BaseModel):
    """A section as the page reads it: its heading, its counts, and what each
    entry already HOLDS (`held`) — values, read by THIS local backend only to
    match entries to profile entries, never passed to a model."""

    model_config = ConfigDict(extra="forbid")
    # `<frame>-s<n>` (content/sections.js), shaped like a fid.
    sid: str = Field(min_length=1, max_length=64, pattern=FID)
    heading: str = Field(max_length=200)
    entries: int = Field(ge=0, le=MAX_ENTRIES)
    # Per entry, whether it already holds any committed value.
    filled: list[bool] = Field(default_factory=list, max_length=MAX_ENTRIES)
    # Per entry, the committed values of its answered fields.
    held: list[Annotated[list[Annotated[str, Field(max_length=HELD_CHARS)]], Field(max_length=MAX_HELD)]] = Field(
        default_factory=list, max_length=MAX_ENTRIES)


class SectionsRequest(Selector):
    sections: list[PageSection] = Field(min_length=1, max_length=MAX_SECTIONS)


class SectionPlan(BaseModel):
    kind: SectionKind
    # How many entries the section should have: the loop presses Add only up
    # to this many. An added entry takes a profile entry holding every fact it
    # would REQUIRE, never more.
    wanted: int = Field(ge=0)
    # Why none is added although the profile has more: an entry on the page
    # holds something the profile does not have, or two hold the same one, so
    # the page cannot be reconciled with the profile.
    reason: Literal["held_out_of_order"] | None = None
    # Jobs and schools only: per page entry, then per entry to add, the profile
    # entry (its catalog index) that entry holds or is given — null for one the
    # profile does not have. Numbers, never values; /map places by it
    # (`MapField.entry_slot`).
    order: list[int | None] | None = None


class SectionsResponse(BaseModel):
    sections: dict[str, SectionPlan]
