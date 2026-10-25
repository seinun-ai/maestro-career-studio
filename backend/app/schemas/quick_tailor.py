"""Quick Tailor preference profile: which auto-resolution moves a one-shot
tailor may make, plus a standing instruction.

Was an untyped `dict[str, Any]` with a module-level DEFAULTS dict and a
hand-maintained tuple of retired keys. Both jobs belong to a model: field
defaults ARE the defaults merge, and pydantic's default `extra="ignore"`
drops a retired key on read without anyone listing it.
"""

from pydantic import BaseModel, Field


class QuickTailorProfile(BaseModel):
    # Each description is the plain meaning an agent reads back to the user
    # (MCP get_tailoring_options); the web's Quick tailor card words the same switches.
    keywords_into_skills: bool = Field(True, description=(
        "Add missing job description keywords to Skills: a skill the job asks for that the "
        "resume lacks goes into the skills list, never into a bullet."))
    mirror_wording: bool = Field(True, description=(
        "Use the job description's wording when the experience backs it up: a skill the "
        "resume already shows takes the job's exact word."))
    summary_rename: bool = Field(False, description=(
        "Match the summary and title to the job: the wording is drafted by Maestro's AI, "
        "so it needs Maestro's AI key."))
    project_keyword_injection: bool = Field(False, description=(
        "Add keywords to projects: a job keyword the user's work backs up is placed in a "
        "project bullet as well as the experience."))
    instruction: str = Field("", description="An extra instruction the user gave for every tailor.")
