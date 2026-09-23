"""Pins for the gap-page autosave (UX next, Task 11, U2).

Source pins: each one names the regression it exists to catch. A "Saved"
line during the debounce, a late response painting "Saved" over a newer
edit, an unmount that drops the timer, and a failed save with no retry.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PAGE = (_FRONTEND / "app/jobs/[id]/tailor/[sessionId]/page.tsx").read_text()
_CONTROLS = (_FRONTEND / "components/gap-analysis/resolution-controls.tsx").read_text()


def _fn(source: str, head: str) -> str:
    start = source.index(head)
    return source[start : source.index("\n}\n", start)]


def _arrow(source: str, head: str) -> str:
    """One arrow function. These live inside the page component, so they close at two spaces."""
    start = source.index(head)
    return source[start : source.index("\n  };", start)]


def test_every_edit_says_saving():
    change = _arrow(_PAGE, "const handleChange = (")
    prompt = _arrow(_PAGE, "const handlePromptChange = (")
    assert "scheduleSave()" in change
    assert "scheduleSave()" in prompt
    schedule = _arrow(_PAGE, "const scheduleSave = () => {")
    assert "editGen.current += 1" in schedule
    bail = schedule.index("if (tailor.isPending || staleReason) return;")
    saving = schedule.index('setSaveState("saving")', bail)
    timeout = schedule.index("setTimeout(", saving)
    assert bail < saving < timeout


def test_saved_only_when_nothing_newer():
    save = _arrow(_PAGE, "const saveNow = async ()")
    gen = save.index("const gen = editGen.current")
    await_run = save.index("await run", gen)
    assert gen < await_run
    assert 'if (editGen.current === gen) setSaveState("saved")' in save
    assert 'if (editGen.current === gen) setSaveState("error")' in save


def test_unmount_flushes_instead_of_dropping():
    assign = _PAGE.index("saveNowRef.current = saveNow")
    assert "useEffect(" in _PAGE[assign - 120 : assign]
    flush = _PAGE.index("void saveNowRef.current()")
    clear = _PAGE.rindex("clearTimeout(timerRef.current)", 0, flush)
    assert clear < flush


def test_failed_save_offers_retry_and_guards_leaving():
    indicator = _fn(_PAGE, "function SaveIndicator(")
    assert "Save failed" in indicator
    assert "Try again" in indicator
    assert "focusableWhenDisabled" in indicator
    assert 'useLeaveGuard(saveState === "saving", { reloadOnly: true })' in _PAGE
    assert 'useLeaveGuard(saveState === "error")' in _PAGE


def test_indicator_live_region_is_always_mounted():
    indicator = _fn(_PAGE, "function SaveIndicator(")
    live = indicator.index('aria-live="polite"')
    assert "return null" not in indicator[:live]


def test_textareas_are_readonly_while_tailoring():
    # Keyboard still reaches a focused textarea under pointer-events-none.
    # readOnly keeps that focus; disabled would drop it to <body>.
    assert "readOnly={tailor.isPending}" in _PAGE
    controls = _fn(_CONTROLS, "export function UserInputControls(")
    textarea = controls[controls.index("<Textarea") : controls.index("/>", controls.index("<Textarea"))]
    assert "readOnly={readOnly}" in textarea
