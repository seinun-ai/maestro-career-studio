"""Quick Tailor preference profile: which auto-resolution moves a one-shot
tailor may make, plus a standing instruction.

Was an untyped `dict[str, Any]` with a module-level DEFAULTS dict and a
hand-maintained tuple of retired keys. Both jobs belong to a model: field
defaults ARE the defaults merge, and pydantic's default `extra="ignore"`
drops a retired key on read without anyone listing it.
"""

from pydantic import BaseModel


class QuickTailorProfile(BaseModel):
    keywords_into_skills: bool = True
    mirror_wording: bool = True
    summary_rename: bool = False
    project_keyword_injection: bool = False
    instruction: str = ""
