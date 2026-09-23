"""Pins for the Q&A tab: the cover letter survives a failed save and a regenerate asks.

The editor used to close on the click, before the save landed: a failed save
showed the OLD letter and the next Edit overwrote the typed text. Regenerate
and Generate replaced a saved (possibly hand-edited) letter without asking.
Each pin names the gesture it keeps.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SRC = (Path(__file__).resolve().parents[2] / "frontend/components/qa-tab.tsx").read_text()


def _flat(source: str) -> str:
    return " ".join(source.split())


def _between(source: str, start: str, end: str) -> str:
    i = source.index(start)
    return source[i : source.index(end, i + len(start))]


_TAB = _between(_SRC, "export function QATab(", "\nfunction QAEntryCard(")
_CARD = _SRC[_SRC.index("\nfunction QAEntryCard(") :]


def test_the_editor_closes_only_after_the_save_lands():
    """A failed save keeps the editor open with the typed text."""
    assert not re.search(r"onSave\(draft\);\s*setEditing\(false\)", _CARD)
    save = re.sub(r"//[^\n]*", "", _between(_CARD, "onClick={async () => {", "}}"))
    assert _flat(save) == "onClick={async () => { try { await onSave(draft); } catch { return; } closeEditor();"
    assert "onSave: (answer: string) => Promise<unknown>;" in _CARD
    assert "onSave={(answer) => editEntry.mutateAsync({ id: entry.id, answer })}" in _flat(_TAB)
    assert "editEntry.mutate(" not in _TAB


def test_a_saved_letter_shows_at_once():
    """On success the saved text replaces the old one in the cache, so the
    closing editor never flashes the old letter while the refetch runs."""
    success = _flat(_between(_TAB, "const editEntry = useMutation(", "onError:"))
    assert 'qc.setQueryData<QAEntry[]>(["qa", applicationId], (prev) =>' in success
    assert "prev?.map((e) => (e.id === updated.id ? updated : e))" in success
    assert success.index("qc.setQueryData") < success.index("invalidate()")


def test_closing_the_editor_returns_focus_to_edit():
    """Save and Cancel unmount the pressed button with the editor. The shared
    hook moves focus only when it fell to <body>: a slow save must not take
    it back from wherever the user went meanwhile."""
    flat = _flat(_CARD)
    assert "const { editRef, returnFocus } = useEditorFocusReturn(editing);" in flat
    assert "const closeEditor = () => { returnFocus(); onEditingChange(false); };" in flat
    assert "useEffect" not in _SRC, "the focus return lives in the hook"
    edit = flat[flat.rindex("<IconButton", 0, flat.index('label="Edit"')) :]
    assert "ref={editRef}" in edit[: edit.index("/>")]
    cancel = _flat(_between(_CARD, 'variant="ghost"', "Cancel"))
    assert 'onClick={() => { setDraft(entry.answer ?? ""); closeEditor(); }}' in cancel


def test_save_keeps_focus_while_it_saves():
    flat = _flat(_CARD)
    save = flat[flat.rindex("<Button", 0, flat.index("onClick={async () => {")) :]
    save = save[: save.index("</Button>")]
    assert "focusableWhenDisabled" in save
    assert "data-disabled:opacity-50" in save
    assert '{isSaving ? "Saving…" : "Save"}' in save
    assert "Saving..." not in _SRC


def test_an_open_edit_asks_before_leaving():
    assert 'useLeaveGuard(editing && draft !== (entry.answer ?? ""));' in _CARD


def test_replacing_a_saved_letter_asks():
    """Decision 10: no "was edited" signal is stored, so any saved letter counts.
    Generate deletes every saved letter first, so it asks too."""
    ask = _flat(_between(_TAB, "const confirmReplaceLetter = () =>", ");"))
    assert 'title: "Replace your cover letter?"' in ask
    assert "destructive: true" in ask
    regen = _flat(_between(_TAB, "onRegenerate={async () => {", "}}"))
    assert (
        'if (entry.kind === "cover_letter" && entry.answer && !(await confirmReplaceLetter())) return;'
        in regen
    )
    assert regen.index("confirmReplaceLetter") < regen.index("regenerateOnce(entry)")
    assert "onClick={() => void generateCoverLetter()}" in _generate_button()
    assert _TAB.count("coverOnce(") == 1, "Generate starts only through generateCoverLetter"
    generate = _flat(_between(_TAB, "const generateCoverLetter = async () => {", "};"))
    assert 'entries?.some((e) => e.kind === "cover_letter" && e.answer)' in _flat(_TAB)
    assert "if (hasCoverLetter && !(await confirmReplaceLetter())) return;" in generate
    assert generate.index("confirmReplaceLetter") < generate.index("coverOnce()")


def _regenerate_button() -> str:
    """The Regenerate IconButton's props (its icon holds `/>` of its own)."""
    return re.search(r'label="Regenerate".*?\n\s*/>\n', _CARD, re.S).group(0)


def test_regenerate_waits_while_the_letter_is_being_edited():
    """A regenerated letter would land under any open letter draft."""
    disabled = re.search(r"disabled=\{(.*)\}\n", _regenerate_button()).group(1)
    assert disabled == "regenerateBusy || isSaving || isRendering || (isCoverLetter && letterEditing)"


def _card_props() -> str:
    return _flat(_between(_TAB, "<QAEntryCard", "/>"))


def test_the_editing_state_lives_in_the_tab():
    """Generate needs to know a letter is open, so the state is lifted."""
    assert "const [editing, setEditing]" not in _CARD
    assert "const [editingIds, setEditingIds] = useState<string[]>([]);" in _TAB
    assert "const letterEditing = entries?.some((e) => editingIds.includes(e.id)) ?? false;" in _TAB
    assert "setEditingIds((ids) => (on ? [...ids, id] : ids.filter((x) => x !== id)))" in _flat(_TAB)
    props = _card_props()
    for prop in (
        "editing={editingIds.includes(entry.id)}",
        "onEditingChange={(on) => setLetterEditing(entry.id, on)}",
        "letterEditing={letterEditing}",
        "generating={coverLetter.isPending}",
    ):
        assert prop in props, prop


def _generate_button() -> str:
    flat = _flat(_TAB)
    start = flat.rindex("<Button", 0, flat.index('"Generate cover letter"'))
    return flat[start : flat.index("</Button>", start)]


def test_generate_waits_while_a_letter_is_being_edited():
    """Generate replaces every saved letter: it destroyed the one open in the
    editor, and the next Save wrote the old draft over the new letter."""
    assert "disabled={coverLetter.isPending || letterEditing}" in _generate_button()


def test_a_letter_does_not_open_for_editing_while_one_generates():
    """The generation replaces the letter the moment it lands."""
    edit = re.search(r'label="Edit".*?\n\s*/>\n', _CARD, re.S).group(0)
    assert "disabled={isSaving || isRendering || isRegenerating || generating}" in edit


def test_questions_typed_while_answering_are_kept():
    """The box stays editable while it answers; only the sent text clears."""
    ask = _flat(_between(_TAB, "const askQuestions = useMutation(", "onError:"))
    assert "mutationFn: (sent: string) => { const list = sent .split" in ask
    assert 'onSuccess: (_answers, sent) => { setQuestions((current) => (current === sent ? "" : current));' in ask
    assert 'setQuestions("")' not in _SRC
    assert "onClick={() => askOnce(questions)}" in _flat(_TAB)


def test_the_letter_is_read_only_while_it_saves():
    """Keys typed after Save were dropped when the editor closed."""
    textarea = _flat(_between(_CARD, "<Textarea", "/>"))
    assert "readOnly={isSaving}" in textarea
    assert "disabled=" not in textarea


@pytest.mark.parametrize(
    ("name", "guarded"),
    [("askQuestions", "askOnce"), ("coverLetter", "coverOnce"), ("regenerateEntry", "regenerateOnce")],
)
def test_a_generate_starts_one_request_per_gesture(name, guarded):
    """A double click read `isPending === false` twice: two paid generations."""
    assert f"const {guarded} = useSingleFlight({name}.mutate);" in _TAB
    rest = _TAB.replace(f"useSingleFlight({name}.mutate)", "")
    assert f"{name}.mutate" not in rest, "a direct start skips the guard"
    assert f"{guarded}(" in rest.replace(f"const {guarded} =", "")


def test_generate_buttons_keep_focus_while_they_work():
    """A generate button disables itself on click; it stays focusable."""
    flat = _flat(_SRC)
    for click in ("onClick={() => askOnce(questions)}", "onClick={() => void generateCoverLetter()}"):
        start = flat.rindex("<Button", 0, flat.index(click))
        button = flat[start : flat.index("</Button>", start)]
        assert "focusableWhenDisabled" in button, click
    assert "focusableWhenDisabled" in _regenerate_button()
