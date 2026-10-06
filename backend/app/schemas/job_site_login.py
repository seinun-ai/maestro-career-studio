"""The job-site login (docs/plans/2026-10-05-full-automation-design.md, Part 1)."""

from pydantic import BaseModel, ConfigDict, Field


class JobSiteLoginIn(BaseModel):
    """A PUT sets either field; a missing one keeps what is stored."""

    model_config = ConfigDict(extra="forbid")
    email: str | None = Field(default=None, max_length=320)
    # No length constraint here: a Pydantic 422 echoes the rejected input, so the password
    # would go back to the browser. The router checks the length with its own message.
    password: str | None = None


PASSWORD_MIN, PASSWORD_MAX = 8, 200


class JobSiteLoginStatus(BaseModel):
    email: str | None = None
    password_set: bool = False
