"""The fill loop's asks, keyed by `fid` both ways."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Shape = Literal["text", "date", "select", "group", "search", "popup"]
# `reasoned`: a choice answered from the work and education history only
# (autofill_map._answerable, autofill_pick._reason), marked `assumed`.
Route = Literal["slot", "free_text", "low_stakes", "reasoned", "none", "blocked"]
# How a written value compares with what the page shows (`date`: a date the
# Companion narrows to the part a Month, Day or Year control holds): decided by
# the fact's SLOT (autofill_map.format_of), never by what the value looks like.
Format = Literal["phone", "money", "date"]
# The profile lists whose entries /sections places (by what the page's entries
# hold) and /map writes by profile entry. The loop's PLACED_KINDS mirrors it.
# A Websites entry's profile entry k is the k-th URL the profile holds
# (autofill_catalog.websites).
EntryKind = Literal["experience", "education", "languages", "websites"]
# The highest entry index a field may carry (its page entry, or its profile
# entry). The loop's MAX_ENTRY_INDEX mirrors it.
MAX_ENTRY_INDEX = 20
Reason = Literal["matched", "closest", "assumed", "abstained"]


# ---------- decision traces (value-free)

# How a model decided an answer: value-free by construction (enums and numbers), returned
# beside /map, /pick and /step answers for the run trace (docs/plans/2026-10-02-fill-trace-design.md).
Engine = Literal["jev", "fast"]
Second = Literal["asked", "decided"]  # asked: it ran and did not change the answer; decided: its answer stands
PolarityWay = Literal["same", "opposite", "neither", "unsure"]


class DecisionFields(BaseModel):
    """The seven value-free fields of how a model decided, shared by the live `DecisionTrace` and the
    stored `TraceStep`."""

    model_config = ConfigDict(extra="forbid")
    engine: Engine | None = None  # None: no model's decision is recorded here (a code path)
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    floor: float | None = Field(default=None, ge=0.0, le=1.0)
    second: Second | None = None
    # With second == "decided": `first_p` is the FIRST engine's probability for its own top
    # choice (the second opinion runs only when it abstained, so that choice is often "none"
    # or give_up), and `first_same` is whether that top choice was the answer that now
    # stands. Only agreeing cases are evidence that a lower floor would have been safe (the
    # calibration goal).
    first_p: float | None = Field(default=None, ge=0.0, le=1.0)
    first_same: bool | None = None
    # Whether the model's top choice was a key that means "no answer": map none,
    # history_unanswered, protected_unanswered, or blocked_eeo once EEO is consented; pick `none`
    # or no oid; step give_up or no move. So "sure there is nothing" reads differently from "its
    # option fell under the floor". False: it chose a real slot, option or move. None: nothing
    # readable came back (a choice that was not offered counts as unreadable), or no model was asked.
    chose_none: bool | None = None


class DecisionTrace(DecisionFields):
    """What /map, /pick and /step say of one decision."""


class PolarityTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    way: PolarityWay
    engine: Engine | None = None
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    # Set only when this way was recalled from memory (autofill_polarity): the same decision as an
    # earlier call's, not a new one. Absent for a fresh decision.
    remembered: bool | None = None


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
    repeat_index: int = Field(default=0, ge=0, le=MAX_ENTRY_INDEX)
    # The profile entry /sections placed this field's entry at (its `order`),
    # by what the page's entries hold. ABSENT: no placement, page order stands.
    # NULL: an entry holding something the profile does not have, or past the
    # profile's entries — nothing of the profile's goes into it.
    profile_entry: int | None = Field(default=None, ge=0, le=MAX_ENTRY_INDEX)
    # The kind of profile entry the section holds, sent with `profile_entry`: an
    # entry fact of another kind is not this entry's (routed none).
    entry_kind: EntryKind | None = None
    shape: Shape
    multi: bool = False
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=MAX_MAP_OPTIONS)


class MapRequest(Selector):
    fields: list[MapField] = Field(min_length=1, max_length=MAX_FIELDS)


# Why a field the profile could answer was left (route "none"): `unclear_job`,
# an end date /map could not tie to the entry's job (autofill_map._one_job_per_entry).
Why = Literal["unclear_job"]


class Mapped(BaseModel):
    route: Route
    slot: str | None = None
    value: str | list[str] | None = None  # to the LOCAL extension only
    format: Format | None = None
    why: Why | None = None
    trace: DecisionTrace | None = None


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
    route: Literal["slot", "low_stakes", "reasoned"]
    slot: str | None = Field(default=None, max_length=120)
    item: str | None = Field(default=None, max_length=300)  # one member of a set slot
    options: list[PickOption] = Field(min_length=1, max_length=MAX_PICK_OPTIONS)
    complete: bool = True


class PickRequest(Selector):
    fields: list[PickField] = Field(min_length=1, max_length=MAX_FIELDS)


class Picked(BaseModel):
    oids: list[str]
    reason: Reason
    trace: DecisionTrace | None = None
    polarity: PolarityTrace | None = None


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
    trace: DecisionTrace | None = None
    polarity: PolarityTrace | None = None


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
    # Why none is added although the profile has more, or why the section is
    # left alone: the page cannot be reconciled with the profile.
    # held_twice: two entries hold the same profile entry, and an added
    # one would not be safe. held_unmatched: an entry holds something the
    # profile does not have — the whole section is placed nowhere, left to the
    # user, whatever there was to add. ambiguous_kind: another section on
    # the page reads as the same job, school, language or website list, and which one
    # is misread cannot be told — neither is placed (every entry null) and
    # neither grows.
    reason: Literal["held_twice", "held_unmatched", "ambiguous_kind"] | None = None
    # Jobs, schools, languages and websites only (EntryKind): per page entry, then per
    # entry to add, the profile entry (its catalog index) that entry holds or
    # is given — null for one the profile does not have. Numbers, never
    # values; /map places by it (`MapField.profile_entry`).
    order: list[int | None] | None = None


class SectionsResponse(BaseModel):
    sections: dict[str, SectionPlan]
