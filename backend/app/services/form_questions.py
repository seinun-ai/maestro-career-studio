"""The form-question catalog (data/form_questions.yaml) and the set resolved for one user.

Domain data, like markets.yaml: the questions Profile, Setup and setup readiness ask, in the words
they ask them. Loaded on first use, then cached, and validated; a malformed file fails that first
load, which a test makes (tests/test_form_questions.py), not a user's first Profile visit.
"""

from functools import cache
from pathlib import Path

import yaml

from app.schemas.form_questions import Catalog, Field, Group, QuestionSet
from app.services import markets

_FILE = Path(__file__).parent / "data" / "form_questions.yaml"


@cache
def catalog() -> Catalog:
    return Catalog.model_validate(yaml.safe_load(_FILE.read_text(encoding="utf-8")))


def _for_home(field: Field, home: str, chosen: bool) -> Field:
    """The address's state line, named and counted by where you live; with no country chosen there
    is no address rule, so it keeps its own label and is never required."""
    if not field.byHome:
        return field
    if not chosen:
        return field.model_copy(update={"optional": True})
    m = markets.get(home)
    return field.model_copy(
        update={"label": m["state_label"] or field.label, "optional": m["asks_state"] is False}
    )


def required_keys(fields: list[Field]) -> list[str]:
    """The keys setup readiness counts: every field not `optional`."""
    return [f.key for f in fields if not f.optional]


def resolve(
    *, home: str, apply_in: list[str], chosen: bool = True, citizenships: tuple[str, ...] = ()
) -> QuestionSet:
    """The questions for someone who lives in `home` and applies in `apply_in`. Callers pass a
    validated `MarketSetting`'s `home`, `apply_in` and `chosen` (upper-cased market keys); an
    unknown key falls back to the default market's (US) wording, as `markets.get` does. Empty
    `apply_in` reads as `[home]`, the setting's own rule.

    Unchosen (`MarketSetting.chosen` false) is the generic set: no country is applied in, so no
    work permits (a permit answer belongs to a country) and no diversity set, and the state line is
    optional. `citizenships` is not read yet (Task 3.5 of
    docs/plans/2026-10-30-country-form-questions.md)."""
    cat = catalog()
    apply_in = (apply_in or [home]) if chosen else []
    groups = [
        Group(key=g.key, title=g.title, fields=[_for_home(f, home, chosen) for f in g.fields])
        for g in cat.groups
    ]
    permits = {m: cat.permits[markets.get(m)["work_auth_vocab"]] for m in apply_in}
    return QuestionSet(
        groups=groups,
        permits=permits,
        offers_eeo=any(markets.offers_eeo(m) for m in apply_in),
        chosen=chosen,
    )
