"""One JSON-blob setting, stored as a `Setting` row with a file mirror.

Every settings blob had written this out for itself — a KEY constant, a FILE
constant, a `_parse` that falls back to defaults, and get/peek/set wrappers
around `text_settings`. Seven modules, one idea, ~250 lines. The idea:

- **The row is the truth, the file is a mirror.** `text_settings` owns that;
  this class only adds the JSON layer on top.
- **A blob that will not parse reads as defaults, it does not raise.** These
  files are hand-editable, so any JSON can arrive. Degrading keeps every
  consumer alive; raising takes down the app over one bad character. Note the
  deliberate asymmetry with the API: a bad value arriving from a HUMAN 422s at
  the schema boundary, while a bad value already on disk degrades quietly.
- **`peek` never writes.** `get` lazily seeds the row and the file mirror,
  which makes it unusable from anything that must not have side effects —
  `setup_status` reads through `peek` precisely so a status request stays
  derived-not-stored, and job capture uses it so a read cannot write a Setting
  row mid-transaction.

Not everything settings-shaped belongs here. `persona` is a bare string with
no JSON layer at all, and `model_settings` keeps one row per key rather than
one blob — both would have to be bent to fit, so both stay as they are.
"""

import json
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.services import text_settings


class JsonSetting[T: BaseModel]:
    """A typed settings blob. Invalid stored JSON reads as `model()`."""

    def __init__(self, key: str, filename: str, model: type[T]):
        self.key = key
        self.filename = filename
        self.model = model

    def parse(self, raw: str) -> T:
        if not raw.strip():
            return self.model()
        try:
            return self.model.model_validate(self.migrate(json.loads(raw)))
        except (json.JSONDecodeError, ValidationError):
            return self.model()

    def migrate(self, payload: Any) -> Any:
        """Hook for salvaging a stored blob before validation.

        Default is identity. Override where one stale field must not cost the
        whole record — `job_preferences` degrades retired role entries item by
        item rather than letting one of them reset every other preference.
        """
        return payload

    def get(self, session: Session | None = None) -> T:
        return self.parse(text_settings.get_text(self.key, self.filename, session))

    def peek(self, session: Session | None = None) -> T:
        """Read without seeding a Setting row or its file mirror."""
        return self.parse(text_settings.peek_text(self.key, self.filename, session))

    def set(self, value: T, session: Session | None = None) -> T:
        text_settings.set_text(
            self.key, self.filename, value.model_dump_json(indent=2), session
        )
        return value

    def is_set(self, value: T) -> bool:
        """Whether the user has actually expressed an opinion.

        A stored value equal to the default is indistinguishable from never
        having chosen, deliberately: both mean "no explicit opinion".
        """
        return value != self.model()
