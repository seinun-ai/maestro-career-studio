from typing import Literal

from pydantic import BaseModel

WorkAuthStatus = Literal[
    "citizen", "permanent_resident", "opt", "stem_opt",
    "h1b", "tn", "other_visa", "not_authorized",
]


class WorkAuth(BaseModel):
    """The two-part question US applications actually ask.

    `sponsorship_now` and `sponsorship_future` are separate because the form
    asks them separately and the answers legitimately differ — an OPT holder
    needs no sponsorship now and will need it later. The single timeless boolean
    this replaces could not express that, and answered one of the two questions
    wrongly every time.

    All fields optional. An unknown answer must STAY unknown: the extension
    reports `missing_source` and the user is asked, which is always better than
    a confident guess on a knockout question.
    """

    status: WorkAuthStatus | None = None
    authorized_now: bool | None = None
    sponsorship_now: bool | None = None
    sponsorship_future: bool | None = None
    authorization_expires_on: str | None = None
    countries_authorized: list[str] = []
