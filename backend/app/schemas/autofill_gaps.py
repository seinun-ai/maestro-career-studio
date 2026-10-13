"""The POST contract for the known-gaps list.

extra="forbid" on both models is the privacy backstop (SYSTEM.md {#inv-autofill-telemetry-no-values}):
a label, a value or an option text 422s instead of being stored. Every string is a closed enum or a
pattern a typed answer cannot satisfy: a lowercase hash, a lowercase hostname, a shape or outcome word.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.autofill_fill import Shape

MAX_GAPS = 40

GapOutcome = Literal["cannot_operate", "unconfirmed", "user_fixed", "missing_technique"]


class GapIn(BaseModel):
    """One sighting. Posting it again adds one to the stored row's count."""

    model_config = ConfigDict(extra="forbid")

    # The recipe-book family hash (content/recipes.js) without its `f:` prefix.
    family: str = Field(pattern=r"^[0-9a-z]{1,24}$")
    host: str = Field(pattern=r"^[a-z0-9.-]{1,253}(:\d{1,5})?$")  # lowercase / punycode, as in a run trace
    shape: Shape | Literal["unknown"]
    outcome: GapOutcome


class GapBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gaps: list[GapIn] = Field(max_length=MAX_GAPS)
