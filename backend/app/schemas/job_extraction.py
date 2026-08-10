from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# Role categories are DATA, not a compiled enum — see services/role_categories
# and ats/data/role_categories.yaml. A closed Literal forced every role outside
# four data/AI titles into "other", which is what made analytics group unrelated
# roles together. Values are normalized on ingest, so the set stays groupable.
RoleCategory = str
RequirementLevel = Literal["required", "preferred", "mentioned"]
WorkAuthorization = Literal[
    "sponsorship_available",
    "no_sponsorship",
    "citizen_or_gc_required",
    "unstated",
]
OptAccepted = Literal["yes", "stem_opt_ok", "no", "unstated"]


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "n/a", "unknown"}:
        return None
    return text


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid integer value: {value}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"Non-integer numeric value: {value}")
        return int(value)
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "n/a", "unknown"}:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value: {value}") from exc


def _coerce_enum(value: Any, allowed: set[str], default: str) -> str:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text or text in {"none", "null", "n/a"}:
        return default
    if text not in allowed:
        return default
    return text


_WORK_AUTH_VALUES = {"sponsorship_available", "no_sponsorship", "citizen_or_gc_required", "unstated"}
_OPT_VALUES = {"yes", "stem_opt_ok", "no", "unstated"}


class ExtractedSkill(BaseModel):
    skill_name: str
    skill_category: str = "other"
    requirement_level: RequirementLevel = "mentioned"

    @field_validator("skill_name", "skill_category", "requirement_level", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()


class JobExtraction(BaseModel):
    company: str | None = None
    title: str | None = None
    role_category: RoleCategory = "unknown"
    level: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    location_raw: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_period: str | None = None
    # ISO 4217. Null when the posting states no pay (the common case) or when
    # currency cannot be inferred. Never invent a currency for a null salary.
    salary_currency: str | None = None
    # When the posting hyperlinks a pay scale/benefits page instead of stating
    # numbers (legal in Illinois under 820 ILCS 112/10(b-25)), capture the URL
    # and leave salary_min/max null — that is a complete extraction, not a miss.
    salary_source_url: str | None = None
    work_authorization: WorkAuthorization = "unstated"
    opt_accepted: OptAccepted = "unstated"
    years_experience_min: int | None = None
    years_experience_max: int | None = None
    skills: list[ExtractedSkill] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)

    @field_validator(
        "company",
        "title",
        "level",
        "employment_type",
        "work_mode",
        "city",
        "state",
        "country",
        "location_raw",
        "salary_period",
        "salary_source_url",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: Any) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_location(cls, values: Any) -> Any:
        # Old extraction payloads stored a single free-text `location` field. If
        # the caller still provides it (re-running on cached JSON, older prompt
        # outputs, tests), treat it as `location_raw` when the new field is
        # absent.
        if not isinstance(values, dict):
            return values
        if values.get("location_raw") in (None, "") and values.get("location") not in (None, ""):
            values = dict(values)
            values["location_raw"] = values["location"]
        return values

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def parse_salary(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
            if not value:
                return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid salary value: {value}") from exc

    @field_validator("salary_period", mode="after")
    @classmethod
    def normalize_salary_period(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().replace("per ", "")
        if normalized in {"hr", "hourly", "hour"}:
            return "hour"
        if normalized in {"day", "daily", "pd", "p/d"}:
            return "day"
        if normalized in {"wk", "week", "weekly"}:
            return "week"
        if normalized in {"mo", "monthly", "month"}:
            return "month"
        if normalized in {"yr", "yearly", "annual", "annually", "year"}:
            return "year"
        return normalized

    @field_validator("salary_currency", mode="before")
    @classmethod
    def normalize_salary_currency(cls, value: Any) -> str | None:
        text = _blank_to_none(value)
        if text is None:
            return None
        cleaned = text.strip().upper()
        symbols = {"£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR", "$": "USD"}
        if cleaned in symbols:
            return symbols[cleaned]
        for prefix in ("US$", "$"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip() or "USD"
                break
        if len(cleaned) == 3 and cleaned.isalpha():
            return cleaned
        return None

    @field_validator("work_authorization", mode="before")
    @classmethod
    def normalize_work_auth(cls, value: Any) -> str:
        return _coerce_enum(value, _WORK_AUTH_VALUES, "unstated")

    @field_validator("opt_accepted", mode="before")
    @classmethod
    def normalize_opt(cls, value: Any) -> str:
        return _coerce_enum(value, _OPT_VALUES, "unstated")

    @field_validator("years_experience_min", "years_experience_max", mode="before")
    @classmethod
    def parse_years(cls, value: Any) -> int | None:
        return _coerce_optional_int(value)

    @field_validator("responsibilities", "qualifications", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("skills", mode="after")
    @classmethod
    def dedupe_skills(cls, value: list[ExtractedSkill]) -> list[ExtractedSkill]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[ExtractedSkill] = []
        for skill in value:
            key = (
                skill.skill_name.lower(),
                skill.skill_category.lower(),
                skill.requirement_level.lower(),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(skill)
        return deduped

    @model_validator(mode="after")
    def order_salary_bounds(self) -> "JobExtraction":
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            self.salary_min, self.salary_max = self.salary_max, self.salary_min
        return self

    @model_validator(mode="after")
    def order_years_bounds(self) -> "JobExtraction":
        if (
            self.years_experience_min is not None
            and self.years_experience_max is not None
            and self.years_experience_min > self.years_experience_max
        ):
            self.years_experience_min, self.years_experience_max = (
                self.years_experience_max,
                self.years_experience_min,
            )
        return self

    @property
    def location(self) -> str | None:
        """Backwards-compat accessor for callers that still read `.location`."""
        return self.location_raw


