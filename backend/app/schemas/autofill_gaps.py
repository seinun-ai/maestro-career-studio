"""The POST contract for the known-gaps list.

extra="forbid" on both models is the privacy backstop (SYSTEM.md {#inv-autofill-telemetry-no-values}):
a label, a value or an option text 422s instead of being stored. Shape and outcome are closed enums.
The family and host patterns are shape checks, not proof: they admit any short lowercase token, so
they bound what can ride along (no spaces, capitals or punctuation; a family no longer than the hash)
and rely on the extension to post only the recipe hash and the page's hostname.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.autofill_fill import Shape

MAX_GAPS = 40

# A lowercase / punycode host, as in a run trace; the Companion's submit report uses it too.
HOST_PATTERN = r"^[a-z0-9.-]{1,253}(:\d{1,5})?$"

GapOutcome = Literal["cannot_operate", "unconfirmed", "user_fixed", "missing_technique"]


class GapIn(BaseModel):
    """One sighting. Posting it again adds one to the stored row's count."""

    model_config = ConfigDict(extra="forbid")

    # The recipe-book family hash (content/recipes.js) without its `f:` prefix: a 53-bit value in
    # base 36, so at most 11 characters ((2**53 - 1).toString(36) is 11 long).
    family: str = Field(pattern=r"^[0-9a-z]{1,11}$")
    host: str = Field(pattern=HOST_PATTERN)
    shape: Shape | Literal["unknown"]
    outcome: GapOutcome


class GapBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gaps: list[GapIn] = Field(max_length=MAX_GAPS)
