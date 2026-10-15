"""The stored fill trace of one Companion run, shaped to keep answers out.

SYSTEM.md {#inv-autofill-telemetry-no-values}: no answer value, typed text, prompt or profile
word enters a trace. Every string is a closed enum, a lowercase-only word, a dotted fact NAME,
a move id, a hash, a hostname pattern or a run id, except the page's own question text:
`label`, `section` and `options` hold what the page shows (the same text the field
observations already keep), length-capped but not pattern-checked. The extension is what keeps
a typed answer out of those three; the schema bounds everything else.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.autofill_fill import (
    FID,
    DecisionFields,
    MAX_PICK_OPTIONS,
    MOVE_ID,
    PolarityWay,
    Route,
    Shape,
    StepReason,
    Why,
)
from app.schemas.autofill_reason import (
    HISTORY,
    SIGNATURE,
    MAX_BUTTONS,
    MAX_ERRORS,
    MAX_EXCLUDED,
    MAX_FIELDS as MAX_SNAPSHOT_FIELDS,
    MAX_HISTORY,
    MAX_TABS,
    NOTE_MAX,
    RejectCode,
    SnapButton,
    SnapError,
    SnapField,
    SnapTab,
    Stuck,
    TARGET,
)

Op = Literal["map", "polarity", "pick", "step",  # decisions
             "explore", "choose", "set", "write", "move",  # page actions
             "sweep", "recipe"]
Effect = Literal["progress", "no_effect", "unexpected", "reverted", "unconfirmed", "refused", "late", "error", "took_back"]
WORD = r"^[a-z_]{1,40}$"  # a page word or a status: lowercase only, so a value cannot hide in it
SLOT = r"^[a-z_]+(\.[a-z0-9_]+)*$"  # a fact NAME (autofill_catalog), never its value
MAX_RUN_FIELDS, MAX_FIELD_STEPS, LABEL_MAX, MAX_OPTION_COUNT = 200, 40, 200, 5000
MAX_REASON_ROUNDS, MAX_REASON_ACTIONS, MAX_REASON_REJECTS = 3, 3, 10
MODEL = r"^[A-Za-z0-9._:/-]{1,120}$"
SNAPSHOT_CHARS = 120_000   # one round's stored snapshot, as JSON: the extension caps it far under, this is the backstop
ReasonType = Literal["fill", "answer_from", "write", "choose", "retry", "redo", "close_dialog", "press_next",
                     "follow_tab", "ask_user"]
ReasonOutcome = Literal["progress", "no_effect", "moved", "refused", "rejected", "asked"]
ReasonStop = Literal["moved", "resolved", "same_page", "asked", "no_reply", "rounds", "clock", "stopped", "followed",
                     "wall", "page_gone"]


class TraceStep(DecisionFields):
    """One decision (a model call or code path) or one page action on a field. The model-decision
    fields (engine, p, floor, second, first_p, first_same, chose_none) come from `DecisionFields`."""

    op: Op
    ms: int | None = Field(default=None, ge=0, le=600_000)  # page action OR model-call latency
    effect: Effect | None = None  # page actions
    word: str | None = Field(default=None, pattern=WORD)  # the page's outcome/reason word
    route: Route | None = None  # map
    slot: str | None = Field(default=None, max_length=120, pattern=SLOT)  # a fact NAME
    why: Why | None = None
    way: PolarityWay | None = None  # polarity
    remembered: bool | None = None  # polarity: recalled from an earlier call, not a new decision (never folded)
    # index into the field's own `options` (the page's passive list, in page order), only when the field has
    # one; below MAX_PICK_OPTIONS, so a longer list's later options carry no index
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
    changes: int = Field(default=0, ge=0, le=99)  # how often the field's value changed under the engine; more than 1 is a flicker
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
    reasoning: list["TraceReasonRound"] = Field(default_factory=list, max_length=MAX_REASON_ROUNDS)  # the reasoning step's rounds (fields is [] then)


class TraceReasonAction(BaseModel):
    """What the reasoning step did to one target: a field id, or an opaque button / tab ref, never a value."""

    model_config = ConfigDict(extra="forbid")
    type: ReasonType
    target: str | None = Field(default=None, pattern=TARGET)
    outcome: ReasonOutcome
    slot: str | None = Field(default=None, max_length=120, pattern=SLOT)   # answer_from's fact NAME
    written: int | None = Field(default=None, ge=0, le=5000)               # a written answer's LENGTH, never it


class TraceSnapshot(BaseModel):
    """What the reasoning model was shown, kept for scripts/eval_reason.py to replay against other models: the
    value-free request (questions, option and button words, booleans, fact NAMES), without its job selectors."""

    model_config = ConfigDict(extra="forbid")
    fields: list[SnapField] = Field(default_factory=list, max_length=MAX_SNAPSHOT_FIELDS)
    buttons: list[SnapButton] = Field(default_factory=list, max_length=MAX_BUTTONS)
    errors: list[SnapError] = Field(default_factory=list, max_length=MAX_ERRORS)
    tabs: list[SnapTab] = Field(default_factory=list, max_length=MAX_TABS)
    history: list[Annotated[str, Field(max_length=120, pattern=HISTORY)]] = Field(default_factory=list, max_length=MAX_HISTORY)
    excluded: list[Annotated[str, Field(pattern=SIGNATURE)]] = Field(default_factory=list, max_length=MAX_EXCLUDED)

    @model_validator(mode="after")
    def _capped(self) -> "TraceSnapshot":
        if len(self.model_dump_json()) > SNAPSHOT_CHARS:
            raise ValueError("snapshot too large")
        return self


class TraceReasonRound(BaseModel):
    """One round of the reasoning step (design 2026-10-14 §3). `note` is the model's own sentence, cleaned by the
    backend (no link, email or phone) and capped: page words, as `label` is, never a value. A round that never
    asked (a wall, the page clock) has no model and no snapshot."""

    model_config = ConfigDict(extra="forbid")
    round: int = Field(ge=1, le=MAX_REASON_ROUNDS)
    why: Stuck
    model: str | None = Field(default=None, pattern=MODEL)
    ms: int = Field(default=0, ge=0, le=60_000)
    note: str = Field(default="", max_length=NOTE_MAX)
    actions: list[TraceReasonAction] = Field(default_factory=list, max_length=MAX_REASON_ACTIONS)
    rejected: list[RejectCode] = Field(default_factory=list, max_length=MAX_REASON_REJECTS)
    stopped: ReasonStop | None = None
    snapshot: TraceSnapshot | None = None


RunTrace.model_rebuild()
