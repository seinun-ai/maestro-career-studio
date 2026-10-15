"""The Companion's reasoning step: the page snapshot it sends and the actions a model may answer with.

VALUE-FREE BY CONSTRUCTION (design docs/plans/2026-10-14-companion-reasoning-step-design.md §1): a field is its
question, shape and whether it is filled, never what it holds. A button, an option and a tab are an opaque ref
plus the page's own words. Every id a reply names must be one this request carried (services/autofill_reason.check).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.schemas.autofill_fill import FID, Selector, Shape

MAX_FIELDS, MAX_OPTIONS, MAX_HISTORY, MAX_BUTTONS, MAX_ERRORS, MAX_TABS, MAX_EXCLUDED = 60, 20, 8, 20, 20, 5, 30
MAX_ACTIONS, MAX_ROUNDS, TEXT_MAX, NOTE_MAX = 3, 3, 300, 200
SLOT = r"^[a-z_]+(\.[a-z0-9_]+)*$"
BUTTON_REF, OPTION_REF, TAB_REF = r"^b\d{1,2}$", r"^o\d{1,2}$", r"^t\d$"
TARGET = r"^[A-Za-z0-9_-]{1,64}$"
SIGNATURE = r"^[a-z_]+:[A-Za-z0-9_-]{1,64}$"
HISTORY = r"^[a-z_]+(:[A-Za-z0-9_-]{1,64})? -> [a-z_]+$"   # the loop's moves and the driver's, never page text

Stuck = Literal["page_errors", "open_questions", "unknown_page", "no_change", "loop", "moved_away"]
Technique = Literal["open_with_keys", "search_with_enter", "search_and_wait", "clear_and_set", "step_by_step"]
Basis = Literal["history", "default"]
Text = Annotated[str, Field(max_length=TEXT_MAX)]
Fid = Annotated[str, Field(pattern=FID)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapOption(_Strict):
    ref: str = Field(pattern=OPTION_REF)
    text: Text


class SnapField(_Strict):
    fid: Fid
    question: Text
    shape: Shape | Literal["unknown"]
    required: bool = False
    filled: bool = False
    invalid: bool = False
    multi: bool = False
    multiline: bool = False
    by_run: bool = False     # the run's own fill wrote it: redo may fill it again
    touched: bool = False    # the user's hands were on it: never rewritten
    slot: str | None = Field(default=None, max_length=120, pattern=SLOT)   # the fact NAME /map gave, never its value
    options: list[SnapOption] = Field(default_factory=list, max_length=MAX_OPTIONS)
    option_count: int = Field(default=0, ge=0, le=5000)


class SnapButton(_Strict):
    ref: str = Field(pattern=BUTTON_REF)
    text: Text
    role: Literal["next", "dialog"]


class SnapError(_Strict):
    text: Text
    fid: Fid | None = None


class SnapTab(_Strict):
    ref: str = Field(pattern=TAB_REF)
    host: str = Field(pattern=r"^[a-z0-9.-]{1,253}(:\d{1,5})?$")


class ReasonRequest(Selector):
    why: Stuck
    round: int = Field(ge=1, le=MAX_ROUNDS)
    fields: list[SnapField] = Field(default_factory=list, max_length=MAX_FIELDS)
    buttons: list[SnapButton] = Field(default_factory=list, max_length=MAX_BUTTONS)
    errors: list[SnapError] = Field(default_factory=list, max_length=MAX_ERRORS)
    tabs: list[SnapTab] = Field(default_factory=list, max_length=MAX_TABS)
    history: list[Annotated[str, Field(max_length=120, pattern=HISTORY)]] = Field(default_factory=list, max_length=MAX_HISTORY)
    excluded: list[Annotated[str, Field(pattern=SIGNATURE)]] = Field(default_factory=list, max_length=MAX_EXCLUDED)
    # The page is one form with Submit on it (no Next): the run may work its fields but presses nothing there, so the
    # prompt never offers a press and the checker refuses one (owner decision 2026-10-15).
    one_page: bool = False

    @model_validator(mode="after")
    def _nothing_from_a_foreign_page(self) -> "ReasonRequest":
        """`moved_away`: the tab is on a site the run never went to. Its fields, buttons and error lines are that
        site's words, and the snapshot carries none of them: dropped here, whatever the caller sent."""
        if self.why == "moved_away":
            self.fields, self.buttons, self.errors = [], [], []
        return self


class Fill(_Strict):
    type: Literal["fill"]
    fids: list[Fid] = Field(min_length=1, max_length=MAX_FIELDS)


class AnswerFrom(_Strict):
    type: Literal["answer_from"]
    fid: Fid
    slot: str = Field(max_length=120, pattern=SLOT)


class Write(_Strict):
    type: Literal["write"]
    fid: Fid


class Choose(_Strict):
    type: Literal["choose"]
    fid: Fid
    basis: Basis


class Retry(_Strict):
    type: Literal["retry"]
    fid: Fid
    technique: Technique


class Redo(_Strict):
    type: Literal["redo"]
    fid: Fid


class CloseDialog(_Strict):
    type: Literal["close_dialog"]
    button: str = Field(pattern=BUTTON_REF)


class PressNext(_Strict):
    type: Literal["press_next"]
    button: str = Field(pattern=BUTTON_REF)


class FollowTab(_Strict):
    type: Literal["follow_tab"]
    tab: str = Field(pattern=TAB_REF)


class AskUser(_Strict):
    type: Literal["ask_user"]
    fids: list[Fid] = Field(default_factory=list, max_length=MAX_FIELDS)
    note: str = Field(default="", max_length=NOTE_MAX)


Action = Annotated[Fill | AnswerFrom | Write | Choose | Retry | Redo | CloseDialog | PressNext | FollowTab | AskUser,
                   Field(discriminator="type")]
ACTION_TYPES = ("fill", "answer_from", "write", "choose", "retry", "redo", "close_dialog", "press_next", "follow_tab",
                "ask_user")


class ReasonReply(_Strict):
    """What the model must return."""
    note: str = Field(max_length=NOTE_MAX)
    actions: list[Action] = Field(min_length=1, max_length=MAX_ACTIONS)


REPLY = TypeAdapter(ReasonReply)

RejectCode = Literal["bad_reply", "model_error", "not_allowed", "unknown_id", "protected", "excluded", "careful_level",
                     "not_free_text", "not_a_choice", "optional_essay", "not_run_filled", "users_field", "not_empty",
                     "multi_value", "next_not_last", "switched_off"]


class ReasonResponse(BaseModel):
    note: str = Field(max_length=NOTE_MAX)
    actions: list[Action] = Field(min_length=1, max_length=MAX_ACTIONS)
    rejected: list[RejectCode] = Field(default_factory=list, max_length=10)
    model: str = Field(max_length=120)
    ms: int = Field(ge=0, le=60_000)


def signature(action: BaseModel) -> str:
    """`type:target`: the field, button or tab an action works (a fill's first field; ask_user's own name)."""
    target = (getattr(action, "fid", None) or getattr(action, "button", None) or getattr(action, "tab", None)
              or (getattr(action, "fids", None) or ["user"])[0])
    return f"{action.type}:{target}"


def signatures(action: BaseModel) -> list[str]:
    """Every signature `action` carries: a fill signs each field it names, so a field that failed twice cannot
    ride in behind another (`signature` names only the first)."""
    if action.type == "fill":
        return [f"fill:{fid}" for fid in action.fids]
    return [signature(action)]
