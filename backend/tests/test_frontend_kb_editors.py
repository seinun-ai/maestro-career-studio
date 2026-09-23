"""Pins for the Career KB's local editors: they ask before throwing text away.

Escape is a reflex key, and in the notes, point and inbox-draft editors it
dropped a multi-line edit with no question. Now Escape and Cancel over
changed text ask ("Discard your changes?", Keep editing focused), unchanged
text closes at once, and a closing editor hands focus back to its Edit
button instead of <body>. Quick capture starts one request per click.
"""

from __future__ import annotations

import re
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

# (name, source, the "changed" expression, the close function)
_EDITORS = [
    ("notes", _NOTES, "value !== notes", "cancel"),
    ("point", _POINT_ROW, "text.trim() !== point.text", "cancelEdit"),
    ("inbox draft", _DRAFT_ROW, "text.trim() !== point.text", "cancelEdit"),
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


def test_a_cancelled_editor_asks_first_and_returns_focus():
    """requestCancel asks, and only a yes closes; the close arms the focus
    return to Edit. Keep editing leaves the text and the textarea as they were."""
    cancel = _flat(_between(_HOOK, "const requestCancel = useCallback(", "[confirmDiscard]"))
    assert "if (!(await confirmDiscard(changed))) return;" in cancel
    assert cancel.index("confirmDiscard(changed)") < cancel.index("refocus.current = true;") < cancel.index(
        "close();"
    )
    escape = _flat(_between(_HOOK, "const cancelOnEscape =", "};"))
    assert 'if (event.key !== "Escape") return; event.preventDefault(); void requestCancel(changed, close);' in escape
    effect = _flat(_between(_HOOK, "useEffect(() => {", "}, [editing]);"))
    assert "if (editing || !refocus.current) return;" in effect
    assert "editRef.current?.focus();" in effect


@pytest.mark.parametrize(("name", "src", "changed", "close"), _EDITORS, ids=_IDS)
def test_escape_asks_before_discarding(name, src, changed, close):
    assert f"onKeyDown={{(event) => cancelOnEscape(event, {changed}, {close})}}" in _flat(src), name
    assert 'event.key === "Escape"' not in src, "Escape is handled once, in the hook"


@pytest.mark.parametrize(("name", "src", "changed", "close"), _EDITORS, ids=_IDS)
def test_cancel_asks_before_discarding(name, src, changed, close):
    flat = _flat(src)
    cancel = flat[: flat.index('<X aria-hidden="true" /> Cancel')]
    cancel = cancel[cancel.rindex("<Button") :]
    assert f"onClick={{() => void requestCancel({changed}, {close})}}" in cancel, name


@pytest.mark.parametrize(("name", "src", "changed", "close"), _EDITORS, ids=_IDS)
def test_the_editor_keeps_focus_while_it_saves(name, src, changed, close):
    """A disabled textarea or Save button dropped focus to <body> mid-save."""
    textarea = _flat(_between(src, "<Textarea", "/>"))
    assert re.search(r"readOnly=\{[^}]+\}", textarea), name
    assert "disabled=" not in textarea, name
    flat = _flat(src)
    click = "save.mutate(value);" if name == "notes" else "onClick={saveText}"
    save = flat[flat.rindex("<Button", 0, flat.index(click)) :]
    save = save[: save.index("</Button>")]
    assert "focusableWhenDisabled" in save, name
    assert "data-disabled:opacity-50" in save, name


@pytest.mark.parametrize(("name", "src", "changed", "close"), _EDITORS, ids=_IDS)
def test_edit_is_where_focus_returns(name, src, changed, close):
    assert "useDiscardableEditor(editing)" in src, name
    edit = _flat(src)
    edit = edit[: edit.index('<Pencil aria-hidden="true" />')]
    assert "ref={editRef}" in edit[edit.rindex("<Button") :], name


@pytest.mark.parametrize(
    ("name", "src", "arm"),
    [
        ("notes", _NOTES, "returnFocus(); save.mutate(value);"),
        ("point", _POINT_ROW, "const saveText = () => { returnFocus();"),
        ("inbox draft", _DRAFT_ROW, "const saveText = () => { returnFocus();"),
    ],
    ids=_IDS,
)
def test_a_landed_save_returns_focus_to_edit(name, src, arm):
    """Armed before the request: the editor closes in onSuccess, and a failed
    save keeps it open (the flag waits for the next close)."""
    assert arm in _flat(re.sub(r"//[^\n]*", "", src)), name


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
