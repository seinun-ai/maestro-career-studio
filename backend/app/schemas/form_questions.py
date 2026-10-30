"""The form-question catalog's shape (services/data/form_questions.yaml) and what
GET /api/settings/autofill/questions serves. Names mirror the frontend's FieldDef, camelCase
included, so the served JSON drops into today's components.

Some attributes are the catalog's own, read by the backend and never served: declared with
`exclude=True`, so no dump carries them (`pack`, `describe`, `policy`, `fills`, `noExpiry`)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField


# Frozen: `services/form_questions.catalog()` is cached, and `resolve` hands its objects to
# every caller.
_CATALOG = ConfigDict(extra="forbid", frozen=True)


class Option(BaseModel):
    model_config = _CATALOG

    value: str
    label: str
    # A status whose right to work never runs out, so its expiry is not asked (Task 3.5). Catalog
    # only.
    noExpiry: bool = PydanticField(default=False, exclude=True)


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
    # Catalog only, never served:
    # - shown only while a country you apply in names this pack (markets.yaml `packs`; Task 3.5);
    pack: str | None = PydanticField(default=None, exclude=True)
    # - what the fill reads for this answer, and how strictly (Task 3.7); absent is today's rule;
    describe: str | None = PydanticField(default=None, exclude=True)
    policy: Literal["exact", "flag", "any"] | None = PydanticField(default=None, exclude=True)
    # - a country answer's flat slot (`section.key`), which it fills on that country's jobs.
    fills: str | None = PydanticField(default=None, exclude=True)


class Group(BaseModel):
    model_config = _CATALOG

    key: str
    title: str
    fields: list[Field]


class CitizenshipRule(BaseModel):
    """Citizens of these countries may work in these markets with no permit: the source says so."""

    model_config = _CATALOG

    citizens: str | list[str]  # a group's name, or ISO codes
    markets: list[str]
    status: str | None = None  # the market's status it settles (`citizen` in one's own country)
    source: str


class Citizenship(BaseModel):
    model_config = _CATALOG

    groups: dict[str, list[str]]
    rules: list[CitizenshipRule]

    def members(self, rule: CitizenshipRule) -> list[str]:
        """The ISO codes a rule covers: its group's, when it names one, else its own list."""
        if isinstance(rule.citizens, str):
            return self.groups[rule.citizens]
        return rule.citizens


class Catalog(BaseModel):
    model_config = _CATALOG

    groups: list[Group]
    # Each market's immigration statuses, keyed by its `work_status` (us, ca, au, ae).
    statuses: dict[str, list[Option]]
    # Work-permit fields per `work_auth_vocab` (us_visa, uk, generic, ca, ae), expiry included.
    permits: dict[str, list[Field]]
    # Country answers: asked per country you apply in, each filling its `fills` slot there.
    answers: list[Field]
    # Extra fields on each language you list (CEFR).
    language_fields: list[Field]
    citizenship: Citizenship


class DerivedAnswer(BaseModel):
    """A work-permit answer a citizenship settles (`services/autofill_derive`): computed on read,
    never stored."""

    value: str | bool
    via: str  # the ISO code of the citizenship that settles it ("IE")


class QuestionSet(BaseModel):
    """The set for one user's countries: groups resolved for where they live, permit fields per
    apply-in market, whether any apply-in market offers a diversity set, and whether the user chose
    their countries (unchosen: the generic set, no permits). `chosen` has no default, so it is
    served either way."""

    groups: list[Group]
    permits: dict[str, list[Field]]
    offers_eeo: bool
    chosen: bool
