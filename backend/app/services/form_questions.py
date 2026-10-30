"""The form-question catalog (data/form_questions.yaml) and the set resolved for one user.

Domain data, like markets.yaml: the questions Profile, Setup and setup readiness ask, in the words
they ask them. Loaded once and validated; a malformed file fails at import in tests, not at a
user's first Profile visit.
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


def resolve(*, home: str, apply_in: list[str]) -> QuestionSet:
    """The questions for someone who lives in `home` and applies in `apply_in` (market keys, as the
    market setting stores them; empty reads as `[home]`, the setting's own rule)."""
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
