"""Pins for the focus-return and single-flight helpers (UX next, Task 8).

Node tests cover `isLoadFailure`, the focus helpers (`lib/focus.test.ts`) and
the single-flight lock (`lib/single-flight.test.ts`); they are not in CI, so
the predicates and the hook shapes are pinned here as source text. Each pin
below was seen to fail on the mutant it names.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


_HOOK = _read("hooks/use-focus-return.ts")
_FOCUS = _read("lib/focus.ts")


def _squash(source: str) -> str:
    return re.sub(r"\s+", " ", source)


def _fn_body(src: str, head: str) -> str:
    """A function's body, whitespace squashed, from after its first `{` to its closing brace."""
    start = src.index(head)
    body = src[src.index("{\n", start) + 1 : src.index("\n}\n", start)]
    return _squash(body).strip()


def test_the_hooks_use_the_node_tested_helpers():
    # One copy: the hook file re-exports what `lib/focus.ts` defines.
    assert 'import { focusIfDropped, focusReturnPoint, focusTarget } from "@/lib/focus";' in _HOOK
    assert "export { focusIfDropped, focusReturnPoint };" in _HOOK
    for name in ("focusIfDropped", "focusReturnPoint", "focusTarget", "holdsDraft"):
        assert f"function {name}(" not in _HOOK, name
    for name in ("focusIfDropped", "focusReturnPoint", "focusTarget", "holdsDraft"):
        assert f"export function {name}(" in _FOCUS, name
    tests = _read("lib/focus.test.ts")
    assert 'from "./focus.ts";' in tests


def test_focus_helpers_move_only_a_dropped_focus():
    # Mutant: the guard neutered (`&& false`) takes focus from where the user put it.
    assert _fn_body(_FOCUS, "export function focusIfDropped(") == (
        "const active = document.activeElement; "
        "if (active && active !== document.body) return; "
        "target?.focus({ preventScroll: true });"
    )


def test_an_opened_editor_lands_in_its_first_text_field():
    # Mutant: any tabbable before a field (the edit view's first button won).
    assert _fn_body(_FOCUS, "export function focusTarget(") == (
        "if (el.matches(TABBABLE)) return el; "
        "return el.querySelector<HTMLElement>(FIELD) ?? el.querySelector<HTMLElement>(TABBABLE) ?? el;"
    )
    assert "export const FIELD =\n  'input:not([type=\"hidden\"]):not(:disabled), textarea:not(:disabled), select:not(:disabled)';" in _FOCUS


def test_the_save_shortcut_blurs_every_draft_holding_field():
    # Mutant: textareas only (a chip or title input kept its draft uncommitted).
    assert _fn_body(_FOCUS, "export function holdsDraft(") == (
        "return ( el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || "
        "(el instanceof HTMLElement && el.isContentEditable) );"
    )


def test_an_armed_move_runs_after_every_commit():
    # Mutant: `[]` deps (mount-only) never runs for a later click's commit.
    assert _fn_body(_HOOK, "export function useFocusOnNextCommit(") == (
        "const pending = useRef<RefObject<HTMLElement | null> | null>(null); "
        "// No deps: it runs after every commit of this component and does nothing unless a handler armed it. "
        "useEffect(() => { const target = pending.current; if (!target) return; pending.current = null; "
        "if (target.current) focusIfDropped(focusTarget(target.current)); }); "
        "return useCallback((target: RefObject<HTMLElement | null>) => { pending.current = target; }, []);"
    )


def test_the_edit_toggle_arms_both_directions():
    # Mutants: `open` or `close` stops arming (the pressed button unmounts, focus drops).
    body = _fn_body(_HOOK, "export function useEditToggle<")
    assert "open: () => { setEditing(true); focusNext(editRef); }," in body
    assert "close: () => { setEditing(false); focusNext(openerRef); }," in body


def test_handoff_reads_focus_before_react_detaches_the_subtree():
    body = _HOOK[_HOOK.index("export function useFocusHandoff(") :]
    body = body[: body.index("\n}\n")]
    assert "useLayoutEffect(" in body
    # `useLayoutEffect` contains the letters `useEffect`; strip the layout call
    # before rejecting a passive effect. Swapping the layout effect for
    # `useEffect` removes the first assert and puts `useEffect(` in this string.
    assert "useEffect(" not in body.replace("useLayoutEffect(", "")
    assert "if (!root || !root.contains(document.activeElement)) return;" in body
    # Only a DROPPED focus moves: never take it from where the user put it.
    assert "queueMicrotask(() => focusIfDropped(back()));" in body


def test_return_point_is_remembered_while_attached_and_ends_at_the_main_area():
    body = _squash(_FOCUS[_FOCUS.index("export function focusReturnPoint(") :])
    assert "closest<HTMLElement>('[tabindex=\"-1\"]')" in body
    # An opted-in tabIndex={-1} ancestor wins over the main area.
    assert "chain.push(a);" in body
    # Mutant: never the element itself (a confirm skipped its still-connected opener).
    assert (
        "return () => el.isConnected ? el : "
        "(chain.find((a) => a.isConnected) ?? document.getElementById(MAIN_CONTENT_ID));"
    ) in body
    assert 'const MAIN_CONTENT_ID = "main-content";' in _FOCUS
    gutter = _read("components/sidebar-reveal-trigger.tsx")
    assert 'id="main-content"' in gutter and "tabIndex={-1}" in gutter


def test_a_data_less_retry_stays_a_load_failure():
    src = _read("lib/query-state.ts")
    body = src[src.index("export function isLoadFailure(") :]
    body = body[: body.index("\n}\n")]
    # Data held is never a load failure (a failed background refetch keeps the
    # loaded content); a paused retry (tab hidden) is still a fetch.
    assert (
        'query.data === undefined &&\n    (query.isError || (query.fetchStatus !== "idle" && query.errorUpdateCount > 0))'
        in body
    )


def test_the_formatting_layer_keeps_the_same_retry_rule():
    # The formatting layer keeps its own copy (a lib file cannot value-import
    # another). It is only asked when data is already undefined.
    formatting = _read("lib/formatting.ts")
    assert 'query.isError || (query.fetchStatus !== "idle" && query.errorUpdateCount > 0)' in formatting
    assert "The same rule as `isLoadFailure`" in formatting


def test_last_seen_keeps_a_value_a_refetch_cleared():
    hook = _read("hooks/use-last-seen.ts")
    body = hook[hook.index("export function useLastSeen") :]
    assert "if (value != null && value !== last) setLast(value);" in body
    assert "return value ?? last;" in body
    assert "useEffect(" not in body


def test_the_guard_flips_before_the_request_and_clears_on_settle():
    hook = _read("hooks/use-single-flight.ts")
    assert 'import { startOnce } from "@/lib/single-flight";' in hook
    assert _fn_body(hook, "export function useSingleFlight<") == (
        "const inFlight = useRef(false); return (vars) => startOnce(inFlight, mutate, vars);"
    )
    lock = _read("lib/single-flight.ts")
    # Mutant: the lock cleared right after `mutate` (a second click got through).
    # It opens in `onSettled` and nowhere else.
    assert _fn_body(lock, "export function startOnce<") == (
        "if (lock.current) return; lock.current = true; "
        "mutate(vars, { onSettled: () => { lock.current = false; }, });"
    )
    assert 'from "./single-flight.ts";' in _read("lib/single-flight.test.ts")


def test_the_qa_history_is_a_named_focus_target():
    qa = _read("components/qa-tab.tsx")
    assert re.search(
        r"<section tabIndex=\{-1\} aria-labelledby=\{historyHeadingId\}[^>]*>\s*"
        r"<h3 id=\{historyHeadingId\}",
        qa,
    )


# --- Task 17: studio focus never drops (F1, decision 11) -------------------


def _function(src: str, head: str) -> str:
    """One top-level function, from its signature to its closing brace."""
    start = src.index(head)
    return src[start : src.index("\n}\n", start)]


def _element(src: str, label: str, tag: str) -> str:
    """The JSX element carrying `aria-label="<label>"`, from `<tag` to `</tag>`."""
    at = src.index(f'aria-label="{label}"')
    start = src.rfind(f"<{tag}", 0, at)
    return src[start : src.index(f"</{tag}>", at)]


_SHELL = _read("components/resume-editor/editor-shell.tsx")
_BASE_STUDIO = _read("components/resume-editor/editor-body.tsx")
_TAILORED = _read("components/resume-editor/tailored-resume-studio.tsx")


def test_read_edit_blocks_focus_their_field_and_return_to_the_pencil():
    contact = _read("components/resume-editor/contact-form.tsx")
    for block in (
        _function(_BASE_STUDIO, "function SummaryBlock("),
        _function(_BASE_STUDIO, "function CertificationsBlock("),
        _function(contact, "export function ContactForm("),
    ):
        assert "const { editing, editRef, openerRef, open, close } = useEditToggle();" in block
        # Opening lands in the edit view's first field; Done lands on the pencil.
        assert "ref={editRef}" in block and "ref={openerRef}" in block
        assert "onClick={open}" in block and "onClick={close}" in block
        assert "setEditing(" not in block, "a bare toggle unmounts the pressed button"
        _assert_refs_sit_on_the_edit_root_and_the_pencil(block)


def _assert_refs_sit_on_the_edit_root_and_the_pencil(block: str) -> None:
    # Mutant: `editRef` on the Done row (opening landed on Done, not the
    # first field). It is the edit view's root, the first thing returned.
    edit_view = _squash(block[block.index("if (editing) {") :])
    assert edit_view.startswith("if (editing) { return ( <div ref={editRef} className="), block[:60]
    assert block.count("ref={editRef}") == 1
    assert block.count("ref={openerRef}") == 1
    pencil = _squash(block[block.index("ref={openerRef}") :])
    assert "onClick={open}" in pencil[: pencil.index("</Button>")]


def test_preview_toggles_hand_focus_to_each_other():
    show = _squash(_element(_SHELL, "Show PDF preview", "button"))
    assert "ref={showRef}" in show
    assert "onClick={() => { setCollapsed(false); focusNext(hideRef); }}" in show
    hide = _squash(_element(_SHELL, "Hide PDF preview", "Button"))
    assert "ref={hideRef}" in hide
    assert "onClick={() => { setCollapsed(true); focusNext(showRef); }}" in hide
    assert "const focusNext = useFocusOnNextCommit();" in _SHELL


def test_widen_and_narrow_keep_focus_at_their_limits():
    for label in ("Widen preview", "Narrow preview"):
        button = _element(_SHELL, label, "Button")
        assert "focusableWhenDisabled" in button, label
        assert "data-disabled:opacity-50" in button, label


def test_a_studio_remount_hands_focus_to_the_page_landmark():
    assert "useFocusHandoff(rootRef);" in _SHELL
    # Both branches' root is the same <div>; the ref must be on each.
    assert _SHELL.count('<div ref={rootRef} className="flex min-h-0 w-full flex-1">') == 2
    page = _read("components/resume-editor/fullscreen-editor-page.tsx")
    assert re.search(r"<main\s+tabIndex=\{-1\}\s+className=\"[^\"]*\boutline-none\b", page)


def test_overflow_menu_and_its_overlays_return_to_the_trigger():
    menu = _read("components/resume-editor/studio-overflow.tsx")
    assert "triggerRef: RefObject<HTMLButtonElement | null>;" in menu
    assert "ref={triggerRef}" in menu
    # Not an explicit finalFocus on the menu: that also overrode the initial
    # focus of an overlay an item opened. After a click the default returns
    # nowhere, so a dropped focus moves once the popup has unmounted.
    assert "finalFocus" not in _squash(menu[menu.index("<DropdownMenuContent") :])
    assert (
        "onOpenChangeComplete={(open) => { // Called just BEFORE the popup unmounts (focus is still on the item)."
        " if (!open) setTimeout(() => focusIfDropped(triggerRef.current), 0); }}"
    ) in _squash(menu)


def test_every_overlay_the_menu_opens_takes_a_return_target():
    assert re.search(
        r"<DialogContent\b[^>]*\bfinalFocus=\{finalFocus\}",
        _read("components/role-category-picker.tsx"),
    )
    for rel in (
        "components/resume-versions/version-history-sheet.tsx",
        "components/resume-editor/kb-import-drawer.tsx",
    ):
        assert re.search(r"<SheetContent\b[^>]*\bfinalFocus=\{finalFocus\}", _read(rel)), rel
    for studio in (_BASE_STUDIO, _TAILORED):
        assert "const overflowRef = useRef<HTMLButtonElement>(null);" in studio
        assert "triggerRef={overflowRef}" in studio
    # role, history, import (Ask for changes is lane 5's file: deferred)
    assert _BASE_STUDIO.count("finalFocus={overflowRef}") == 3
    assert _TAILORED.count("finalFocus={overflowRef}") == 1  # history


def test_leaving_the_raw_pane_returns_to_the_menu():
    for studio in (_BASE_STUDIO, _TAILORED):
        pane = _squash(studio[studio.index("<RawJsonToggle") :])
        pane = pane[: pane.index("/>")]
        # Apply and an unconfirmed Cancel unmount the pressed button.
        assert "onClose={() => { setRawMode(false); focusNext(overflowRef); }}" in pane
        # A confirmed discard closes behind its dialog, which then returns here.
        assert "exitFocus={() => overflowRef.current}" in pane
    toggle = _squash(_read("components/resume-editor/raw-json-toggle.tsx"))
    assert (
        "returnFocus: () => cancelRef.current?.isConnected ? cancelRef.current : (exitFocus?.() ?? null),"
        in toggle
    )
    # Mutant: the ref on Apply (a kept draft returned focus to Apply).
    assert '<Button onClick={apply}>Apply JSON</Button> <Button ref={cancelRef} variant="outline" onClick={cancel}>' in toggle
    assert toggle.count("ref={cancelRef}") == 1


def test_confirm_returns_to_its_opener_or_what_survived_it():
    src = _read("components/confirm-dialog.tsx")
    confirm = src[src.index("const confirm = useCallback<ConfirmFn>(") :]
    # Taken when the confirm OPENS: the confirmed action can remove the opener.
    assert "returnPoint.current = focusReturnPoint(document.activeElement);" in confirm[
        : confirm.index("setOpen(true)")
    ]
    assert "finalFocus={() => returnTo(opts?.returnFocus?.() ?? returnPoint.current())}" in _squash(src)
    # Base UI would focus a landmark's first tabbable child (Load latest landed
    # on "Back to application"): a tabIndex={-1} target is focused directly.
    helper = _squash(_function(src, "function returnTo("))
    assert "if (!target) return true;" in helper
    assert "if (target.tabIndex >= 0) return target; queueMicrotask(() => focusIfDropped(target)); return false;" in helper
    rebuild = _TAILORED[_TAILORED.index('title: "Rebuild from base resume?"') :]
    assert "returnFocus: () => overflowRef.current," in rebuild[: rebuild.index("});")]


def test_entry_cards_focus_their_editor_and_return_to_the_pencil():
    card = _read("components/resume-editor/editable-card.tsx")
    setter = _squash(card[card.index("const setEditing = (next: boolean) =>") :])
    setter = setter[: setter.index("};")]
    assert "focusNext(next ? editRef : pencilRef);" in setter
    assert "ref={pencilRef}" in _element(card, "Edit", "Button")
    assert "<EditPane ref={editRef} edit={edit} onClose={() => setEditing(false)} />" in card
    # Mutants: Done doing nothing, or the editor handed a no-op `close`.
    # Both must close through `onClose`, which returns focus to the pencil.
    assert _squash(_function(card, "function EditPane(")).endswith(
        '}) { return ( <div ref={ref} className="flex flex-col gap-3"> {edit(onClose)} '
        '<div className="flex justify-end"> <Button size="sm" onClick={onClose}> Done </Button> </div> </div> );'
    )


def test_chat_rail_toggles_hand_focus_to_each_other():
    chat = _read("components/chat/chat-page.tsx")
    hide = _squash(_element(chat, "Hide chat history", "Button"))
    assert "ref={hideRailRef}" in hide
    assert "onClick={() => { setHistoryCollapsed(true); focusNext(showRailRef); }}" in hide
    show = _squash(_element(chat, "Show chat history", "button"))
    assert "ref={showRailRef}" in show
    assert "onClick={() => { setHistoryCollapsed(false); focusNext(hideRailRef); }}" in show


_REFERRALS = _read("app/referrals/page.tsx")


def _icon_button(src: str, label: str) -> str:
    """A self-closing `<IconButton label="<label>" … />`."""
    at = src.index(f'label="{label}"')
    start = src.rfind("<IconButton", 0, at)
    return src[start : at + re.search(r"\n\s*/>", src[at:]).end()]


def test_referral_rows_move_focus_into_the_edit_row_and_back():
    row = _function(_REFERRALS, "function ReferralRow(")
    assert "useEditToggle<HTMLTableRowElement>();" in row
    assert "rowRef={editRef}" in row and "onDone={close}" in row
    assert "editButtonRef={openerRef}" in _squash(row) and "onEdit={open}" in row
    assert "ref={editButtonRef}" in _icon_button(_REFERRALS, "Edit")
    edit_row = _function(_REFERRALS, "function ReferralEditRow(")
    assert "<TableRow ref={rowRef}>" in edit_row
    # Save disables itself while it runs; a disabled <button> drops focus.
    save = edit_row[edit_row.index("onClick={save}") :]
    assert "focusableWhenDisabled" in save[: save.index("</Button>")]


def test_a_deleted_referral_hands_focus_to_what_survived_it():
    view = _function(_REFERRALS, "function ReferralViewRow(")
    assert "useFocusHandoff(rowRef);" in view and '<TableRow ref={rowRef} className="group">' in view
    assert "focusableWhenDisabled" in _icon_button(_REFERRALS, "Delete referral")
    table = _function(_REFERRALS, "function ReferralsTable(")
    # The last delete unmounts the whole table for the first-referral form.
    assert "useFocusHandoff(rootRef);" in table
    assert '<div ref={rootRef} tabIndex={-1} className="outline-none">' in table
