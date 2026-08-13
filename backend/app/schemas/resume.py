import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContactInfo(BaseModel):
    name: str
    email: str
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class ExperienceEntry(BaseModel):
    """A role. ``start_date`` is None when the resume states no date for it
    (functional and academic resumes routinely do): that is a legal
    representation, not a defect. Renderers must guard it, the ATS indexer
    treats the entry as undated (no recency credit, no tenure span), and health
    gate S3 skips it — only a NON-EMPTY unparseable date string is a defect."""

    company: str
    role: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    enabled: bool = True
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """A term of study. ``degree`` is None for non-degree study (coursework,
    bootcamps, exchange terms) — never invent a degree title. Renderers must
    guard it; ``ats/degrees.resume_degree_level`` simply reads no level from it."""

    institution: str
    degree: str | None = None
    field: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    graduation_date: str | None = None
    gpa: str | None = None
    coursework: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str
    enabled: bool = True
    tech: str | None = None
    link: str | None = None
    date: str | None = None
    bullets: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)


# --- Custom (extra) sections -------------------------------------------------
#
# User-defined sections (Publications, Awards, Volunteer Work, ...). They live
# in ``ResumeData.extra_sections`` as an ordered list of a discriminated union
# on ``type``: an ``entries`` section carries structured entries, a ``bullets``
# section carries a flat bullet list. A section is NEVER both at once — the
# union routes on ``type`` and each member forbids the other's content field.
#
# ``key`` is the stable machine identity (lookups use it as ``section_key``);
# ``title`` is editable display text. Keys are lowercase slugs, unique
# case-insensitively across the resume, and must not collide with a core
# section name. Extras are first-class evidence: they feed the ATS engine at
# the ``extra_only`` tier, gap placement targets them by ``section_key``, and
# their bullets sit on the health evidence ladder (see SYSTEM.md §4). The
# canonical common-section vocabulary lives in
# ``services/extra_section_presets.py``.

# Core section field names an extra-section key may not shadow.
CORE_SECTION_KEYS = frozenset(
    {
        "contact",
        "summary",
        "skills",
        "experience",
        "projects",
        "education",
        "certifications",
    }
)

# Display headers a core section already prints. An extra-section TITLE equal to
# one of these (case-insensitively) would render a duplicate header in the PDF,
# so it is rejected. Distinct from CORE_SECTION_KEYS: keys are machine slugs,
# titles are human display text (e.g. the skills section prints "Technical
# Skills"). Mirrored in frontend/lib/resume-schema.ts (keep in sync).
CORE_SECTION_TITLES = frozenset(
    {
        "summary",
        "skills",
        "technical skills",
        "experience",
        "projects",
        "education",
        "certifications",
    }
)

TITLE_COLLISION_MESSAGE = (
    "Title collides with a core section header. Choose a different title."
)

# Lowercase slug: starts alphanumeric, then alphanumeric / underscore / hyphen.
_SECTION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ExtraSectionEntry(BaseModel):
    heading: str = Field(min_length=1)
    subheading: str | None = None
    location: str | None = None
    date: str | None = None
    link: str | None = None
    enabled: bool = True
    bullets: list[str] = Field(default_factory=list)


class _ExtraSectionBase(BaseModel):
    # Reject stray/miswired content fields (e.g. a ``bullets`` key on an
    # ``entries`` section) instead of silently dropping them — this is what
    # makes "both content fields at once" a hard validation error.
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str = Field(min_length=1)
    enabled: bool = True

    @field_validator("key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        if not _SECTION_KEY_RE.match(value):
            raise ValueError(
                "section key must be a lowercase slug (alphanumeric, "
                "'_' or '-'), e.g. 'publications'"
            )
        return value

    @field_validator("title")
    @classmethod
    def _title_not_core_header(cls, value: str) -> str:
        if value.strip().casefold() in CORE_SECTION_TITLES:
            raise ValueError(TITLE_COLLISION_MESSAGE)
        return value


class ExtraSectionEntries(_ExtraSectionBase):
    type: Literal["entries"] = "entries"
    entries: list[ExtraSectionEntry] = Field(default_factory=list)


class ExtraSectionBullets(_ExtraSectionBase):
    type: Literal["bullets"] = "bullets"
    bullets: list[str] = Field(default_factory=list)


ExtraSection = Annotated[
    ExtraSectionEntries | ExtraSectionBullets,
    Field(discriminator="type"),
]


class ResumeData(BaseModel):
    contact: ContactInfo
    summary: str | None = None
    skills: list[SkillGroup] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    extra_sections: list[ExtraSection] = Field(default_factory=list)

    @field_validator("extra_sections")
    @classmethod
    def _unique_non_reserved_keys(
        cls, sections: list[ExtraSection]
    ) -> list[ExtraSection]:
        seen: set[str] = set()
        for section in sections:
            folded = section.key.casefold()
            if folded in CORE_SECTION_KEYS:
                raise ValueError(
                    f"extra section key {section.key!r} collides with the core "
                    f"'{folded}' section"
                )
            if folded in seen:
                raise ValueError(f"duplicate extra section key {section.key!r}")
            seen.add(folded)
        return sections
