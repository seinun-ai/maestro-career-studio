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


def _for_home(field: Field, home: str) -> Field:
    if not field.byHome:
        return field
    m = markets.get(home)
    return field.model_copy(
        update={"label": m["state_label"] or field.label, "optional": m["asks_state"] is False}
    )


def required_keys(fields: list[Field]) -> list[str]:
    """The keys setup readiness counts: every field not `optional`."""
    return [f.key for f in fields if not f.optional]


def resolve(*, home: str, apply_in: list[str]) -> QuestionSet:
    """The questions for someone who lives in `home` and applies in `apply_in`. Callers pass a
    validated `MarketSetting`'s `home` and `apply_in` (upper-cased market keys); an unknown key
    falls back to the default market's (US) wording, as `markets.get` does. Empty `apply_in` reads
    as `[home]`, the setting's own rule."""
    cat = catalog()
    apply_in = apply_in or [home]
    groups = [
        Group(key=g.key, title=g.title, fields=[_for_home(f, home) for f in g.fields])
        for g in cat.groups
    ]
    permits = {m: cat.permits[markets.get(m)["work_auth_vocab"]] for m in apply_in}
    return QuestionSet(
        groups=groups, permits=permits, offers_eeo=any(markets.offers_eeo(m) for m in apply_in)
    )
