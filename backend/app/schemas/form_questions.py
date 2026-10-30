"""The form-question catalog's shape (services/data/form_questions.yaml) and what
GET /api/settings/autofill/questions serves. Names mirror the frontend's FieldDef, camelCase
included, so the served JSON drops into today's components."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


# Frozen: `services/form_questions.catalog()` is cached, and `resolve` hands its objects to
# every caller.
_CATALOG = ConfigDict(extra="forbid", frozen=True)


class Option(BaseModel):
    model_config = _CATALOG

    value: str
    label: str


class Field(BaseModel):
    model_config = _CATALOG

    key: str
    label: str
    optional: bool = False
    type: Literal["text", "select", "date"] | None = None
    boolean: bool = False
    options: list[Option] | None = None
    hint: str | None = None
    staleHint: str | None = None
    when: tuple[str, str] | None = None
    # The address's state line: named and counted by where you live (markets.yaml).
    byHome: bool = False


class Group(BaseModel):
    model_config = _CATALOG

    key: str
    title: str
    fields: list[Field]


class Catalog(BaseModel):
    model_config = _CATALOG

    groups: list[Group]
    # Work-permit fields per `work_auth_vocab` (us_visa, uk, generic), expiry included.
    permits: dict[str, list[Field]]


class QuestionSet(BaseModel):
    """The set for one user's countries: groups resolved for where they live, permit fields per
    apply-in market, whether any apply-in market offers a diversity set, and whether the user chose
    their countries (unchosen: the generic set, no permits). `chosen` has no default, so it is
    served either way."""

    groups: list[Group]
    permits: dict[str, list[Field]]
    offers_eeo: bool
    chosen: bool
