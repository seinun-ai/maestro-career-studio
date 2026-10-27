"""Job-search preferences: favored roles, level, location, remote posture.

New (2026-07-29) and therefore fully typed — unlike autofill_profile there is
no legacy loose shape to tolerate on the write path. Consumers: setup status
(suggested base resumes for favored roles without one), persona draft
grounding; later the job-search brief and automated-apply lanes.

`favored_roles` (2026-08-10) is the field the picker writes; `role_categories`
is a COMPUTED PROJECTION of it, recomputed on every validation. That is what
lets the four existing readers of the coarse list — setup status, the job-search
brief, the persona prompt, and any agent reading settings/job_preferences.json —
stay exactly as they were, and it is why the projection can never drift: it is
never stored independently of its source.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services import countries, money, role_categories

MAX_FAVORED_ROLES = 25
MAX_LABEL_CHARS = 80


def _unknown(message: str, value: str, *, roles: bool = False) -> str:
    """A refusal of `value`, naming the closest catalog entries when any is close (the web's picker
    and an agent's set_job_preferences share it)."""
    near = role_categories.name_closest(value, roles=roles)
    return f"{message}; closest: {near}" if near else message


class FavoredRole(BaseModel):
    """One role the user is targeting.

    Three shapes, distinguished by `role`:
      * a coarse category  -> role == category (both "data_scientist")
      * a specific role    -> role is a catalog role key, category is its parent
      * custom free text   -> role is None; category is the user's CONFIRMED
                              mapping, or None if they left it unmapped, which
                              is a valid resting state and not an error
    """

    role: str | None = None
    label: str = ""
    category: str | None = None

    @model_validator(mode="after")
    def _resolve(self) -> "FavoredRole":
        if self.category is not None and self.category not in role_categories.all_keys():
            raise ValueError(_unknown(f"unknown role category: {self.category}", self.category))

        if self.role is None:
            # Custom free text is the user's own words, so it is only tidied,
            # never rewritten — and it must actually say something.
            label = " ".join(self.label.split())
            if not label:
                raise ValueError("a custom favored role needs a label")
            if len(label) > MAX_LABEL_CHARS:
                raise ValueError(f"label is longer than {MAX_LABEL_CHARS} characters")
            self.label = label
            return self

        parent = role_categories.parent_of(self.role)
        if parent is None:
            raise ValueError(_unknown(f"unknown role: {self.role}", self.role, roles=True))
        if self.category is None:
            # Completion of a derived field, not coercion of a human's answer —
            # unlike the contradiction below, nobody asserted anything here.
            self.category = parent
        elif self.category != parent:
            raise ValueError(
                f"role {self.role!r} belongs to {parent!r}, not {self.category!r}"
            )
        # The catalog owns display names. Trusting a client's copy buys a stale
        # label the first time role_categories.yaml is edited.
        self.label = role_categories.label_for(self.role)
        return self


class MinSalary(BaseModel):
    """The lowest yearly pay you want: an amount in a currency (ISO 4217).

    `currency` None is your home currency: `job_preferences.get_preferences` fills it in when
    read, so the figure is never compared as a bare number. A stored preference from before
    (free text) reads as an amount when the text is a number ("150000", "£80,000", "150k");
    any other text stays readable in `text`, with no amount, until you save a number. Mapped
    when read, never migrated: the stored text stays as written until a save.
    """

    amount: int | None = Field(default=None, ge=0)
    currency: str | None = None
    text: str | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def _known_currency(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        code = str(value).strip().upper()
        if code not in countries.currency_codes():
            raise ValueError(f"currency must be an ISO 4217 code, got {value!r}")
        return code


def _min_salary_from_text(value):
    """The old free-text minimum salary as `MinSalary` fields (see `MinSalary`)."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    amount, currency = money.parse_amount(text, whole=True)
    if amount is None:
        return {"text": text}
    return {"amount": int(amount), "currency": currency}


class JobPreferences(BaseModel):
    favored_roles: list[FavoredRole] = []
    role_categories: list[str] = []  # DERIVED — see _project_role_categories.
    years_experience: int | None = Field(default=None, ge=0, le=60)
    employment_types: list[str] = []
    locations: list[str] = []
    remote: Literal["remote", "hybrid", "onsite", "any"] | None = None
    min_salary: MinSalary | None = None
    notes: str | None = None

    @field_validator("min_salary", mode="before")
    @classmethod
    def _old_min_salary(cls, value):
        return _min_salary_from_text(value)

    @field_validator("role_categories")
    @classmethod
    def _known_role_keys(cls, value: list[str]) -> list[str]:
        # Validate, never normalize: an alias or typo must 422 back to the
        # picker, not be silently coerced (same rule as base-resume identity).
        #
        # Still enforced even though the field is recomputed below, because a
        # client PUTting the legacy list is upgraded FROM it — bad keys there
        # must be reported, not quietly dropped on the floor.
        valid = set(role_categories.all_keys())
        unknown = [key for key in value if key not in valid]
        if unknown:
            near = [(key, role_categories.name_closest(key)) for key in unknown]
            raise ValueError("; ".join([
                f"unknown role categories: {', '.join(unknown)}",
                *(f"closest to {key}: {names}" for key, names in near if names),
            ]))
        return value

    @model_validator(mode="after")
    def _project_role_categories(self) -> "JobPreferences":
        if not self.favored_roles and self.role_categories:
            # Every preference stored before favored_roles existed has this
            # shape, so this is the path that must not break.
            self.favored_roles = [
                FavoredRole(role=key, category=key) for key in self.role_categories
            ]

        seen: set[tuple[str, str]] = set()
        unique: list[FavoredRole] = []
        for favored in self.favored_roles:
            identity = (
                ("role", favored.role)
                if favored.role
                else ("label", favored.label.casefold())
            )
            # Silently, not with a 422: autosave fires on every edit, and
            # rejecting a duplicate the UI should not have produced would strand
            # the whole save. The cap below IS worth a 422 — a limit, not cleanup.
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(favored)
        if len(unique) > MAX_FAVORED_ROLES:
            raise ValueError(f"at most {MAX_FAVORED_ROLES} favored roles")
        self.favored_roles = unique

        self.role_categories = list(
            dict.fromkeys(f.category for f in unique if f.category is not None)
        )
        return self
