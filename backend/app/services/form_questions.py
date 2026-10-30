"""The form-question catalog (data/form_questions.yaml) and the set resolved for one user.

Domain data, like markets.yaml: the questions Profile, Setup and setup readiness ask, in the words
they ask them. Loaded once and validated; a malformed file fails at import in tests, not at a
user's first Profile visit.
"""

from functools import cache
from pathlib import Path

import yaml

from app.schemas.form_questions import Catalog

_FILE = Path(__file__).parent / "data" / "form_questions.yaml"


@cache
def catalog() -> Catalog:
    return Catalog.model_validate(yaml.safe_load(_FILE.read_text(encoding="utf-8")))
