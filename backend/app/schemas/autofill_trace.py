"""The stored fill trace of one Companion run, shaped to keep answers out.

SYSTEM.md {#inv-autofill-telemetry-no-values}: no answer value, typed text, prompt or profile
word enters a trace. Every string is a closed enum, a lowercase-only word, a dotted fact NAME,
a move id, a hash, a hostname pattern or a run id, except the page's own question text:
`label`, `section` and `options` hold what the page shows (the same text the field
observations already keep), length-capped but not pattern-checked. The extension is what keeps
a typed answer out of those three; the schema bounds everything else.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.autofill_fill import (
    FID,
    MAX_PICK_OPTIONS,
    MOVE_ID,
    Engine,
    PolarityWay,
    Route,
    Second,
    Shape,
    StepReason,
    Why,
)

Op = Literal["map", "polarity", "pick", "step",  # decisions
             "explore", "choose", "set", "write", "move",  # page actions
             "sweep", "recipe"]
Effect = Literal["progress", "no_effect", "unexpected", "reverted", "unconfirmed", "refused", "late", "error"]
WORD = r"^[a-z_]{1,40}$"  # a page word or a status: lowercase only, so a value cannot hide in it
SLOT = r"^[a-z_]+(\.[a-z0-9_]+)*$"  # a fact NAME (autofill_catalog), never its value
MAX_RUN_FIELDS, MAX_FIELD_STEPS, LABEL_MAX, MAX_OPTION_COUNT = 200, 40, 200, 5000


class TraceStep(BaseModel):
    """One decision (a model call or code path) or one page action on a field."""

    model_config = ConfigDict(extra="forbid")
    op: Op
    ms: int | None = Field(default=None, ge=0, le=600_000)  # page action OR model-call latency
    effect: Effect | None = None  # page actions
    word: str | None = Field(default=None, pattern=WORD)  # the page's outcome/reason word
    route: Route | None = None  # map
    slot: str | None = Field(default=None, max_length=120, pattern=SLOT)  # a fact NAME
    why: Why | None = None
    engine: Engine | None = None
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    floor: float | None = Field(default=None, ge=0.0, le=1.0)
    second: Second | None = None
    first_p: float | None = Field(default=None, ge=0.0, le=1.0)
    first_same: bool | None = None
    chose_none: bool | None = None  # the model's top choice was the no-answer key (see DecisionTrace)
    way: PolarityWay | None = None  # polarity
    # index into the options offered to /pick (not TraceField.options, which is capped)
    option: int | None = Field(default=None, ge=0, lt=MAX_PICK_OPTIONS)
    reason: StepReason | None = None  # pick / step
    move: str | None = Field(default=None, max_length=40, pattern=MOVE_ID)  # op step / move


class TraceField(BaseModel):
    """One form field's journey through a run: what it was, each step taken and how it ended.

    `options` is capped at 30 entries; `option_count` is the page's FULL option count.
    """

    model_config = ConfigDict(extra="forbid")
    fid: str = Field(max_length=64, pattern=FID)
    label: str = Field(default="", max_length=LABEL_MAX)
    label_source: str | None = Field(default=None, max_length=40, pattern=r"^[a-z-]+$")
    shape: Shape | Literal["unknown"]
    section: str | None = Field(default=None, max_length=LABEL_MAX)
    required: bool = False
    options: list[Annotated[str, Field(max_length=LABEL_MAX)]] | None = Field(default=None, max_length=30)
    option_count: int = Field(default=0, ge=0, le=MAX_OPTION_COUNT)
    family: str | None = Field(default=None, max_length=32, pattern=r"^f:[0-9a-z]{1,24}$")
    steps: list[TraceStep] = Field(default_factory=list, max_length=MAX_FIELD_STEPS)
    outcome: str = Field(pattern=WORD)
    round: int = Field(default=0, ge=0, le=10)


class RunTrace(BaseModel):
    """A whole run, built by the extension and stored whole (`AutofillRun.trace`)."""

    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-z-]{8,64}$")
    host: str = Field(pattern=r"^[a-z0-9.-]{1,253}(:\d{1,5})?$")  # a hostname, optionally with a port: lowercase / punycode
    started_at: AwareDatetime
    ended_at: AwareDatetime
    mode: Literal["assist"] = "assist"  # only "Saved answers + AI" runs the loop (panel/actions/fill.js:458)
    halted: Literal["stopped", "timeout"] | None = None
    rounds: int = Field(default=0, ge=0, le=10)
    fields: list[TraceField] = Field(max_length=MAX_RUN_FIELDS)
