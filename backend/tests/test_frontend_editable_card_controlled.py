"""Guard: index-keyed entry lists must drive `EditableCard` in CONTROLLED mode.

`EditableCard` keeps open/closed in local `useState` when it is uncontrolled.
Every entry editor renders `value.map(...)` with `key={i}`, so React reconciles
by POSITION: move the entry you are editing up one slot (or delete the one above
it) and the open card stays at the old position — a DIFFERENT entry is now open
for editing and the one you were writing in silently collapses.

`EditableCard`'s own prop doc says controlled mode exists for exactly this, and
`extra-sections-editor.tsx` already hand-rolled it. The four other editors did
not, so the state and the reorder callbacks now come from ONE hook
(`useEntryEditing`): the two halves have to move together, and a caller cannot
take the reorder half while forgetting the state half.

There is no JS test runner in this repo, so this pins the structural property
rather than the interaction. `test_formatting_parity.py` is the cross-boundary
precedent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_EDITORS = Path(__file__).resolve().parents[2] / "frontend" / "components" / "resume-editor"

_ENTRY_EDITORS = [
    "experience-editor.tsx",
    "project-editor.tsx",
    "education-editor.tsx",
    "skills-editor.tsx",
    "extra-sections-editor.tsx",
]


@pytest.mark.parametrize("filename", _ENTRY_EDITORS)
def test_entry_editor_keeps_edit_state_with_the_entry(filename: str):
    source = (_EDITORS / filename).read_text()

    assert "useEntryEditing(" in source, (
        f"{filename} does not own an editing index: with EditableCard left "
        "uncontrolled in an index-keyed list, reordering or deleting an entry "
        "moves the open editor onto a different entry."
    )
    assert "entryEditingProps(" in source, (
        f"{filename} calls useEntryEditing but does not spread its props onto "
        "EditableCard, so the state it owns reaches nothing."
    )


@pytest.mark.parametrize("filename", _ENTRY_EDITORS)
def test_index_keyed_cards_never_reorder_through_card_reorder_props(filename: str):
    """`cardReorderProps` moves the DATA and not the open card.

    It stays correct for a list keyed by something STABLE (the custom-sections
    outer list keys on `section.key`, so React follows identity and card-local
    state comes along). The bug is the combination: an index key plus reorder
    callbacks that renumber the list under it. So this checks the pairing, not
    the helper.
    """
    lines = (_EDITORS / filename).read_text().split("\n")
    index_keyed = [n for n, line in enumerate(lines) if "key={i}" in line]

    for n in index_keyed:
        window = "\n".join(lines[n : n + 12])
        assert "cardReorderProps(" not in window, (
            f"{filename}:{n + 1} keys a card by index and reorders through "
            "cardReorderProps; use useEntryEditing so the open card follows "
            "its entry."
        )
