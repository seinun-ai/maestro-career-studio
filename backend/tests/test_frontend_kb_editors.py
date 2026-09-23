"""Pins for the Career KB's local editors: they ask before throwing text away.

Escape is a reflex key, and in the notes, point and inbox-draft editors it
dropped a multi-line edit with no question. Now Escape and Cancel over
changed text ask ("Discard your changes?", Keep editing focused), unchanged
text closes at once, and a closing editor hands focus back to its Edit
button instead of <body>. Quick capture starts one request per click.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _flat(source: str) -> str:
    return " ".join(source.split())


def _between(source: str, start: str, end: str) -> str:
    i = source.index(start)
    return source[i : source.index(end, i + len(start))]


_HOOK = _read("hooks/use-confirm-discard.ts")
_NOTES = _read("components/career/notes-editor.tsx")
_POINTS = _read("components/career/points-list.tsx")
_POINT_ROW = _POINTS[_POINTS.index("function PointRow(") :]
_INBOX = _read("components/career/inbox-panel.tsx")
_DRAFT_ROW = _INBOX[_INBOX.index("function DraftRow(") :]
_CAPTURE = _read("components/career/capture-box.tsx")

# (name, source, the "changed" expression, the close function, the busy flag)
_EDITORS = [
    ("notes", _NOTES, "value !== notes", "cancel", "save.isPending"),
    ("point", _POINT_ROW, "text.trim() !== point.text", "cancelEdit", "pending"),
    ("inbox draft", _DRAFT_ROW, "text.trim() !== point.text", "cancelEdit", "pending"),
]
_IDS = [e[0] for e in _EDITORS]


def test_one_discard_question():
    """One copy of the copy: every editor asks through this hook."""
    ask = _flat(_between(_HOOK, "export function useConfirmDiscard()", "\n}\n"))
    assert "changed ? confirm({" in ask
    assert ": Promise.resolve(true)" in ask, "unchanged text closes at once"
    for needle in (
        'title: "Discard your changes?"',
        'confirmLabel: "Discard"',
        'cancelLabel: "Keep editing"',
        "destructive: true",
    ):
        assert needle in ask, needle
    copies = [
        str(p.relative_to(_FRONTEND))
        for root in ("app", "components", "hooks")
        for p in (_FRONTEND / root).rglob("*.ts*")
        if "Discard your changes?" in p.read_text(encoding="utf-8")
    ]
    assert copies == ["hooks/use-confirm-discard.ts"], copies


_DISCARDABLE = _between(_HOOK, "export function useDiscardableEditor(", "\n}\n")


def test_cancel_and_escape_ask_first_and_wait_for_a_save():
    """Only a yes closes, and the close focuses Edit. While a save is in flight
    both do nothing: a Discard then closed the editor, and the save landed a
    moment later with a "saved" toast."""
    cancel = _flat(_between(_DISCARDABLE, "const onCancel = async () => {", "};"))
    assert cancel == (
        "const onCancel = async () => { if (busy || !(await confirmDiscard(changed))) return;"
        ' returnFocus("always"); close();'
    )
    escape = _flat(_between(_DISCARDABLE, "const onKeyDown = (event: KeyboardEvent) => {", "};"))
    assert escape.endswith('if (event.key !== "Escape") return; event.preventDefault(); void onCancel();')
    assert "return { editRef, onCancel, onKeyDown, onSave };" in _DISCARDABLE


def test_a_closing_editor_returns_focus_to_edit_without_stealing_it():
    """After a Discard focus sits in the closing confirm, so Edit takes it
    unconditionally. A save closes later: by then the user may have moved on,
    so it moves focus only when focus fell to <body> with the editor."""
    ret = _between(_HOOK, "export function useEditorFocusReturn(", "\n}\n")
    effect = _flat(_between(ret, "useEffect(() => {", "}, [editing]);"))
    assert effect == (
        "useEffect(() => { if (editing || !armed.current) return;"
        ' const always = armed.current === "always"; armed.current = null;'
        " if (always) editRef.current?.focus(); else focusIfDropped(editRef.current);"
    )
    assert '(when: "if-dropped" | "always" = "if-dropped") => { armed.current = when; }' in _flat(ret)
    assert "useEditorFocusReturn(editing)" in _DISCARDABLE


@pytest.mark.parametrize(("name", "src", "changed", "close", "busy"), _EDITORS, ids=_IDS)
def test_each_editor_states_its_change_once(name, src, changed, close, busy):
    """Escape and Cancel read one "changed" expression and one close."""
    call = _flat(_between(src, "useDiscardableEditor({", "});"))
    assert call == f"useDiscardableEditor({{ editing, changed: {changed}, close: {close}, busy: {busy},", name
    assert src.count(changed) == 1, name
    assert "onKeyDown={onKeyDown}" in _flat(_between(src, "<Textarea", "/>")), name
    assert 'event.key === "Escape"' not in src, "Escape is handled once, in the hook"


@pytest.mark.parametrize(("name", "src", "changed", "close", "busy"), _EDITORS, ids=_IDS)
def test_cancel_asks_before_discarding(name, src, changed, close, busy):
    flat = _flat(src)
    cancel = flat[: flat.index('<X aria-hidden="true" /> Cancel')]
    cancel = cancel[cancel.rindex("<Button") :]
    assert "onClick={() => void onCancel()}" in cancel, name


@pytest.mark.parametrize(("name", "src", "changed", "close", "busy"), _EDITORS, ids=_IDS)
def test_the_editor_keeps_focus_while_it_saves(name, src, changed, close, busy):
    """A disabled textarea or Save button dropped focus to <body> mid-save,
    and a textarea left writable took keys the closing save then dropped."""
    textarea = _flat(_between(src, "<Textarea", "/>"))
    assert f"readOnly={{{busy}}}" in textarea, name
    assert "disabled=" not in textarea, name
    flat = _flat(src)
    click = "onClick={() => onSave("
    save = flat[flat.rindex("<Button", 0, flat.index(click)) :]
    save = save[: save.index("</Button>")]
    assert "focusableWhenDisabled" in save, name
    assert "data-disabled:opacity-50" in save, name


@pytest.mark.parametrize(("name", "src", "changed", "close", "busy"), _EDITORS, ids=_IDS)
def test_edit_is_where_focus_returns(name, src, changed, close, busy):
    edit = _flat(src)
    edit = edit[: edit.index('<Pencil aria-hidden="true" />')]
    assert "ref={editRef}" in edit[edit.rindex("<Button") :], name


def test_save_arms_the_focus_return_then_saves_or_closes():
    """Save unmounts itself whether it saves or only closes, so the focus
    return is armed first. A save closes in onSuccess, and a failed save keeps
    the editor open (the flag waits for the next close)."""
    save = _flat(_between(_DISCARDABLE, "const onSave = (save: () => void) => {", "};"))
    assert save == "const onSave = (save: () => void) => { returnFocus(); if (changed) save(); else close();"


@pytest.mark.parametrize(
    ("name", "src", "save"),
    [
        ("notes", _NOTES, "onClick={() => onSave(() => save.mutate(value))}"),
        (
            "point",
            _POINT_ROW,
            'onClick={() => onSave(() => update.mutate({ payload: { text: text.trim() }, message: "Point updated" })) }',
        ),
        (
            "inbox draft",
            _DRAFT_ROW,
            'onClick={() => onSave(() => update.mutate({ payload: { text: text.trim() }, success: "Draft updated" })) }',
        ),
    ],
    ids=_IDS,
)
def test_each_save_goes_through_the_hook(name, src, save):
    assert save in _flat(src), name


@pytest.mark.parametrize(
    ("name", "guarded"), [("capture", "captureOnce"), ("ingest", "ingestOnce")]
)
def test_quick_capture_starts_one_request_per_gesture(name, guarded):
    """A double click ran two LLM extractions and two sets of draft points."""
    assert f"const {guarded} = useSingleFlight({name}.mutate);" in _CAPTURE
    rest = _CAPTURE.replace(f"useSingleFlight({name}.mutate)", "")
    assert f"{name}.mutate" not in rest, "a direct start skips the guard"
    assert f"{guarded}(" in rest.replace(f"const {guarded} =", "")


def test_quick_capture_keeps_focus_while_it_captures():
    textarea = _flat(_between(_CAPTURE, "<Textarea", "/>"))
    assert "readOnly={capture.isPending}" in textarea
    assert "disabled=" not in textarea
    flat = _flat(_CAPTURE)
    submit = flat[flat.rindex("<Button", 0, flat.index('"Capturing…" : "Add to inbox"')) :]
    assert "focusableWhenDisabled" in submit
    assert "data-disabled:opacity-50" in submit
