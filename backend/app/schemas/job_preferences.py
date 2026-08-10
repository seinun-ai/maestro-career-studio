"""Job-search preferences: favored roles, level, location, remote posture.

New (2026-07-29) and therefore fully typed — unlike autofill_profile there is
no legacy loose shape to tolerate on the write path. Consumers: setup status
(suggested base resumes for favored roles without one), persona draft
grounding; later the job-search brief and automated-apply lanes.
"""

from typing import Literal

from pydantic import BaseModel, field_validator

from app.services import role_categories


class JobPreferences(BaseModel):
    role_categories: list[str] = []
    levels: list[str] = []
    employment_types: list[str] = []
    locations: list[str] = []
    remote: Literal["remote", "hybrid", "onsite", "any"] | None = None
    min_salary: str | None = None
    notes: str | None = None

    @field_validator("role_categories")
    @classmethod
    def _known_role_keys(cls, value: list[str]) -> list[str]:
        # Validate, never normalize: an alias or typo must 422 back to the
        # picker, not be silently coerced (same rule as base-resume identity).
        valid = set(role_categories.all_keys())
        unknown = [key for key in value if key not in valid]
        if unknown:
            raise ValueError(f"unknown role categories: {', '.join(unknown)}")
        return value
