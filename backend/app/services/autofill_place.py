"""A city picked from a Places-style search ("Springfield, IL, USA"), decided in code.

Such a box offers each place as the city, then its state, then its country. The saved city and state pick the option
whose first comma part is the city (a whole name: "Springfield Gardens" is another place) and whose later parts name
the state, by code or by full name. Exactly one such option is the pick; none, or two that say the one place, leaves it
to the ordinary path and the user. No state saved, nothing is claimed: a city alone names many places."""

import re
from typing import Any

from app.services.knockout import _city, _state


def _state_of(part: str) -> str:
    """A part's state code or name, a ZIP code dropped ("TX 78701")."""
    return _state(re.sub(r"\d[\d-]*", " ", part))


def city_option(city: Any, state: Any, options: list[tuple[str, str]]) -> str | None:
    """The id of the one option that is `city` in `state`, else None."""
    want_city, want_state = _city(city), _state_of(str(state or ""))
    if not want_city or not want_state:
        return None
    found = [oid for oid, text in options
             if len(parts := [p.strip() for p in text.split(",")]) > 1 and _city(parts[0]) == want_city
             and any(_state_of(p) == want_state for p in parts[1:])]
    return found[0] if len(found) == 1 else None
