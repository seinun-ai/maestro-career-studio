"""The second fill pass's ask, and what comes back.

Keyed by `qid` in BOTH directions, which is the whole reason this endpoint
exists rather than a flag on /api/qa. The QA path returns numbered prose and
`_split_numbered_answers` reconstructs the mapping by counting; when the model
answers eight questions in one un-numbered block that count is 1, and the
extension has to throw the entire batch away. A dict keyed by the id the caller
sent cannot be misaligned by a model's formatting.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChooseKind = Literal["text", "textarea", "select", "radio", "checkbox", "combobox"]

MAX_FIELDS = 40


class ChooseField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qid: str = Field(max_length=64)
    label: str = Field(max_length=300)
    kind: ChooseKind
    # Verbatim as the page renders them. The model must return one of these
    # strings exactly; anything else is treated as an abstention by the caller.
    options: list[str] = Field(default_factory=list, max_length=30)
    # The value the profile already holds, when the page's own matcher could not
    # map it onto any rendered option. Its presence changes the question from
    # "what is the answer" to "which of these IS this answer" — one field, not a
    # second code path.
    known_value: str | None = Field(default=None, max_length=300)


class ChooseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[ChooseField] = Field(min_length=1, max_length=MAX_FIELDS)
    # Optional on purpose: the chooser is grounded in the PROFILE, and a form
    # you have not tracked yet is exactly when you most want it. A job sharpens
    # the answers; its absence must not refuse the request.
    application_id: str | None = None


class Choice(BaseModel):
    answer: str | None
    reason: Literal["matched", "abstained"]


class ChooseResponse(BaseModel):
    choices: dict[str, Choice]
