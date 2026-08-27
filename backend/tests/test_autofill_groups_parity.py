"""Guard: the autofill field taxonomy is written twice, so pin it.

`setup_status._PERSONAL` and friends are, in that module's own words, "a
hand-mirror of the frontend GROUPS array in
frontend/components/settings/autofill-section.tsx ... update BOTH when a field
is added". A comment asking two people in two languages to stay in sync is not
a mechanism; nothing failed when they drifted.

Serving the taxonomy from the backend was the alternative considered and
rejected: GROUPS carries labels, placeholders and select options, which are
presentation, and the browser extension ships on its own cadence against the
same shape. So the two lists stay, and this makes the drift loud instead.

Parity rule: for each group, the backend's REQUIRED field list must equal the
frontend's non-`optional` fields, in order. Readiness counts answerable
fields, so a field the editor marks optional must not count against it, and a
field the editor added must count.

Precedent: `test_frontend_query_error_states.py`, `test_formatting_parity.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services import setup_status

_AUTOFILL_TSX = (
    Path(__file__).resolve().parents[2]
    / "frontend/components/settings/autofill-section.tsx"
)

_EXPECTED = {
    "personal": setup_status._PERSONAL,
    "work_auth": setup_status._WORK_AUTH_CORE,
    "eeo": setup_status._EEO,
    "preferences": setup_status._PREFERENCES,
}


def _frontend_required_fields() -> dict[str, list[str]]:
    source = _AUTOFILL_TSX.read_text()
    start = source.index("const GROUPS: GroupDef[] = [")
    block = source[start : source.index("\n];", start)]

    groups: dict[str, list[str]] = {}
    for match in re.finditer(
        r'\{\s*\n\s*key: "(\w+)",\s*\n\s*title: "[^"]*",\s*\n\s*fields: \[', block
    ):
        cursor, depth = match.end(), 1
        while depth:
            if block[cursor] == "[":
                depth += 1
            elif block[cursor] == "]":
                depth -= 1
            cursor += 1
        fields = block[match.end() : cursor - 1]
        groups[match.group(1)] = [
            field.group(1)
            for field in re.finditer(r'\{[^{}]*?key: "(\w+)".*?\}', fields, re.S)
            if "optional: true" not in field.group(0)
        ]
    return groups


def test_the_parser_still_finds_the_groups():
    """If GROUPS is reshaped, this file must fail loudly rather than pass empty.

    Without this, a refactor that breaks the regex turns every parity check
    below into a comparison against nothing — a green vacuous test, which is
    the failure mode these source-parsing guards are most prone to.
    """
    found = _frontend_required_fields()
    assert set(_EXPECTED) <= set(found), (
        f"could not parse groups {sorted(set(_EXPECTED) - set(found))} out of "
        f"{_AUTOFILL_TSX.name} — the GROUPS shape changed; fix this parser."
    )
    assert all(found[group] for group in _EXPECTED)


@pytest.mark.parametrize("group", sorted(_EXPECTED))
def test_backend_required_fields_match_the_editor(group: str):
    frontend = _frontend_required_fields()[group]
    assert frontend == _EXPECTED[group], (
        f"autofill group {group!r} has drifted. The editor requires "
        f"{frontend}, setup_status counts {_EXPECTED[group]}. Readiness is "
        "computed from the backend list, so a mismatch either hides a question "
        "the user must answer or blocks setup on one the editor never shows."
    )
