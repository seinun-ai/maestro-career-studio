"""Pins for the gap-page autosave (UX next, Task 11, U2, plus the review fixes).

Source pins: each one names the regression it exists to catch. A "Saved"
line during the debounce, a late response painting "Saved" over a newer
edit, an unmount that drops the timer, a failed save with no retry, focus
pulled out of a field mid-typing, edits made while tailoring that are shown
but never saved, and a second ~30 s tailor from a second click.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PAGE = (_FRONTEND / "app/jobs/[id]/tailor/[sessionId]/page.tsx").read_text()
_CONTROLS = (_FRONTEND / "components/gap-analysis/resolution-controls.tsx").read_text()
_CARD = (_FRONTEND / "components/gap-analysis/gap-card.tsx").read_text()


def _flat(source: str) -> str:
    """Whitespace-insensitive view, so a reflow never breaks a pin."""
    return " ".join(source.split())


def _fn(source: str, head: str) -> str:
    start = source.index(head)
    return source[start : source.index("\n}\n", start)]


def _arrow(source: str, head: str) -> str:
    """One arrow function. These live inside the page component, so they close at two spaces."""
    start = source.index(head)
    return source[start : source.index("\n  };", start)]


def _jsx(source: str, head: str) -> str:
    """One JSX element's opening tag, from `head` to its closing `>` line."""
    start = source.index(head)
    return _flat(source[start : source.index(">\n", start)])


_INDICATOR = _fn(_PAGE, "function SaveIndicator(")
_SCHEDULE = _arrow(_PAGE, "const scheduleSave = () => {")
_SAVE = _arrow(_PAGE, "const saveNow = async ()")
_RUN = _arrow(_PAGE, "const runTailor = async (")


# --- Saving… and Saved ---------------------------------------------------------


def test_every_edit_says_saving():
    assert "scheduleSave()" in _arrow(_PAGE, "const handleChange = (")
    assert "scheduleSave()" in _arrow(_PAGE, "const handlePromptChange = (")
    bail = _SCHEDULE.index("if (tailorLock.current) return;")
    saving = _SCHEDULE.index('setSaveState("saving")', bail)
    assert saving < _SCHEDULE.index("setTimeout(", saving)


def test_every_edit_bumps_the_generation_before_any_bail():
    # A bump after a bail would let a held-back edit look "already saved".
    bump = _SCHEDULE.index("editGen.current += 1")
    assert bump < _SCHEDULE.index("if (staleReason)")
    assert bump < _SCHEDULE.index("if (tailorLock.current) return;")


def test_the_debounce_absorbs_a_mis_click():
    # 800 ms is what keeps an undone "I can't confirm this" from becoming a
    # durable KB record; 0 would save it at once.
    assert "}, 800);" in _SCHEDULE


def test_saved_only_when_nothing_newer():
    gen = _SAVE.index("const gen = editGen.current")
    assert gen < _SAVE.index("await run", gen)
    assert 'if (editGen.current === gen) setSaveState("saved")' in _SAVE
    assert 'if (editGen.current === gen) setSaveState("error")' in _SAVE


def test_saves_run_one_at_a_time_in_order():
    # Without the chain two PATCHes race and an older list can land last.
    assert "const run = chainRef.current.then(attempt, attempt);" in _SAVE


def test_a_prompt_only_save_leaves_the_stored_prompt_alone():
    # `?? undefined` omits user_prompt; `?? ""` would wipe the stored note.
    assert "promptRef.current ?? undefined," in _SAVE


def test_a_stale_session_never_sends_a_save():
    assert _SAVE.index("if (staleReason) return true;") < _SAVE.index("saveResolutions(")


# --- Leaving -------------------------------------------------------------------


def test_unmount_flushes_instead_of_dropping():
    refresh = _flat("useEffect(() => { saveNowRef.current = saveNow; });")
    assert refresh in _flat(_PAGE)  # no deps: the cleanup must call the newest saveNow
    cleanup = _flat(
        "useEffect( () => () => { if (!timerRef.current) return; clearTimeout(timerRef.current);"
        " timerRef.current = null; void saveNowRef.current(); }, [], );"
    )
    # `if (!timerRef.current) return;` keeps an unmount with nothing pending
    # from saving again; `[]` runs it on unmount only, not after every render.
    assert cleanup in _flat(_PAGE)


def test_leaving_asks_after_a_failure_and_reload_warns_while_saving():
    assert 'useLeaveGuard(saveState === "saving", { reloadOnly: true })' in _PAGE
    assert 'useLeaveGuard(saveState === "error")' in _PAGE


# --- The status line and Try again ----------------------------------------------


def test_indicator_live_region_is_always_mounted():
    live = _INDICATOR.index('aria-live="polite"')
    assert "return null" not in _INDICATOR[:live]


def test_try_again_retries_and_stays_mounted_while_it_runs():
    assert "Not saved" in _INDICATOR and "Save failed" not in _INDICATOR
    assert "focusableWhenDisabled" in _INDICATOR
    # `|| retrying`: state flips to "saving" at once; without it the focused
    # button unmounts mid-retry and focus drops to <body>.
    assert '{onRetry && (state === "error" || retrying) ? (' in _INDICATOR
    click = _INDICATOR[_INDICATOR.index("onClick={() => {") :]
    assert "void onRetry().then((ok) => {" in click


def test_focus_moves_only_when_it_was_dropped():
    # A bare .focus() here stole focus from a field the user was typing in.
    # A layout effect: a passive one paints a frame with focus on <body> first.
    effect = _INDICATOR[_INDICATOR.index("useLayoutEffect(") : _INDICATOR.index("}, [state, retrying]);")]
    assert "focusIfDropped(statusRef.current);" in effect
    assert ".focus()" not in _INDICATOR


def test_a_failed_retry_disarms_the_focus_move():
    # Left armed, the NEXT ordinary save moved focus mid-typing.
    click = _flat(_INDICATOR[_INDICATOR.index("void onRetry().then(") :])
    assert "if (!ok) refocus.current = false; setRetrying(false);" in click


def test_a_stale_session_offers_no_dead_try_again():
    assert "onRetry={staleReason ? undefined : saveNow}" in _PAGE


def test_an_edit_on_a_stale_session_admits_it_is_unsaved():
    # The error state keeps "Not saved" up and the leave guard on.
    stale = _flat(_SCHEDULE[_SCHEDULE.index("if (staleReason)") :])
    assert stale.startswith('if (staleReason) { setSaveState("error"); return; }')


# --- Tailor ----------------------------------------------------------------------


def test_both_tailor_buttons_go_through_one_locked_sequence():
    assert "await runTailor(" in _arrow(_PAGE, "const onTailorClick = async")
    assert "await runTailor(" in _arrow(_PAGE, "const onQuickTailorClick = async")
    assert _PAGE.count("tailor.mutate(") == 1


def test_a_second_click_cannot_start_a_second_tailor():
    # The lock is taken synchronously, before the first await.
    lock = _flat(_RUN)
    assert "if (tailorLock.current) return; tailorLock.current = true; setTailorBusy(true);" in lock
    assert _RUN.index("setTailorBusy(true)") < _RUN.index("await ")


def test_tailor_never_runs_on_an_unsaved_flush():
    saved = _RUN.index("const saved = await saveNow();")
    bail = _RUN.index("if (!saved) return endTailor();", saved)
    assert bail < _RUN.index("tailor.mutate(", bail)


def test_tailor_buttons_are_disabled_but_keep_focus_while_busy():
    for label in ("onClick={onQuickTailorClick}", "onClick={onTailorClick}"):
        start = _PAGE.rindex("<Button", 0, _PAGE.index(label))
        tag = _flat(_PAGE[start : _PAGE.index(">\n", _PAGE.index(label))])
        assert "disabled={tailorBusy ||" in tag, label
        # The confirm hands focus back here; a native disabled drops it to <body>.
        assert "focusableWhenDisabled" in tag, label


def test_autosave_holds_back_while_tailoring_and_resaves_if_it_fails():
    gen = _RUN.index("const gen = editGen.current;")
    assert gen < _RUN.index("await saveNow()")
    on_error = _flat(_RUN[_RUN.index("onError: () => {") :])
    assert "if (editGen.current !== gen && !applyProfile) scheduleSave();" in on_error
    assert on_error.index("endTailor();") < on_error.index("scheduleSave();")


# --- Every gap input is locked while tailoring -------------------------------------


def test_the_page_locks_the_gap_controls_and_the_note():
    region = _PAGE.index("<GapLocked value={tailorBusy}>")
    assert _PAGE.index("<CategorySection", region) < _PAGE.index("</GapLocked>", region)
    assert 'tailorBusy && "pointer-events-none opacity-60"' in _PAGE
    note = _jsx(_PAGE, '<Textarea\n            id="tailor-instructions"')
    assert "readOnly={tailorBusy}" in note


def test_the_answer_and_wording_fields_are_readonly():
    # readOnly keeps focus where disabled would drop it.
    answer = _fn(_CONTROLS, "export function UserInputControls(")
    assert "const locked = use(GapLocked);" in answer
    assert "readOnly={locked}" in _jsx(answer, "<Textarea")
    wording = _fn(_CONTROLS, "export function AddKeywordControls(")
    assert "const locked = use(GapLocked);" in wording
    assert "readOnly={locked}" in _jsx(wording, "<Input")


def test_chips_and_segments_ignore_the_keyboard_while_locked():
    for head, handler in (
        ("export function Chip(", "onClick={locked ? undefined : onClick}"),
        ("export function ActionSegment(", "onClick={locked ? undefined : () => onSelect(action)}"),
    ):
        body = _fn(_CONTROLS, head)
        assert "const locked = use(GapLocked);" in body, head
        assert "aria-disabled={locked || undefined}" in body, head
        assert handler in body, head


def test_card_buttons_that_change_a_resolution_are_locked():
    # Every Undo (cannot_confirm, skip, auto-resolved) and "I can't confirm this".
    undo = _flat(_fn(_CARD, "function UndoButton("))
    assert "const locked = use(GapLocked);" in undo
    assert "focusableWhenDisabled disabled={locked} onClick={onClick}" in undo
    assert _CARD.count("<UndoButton") == 3
    assert "<Undo2 />" not in _CARD.replace(_fn(_CARD, "function UndoButton("), "")
    confirm = _CARD.rindex("<Button", 0, _CARD.index('setAction("cannot_confirm")'))
    tag = _flat(_CARD[confirm : _CARD.index('setAction("cannot_confirm")')])
    assert "focusableWhenDisabled disabled={locked}" in tag
