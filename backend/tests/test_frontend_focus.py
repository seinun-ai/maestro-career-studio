"""Pins for the focus-return and single-flight helpers (UX next, Task 8).

Node tests cover `isLoadFailure`, the focus helpers (`lib/focus.test.ts`) and
the single-flight lock (`lib/single-flight.test.ts`); they are not in CI, so
the predicates and the hook shapes are pinned here as source text. Each pin
below was seen to fail on the mutant it names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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
    assert 'import { finalFocusOn, focusIfDropped, focusReturnPoint, focusTarget } from "@/lib/focus";' in _HOOK
    assert "export { focusIfDropped, focusReturnPoint };" in _HOOK
    names = ("focusIfDropped", "focusReturnPoint", "focusSuccessor", "focusTarget", "finalFocusOn", "holdsDraft")
    for name in names:
        assert f"function {name}(" not in _HOOK, name
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
    # nowhere; the `DropdownMenu` primitive moves a dropped focus to ⋯ (pinned
    # by test_every_menu_returns_a_dropped_focus_to_its_trigger).
    assert "finalFocus" not in _squash(menu[menu.index("<DropdownMenuContent") :])


def test_every_overlay_the_menu_opens_takes_a_return_target():
    assert re.search(
        r"<DialogContent\b[^>]*\bfinalFocus=\{finalFocus\}",
        _read("components/role-category-picker.tsx"),
    )
    for rel in (
        "components/resume-versions/version-history-sheet.tsx",
        "components/resume-editor/kb-import-drawer.tsx",
        "components/resume-editor/instruct-sheet.tsx",
    ):
        assert re.search(r"<SheetContent\b[^>]*\bfinalFocus=\{finalFocus\}", _read(rel)), rel
    for studio in (_BASE_STUDIO, _TAILORED):
        assert "const overflowRef = useRef<HTMLButtonElement>(null);" in studio
        assert "triggerRef={overflowRef}" in studio
    # role, history, import, Ask for changes
    assert _BASE_STUDIO.count("finalFocus={overflowRef}") == 4
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
    assert 'import { finalFocusOn, focusReturnPoint } from "@/lib/focus";' in src
    assert "finalFocus={() => finalFocusOn(opts?.returnFocus?.() ?? returnPoint.current())}" in _squash(src)


def test_a_landmark_return_target_is_focused_directly():
    # Base UI would focus a landmark's first tabbable child (Load latest landed
    # on "Back to application"): a tabIndex={-1} target is focused directly.
    # Mutant: the landmark handed back to Base UI.
    assert _fn_body(_FOCUS, "export function finalFocusOn(") == (
        "if (!target) return true; if (target.tabIndex >= 0) return target; "
        "queueMicrotask(() => focusIfDropped(target)); return false;"
    )
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


# --- Browser verification: focus drops the lanes left behind -----------------


def _button_with(src: str, marker: str) -> str:
    """The `<Button …>…</Button>` element whose source contains `marker`, whitespace squashed."""
    at = src.index(marker)
    return _squash(src[src.rfind("<Button", 0, at) : src.index("</Button>", at)])


_NBR = _read("components/base-resumes/new-base-resume-dialog.tsx")
_DEMONSTRATE = _read("components/resume-health/demonstrate-skill-dialog.tsx")
_SEND = _read("components/career/send-to-resume-dialog.tsx")
_CAPTURE = _read("components/career/capture-box.tsx")
_NEW_ENTITY = _read("components/career/new-entity-dialog.tsx")
_FINDINGS = _read("components/resume-health/finding-cards.tsx")
_CAREER_PAGE = _read("app/career/page.tsx")
_DROPDOWN = _read("components/ui/dropdown-menu.tsx")
_OVERFLOW = _read("components/resume-editor/studio-overflow.tsx")
_NEW_JOB = _read("app/new/page.tsx")


@pytest.mark.parametrize(
    ("src", "marker"),
    [
        (_NBR, "onClick={() => proposeOnce()}"),  # Suggest a selection
        (_NBR, "onClick={() => submit()}"),  # Create
        (_DEMONSTRATE, "onClick={() => draftOnce()}"),  # Draft rewrite
        (_DEMONSTRATE, "onClick={() => applyOnce()}"),  # Apply
        (_SEND, "onClick={() => portOnce()}"),  # Send as-is
        (_SEND, "onClick={() => adaptOnce()}"),  # Adapt & preview
        (_SEND, "onClick={() => applyOnce()}"),  # Apply N to resume
        (_CAPTURE, '"From document"'),  # Read document
        (_NEW_ENTITY, 'form="new-career-entity"'),  # Add career item
        (_NEW_JOB, "onClick={() => extract(undefined)}"),  # Extract job on /new
        (_read("components/settings/persona-section.tsx"), "onClick={() => draftOnce(editRevision.current)}"),  # Draft from my career
        (_read("components/settings/model-catalog-panel.tsx"), "sync.mutate(provider)"),  # Find models
        (_read("components/settings/models-section.tsx"), "aria-label={`Test ${name}`}"),  # Test a model
    ],
    ids=["suggest", "nbr-create", "draft", "demo-apply", "send-as-is", "adapt", "send-apply", "from-doc", "add-item", "extract", "persona-draft", "sync", "model-test"],
)
def test_a_button_that_disables_itself_while_it_works_keeps_focus(src, marker):
    # Mutant: `focusableWhenDisabled` dropped (a native `disabled` drops focus to <body>).
    button = _button_with(src, marker)
    assert "focusableWhenDisabled" in button, marker
    assert "data-disabled:opacity-50" in button, marker
    assert "data-disabled:pointer-events-none" in button, marker


def test_read_document_opens_one_picker_per_gesture():
    # Mutant: the guard removed (a double click opened two file pickers).
    button = _button_with(_CAPTURE, '"From document"')
    assert "onClick={(event) => { if (event.detail > 1) return; fileInputRef.current?.click(); }}" in button


def test_adapt_hands_focus_to_the_review_apply():
    # Adapt's button unmounts with the select step; its success lands on Apply.
    success = _squash(_SEND[_SEND.index("const adapt = useMutation(") : _SEND.index("const apply = useMutation(")])
    assert 'setStep("review"); focusNext(applyRef);' in success
    assert "const focusNext = useFocusOnNextCommit();" in _SEND
    assert "ref={applyRef}" in _button_with(_SEND, "onClick={() => applyOnce()}")
    assert _SEND.count("ref={applyRef}") == 1


def test_a_demonstrated_skill_returns_focus_to_a_live_chip():
    # Apply disables the chip that opened the dialog ("· done"): Base UI's
    # return to it landed on <body>. Mutants: no finalFocus, or the opener
    # returned even when disabled.
    assert re.search(r"<DialogContent\b[^>]*\bfinalFocus=\{finalFocus\}", _DEMONSTRATE)
    body = _squash(_function(_FINDINGS, "function NotesTable("))
    assert (
        "const returnFrom = (subject: string) => () => { "
        'const chips = Array.from( sectionRef.current?.querySelectorAll<HTMLButtonElement>("button[data-skill]") ?? [], ); '
        "const at = Math.max(0, chips.findIndex((chip) => chip.dataset.skill === subject)); "
        "const live = [...chips.slice(at), ...chips.slice(0, at)].find((chip) => !chip.disabled); "
        "if (live) return live; queueMicrotask(() => focusIfDropped(sectionRef.current)); return false; };"
    ) in body
    assert "finalFocus={returnFrom(s)}" in body
    assert "data-skill={subject}" in body
    assert '<section ref={sectionRef} id="notes" tabIndex={-1} hidden={hidden} className="' in body


def test_new_career_item_returns_focus_to_its_opener_or_the_new_card():
    # `autoFocus` focused the title before Base UI recorded the opener, so every
    # close returned focus to the unmounted title: <body>.
    assert not re.search(r"(?<![`\w])autoFocus(?![`\w])", _NEW_ENTITY), "an autoFocus prop"
    assert re.search(r"<DialogContent\b[^>]*\binitialFocus=\{titleRef\}", _NEW_ENTITY)
    assert _NEW_ENTITY.count("ref={titleRef}") == 1
    title = _squash(_NEW_ENTITY)
    title = title[title.index('<Input id="career-entity-title"') :]
    assert "ref={titleRef}" in title[: title.index("/>")]
    # A create closes once the refetched list holds the new card, and lands on it.
    success = _squash(_NEW_ENTITY[_NEW_ENTITY.index("onSuccess: async (entity) =>") :])
    success = success[: success.index("onError:")]
    assert (
        'created.current = entity.id; await queryClient.invalidateQueries({ queryKey: ["kb", "entities"] }); '
        "onOpenChange(false); reset();"
    ) in success
    assert (
        "finalFocus={() => { const id = created.current; created.current = null; "
        "return (id ? landOn?.(id) : null) ?? true; }}"
    ) in _squash(_NEW_ENTITY)
    assert (
        "landOn={(id) => document.querySelector<HTMLElement>( "
        '`#kb-entities [role="tabpanel"]:not([inert]) a[href="/career/${id}"]`, ) }'
    ) in _squash(_CAREER_PAGE)


def test_every_menu_returns_a_dropped_focus_to_its_trigger():
    # One fix in the primitive: after a click Base UI returns focus nowhere.
    # Mutants: the timeout removed, or the modal guard removed (focus stolen
    # from behind an overlay an item opened).
    menu = _squash(_function(_DROPDOWN, "function DropdownMenu("))
    assert "if (open) trigger.current = details.trigger onOpenChange?.(open, details)" in menu
    assert (
        "onOpenChangeComplete?.(open) "
        "// Called just BEFORE the popup unmounts (focus is still on the item). "
        "if (!open) setTimeout(() => returnToTrigger(trigger.current), 0)"
    ) in menu
    helper = _squash(_function(_DROPDOWN, "function returnToTrigger("))
    assert (
        "if (!(trigger instanceof HTMLElement) || trigger.closest('[aria-hidden=\"true\"], [inert]')) return "
        "focusIfDropped(trigger)"
    ) in helper
    # The studio's own copy is gone: the primitive covers it.
    assert "onOpenChangeComplete={" not in _OVERFLOW


def test_every_editor_takes_a_focus_the_navigation_dropped():
    # Create on /templates or New base résumé navigates into an editor: what
    # held focus unmounts, so the editor's landmark takes a focus left on
    # <body>. The shell does it, so all three editors (both studios and the
    # template editor) get it; a stable module ref runs on mount only.
    shell = _read("components/resume-editor/fullscreen-editor-page.tsx")
    assert 'import { focusIfDropped } from "@/lib/focus";' in shell
    assert re.search(r"<main\s+tabIndex=\{-1\}\s+className=\"[^\"]*\"\s+ref=\{focusIfDropped\}>", shell)
    for rel in ("app/templates/[id]/page.tsx", "app/base-resumes/[slug]/page.tsx", "app/applications/[id]/resume/page.tsx"):
        assert "<FullscreenEditorPage>" in _read(rel), rel


# --- Task 21 sweep: the last focus drops ------------------------------------


def test_a_kept_mounted_dialog_returns_to_the_element_that_opened_it():
    # A kept-mounted dialog keeps what a nested popup recorded (the role
    # picker's list records the dialog's first tab) connected but hidden, and
    # Base UI's default return focused it: <body>. Mutants: finalFocus dropped
    # from the dialog; the opener read in a passive effect (initial focus has
    # already moved into the dialog by then); read on close instead of open.
    hook = _squash(_function(_HOOK, "export function useOpenerReturn("))
    assert (
        "const opener = useRef<() => HTMLElement | null>(() => null); "
        "useLayoutEffect(() => { if (open) opener.current = focusReturnPoint(document.activeElement); }, [open]); "
        "return useCallback(() => finalFocusOn(opener.current()), []);"
    ) in hook
    wrapper = _NBR[_NBR.index("export function NewBaseResumeDialog(") : _NBR.index("\nfunction NewBaseResumeForm(")]
    assert "const returnToOpener = useOpenerReturn(open);" in wrapper
    assert '<DialogContent size="lg" keepMounted ref={popupRef} finalFocus={returnToOpener}>' in wrapper


def test_every_kept_mounted_dialog_names_its_return_target():
    # Base UI's default return target is only safe when closing unmounts the popup.
    offenders = [
        f"{p.relative_to(_FRONTEND)}: {tag}"
        for root in ("app", "components")
        for p in sorted((_FRONTEND / root).rglob("*.tsx"))
        if "components/ui/" not in str(p)
        for tag in re.findall(r"<(?:Dialog|Sheet)Content\b[^>]*\bkeepMounted\b[^>]*>", p.read_text())
        if "finalFocus=" not in tag
    ]
    assert offenders == [], offenders


def test_a_list_item_hands_focus_to_its_neighbour_then_its_landmark():
    # Mutants: previous before next; the item itself (still connected at menu
    # close) as the fallback; siblings read late, after the item has gone; the
    # neighbour's matching control ignored.
    assert (
        "export function focusSuccessor(item: Element | null | undefined, control?: string): () => HTMLElement | null {"
    ) in _FOCUS
    body = _fn_body(_FOCUS, "export function focusSuccessor(")
    assert body == (
        "const siblings = [item?.nextElementSibling, item?.previousElementSibling]; "
        "const landmark = focusReturnPoint( "
        "item?.parentElement?.closest<HTMLElement>('[tabindex=\"-1\"]') ?? document.getElementById(MAIN_CONTENT_ID), ); "
        "return () => { const sibling = siblings.find((s): s is HTMLElement => s instanceof HTMLElement && s.isConnected); "
        "if (!sibling) return landmark(); "
        "return (control ? sibling.querySelector<HTMLElement>(control) : null) ?? focusTarget(sibling); };"
    )


_BASE_LIST = _read("app/base-resumes/page.tsx")


def test_archiving_a_card_hands_focus_to_the_next_card():
    # Archive removes the card and the ⋯ that held focus. Once the menu's popup
    # is gone, a dropped focus lands on the next card's link, else the previous,
    # else the list (a refetch can beat the menu's close, and the card's menu
    # unmounts with it). Only an archive that hides the card moves focus; every
    # close returns false so an overlay an item opened keeps its focus.
    # Mutants: the successor read after the refetch; `leaving` never cleared;
    # the guard on `hidesArchived` dropped (Show archived keeps the card).
    menu = _squash(_function(_BASE_LIST, "function CardMenu("))
    assert "const triggerRef = useRef<HTMLButtonElement>(null);" in menu
    assert "const leaving = useRef<(() => HTMLElement | null) | null>(null);" in menu
    assert (
        "finalFocus={() => { const back = leaving.current; leaving.current = null; "
        "if (back) queueMicrotask(() => focusIfDropped(back())); return false; }}"
    ) in menu
    assert (
        "onClick={() => { if (hidesArchived && !resume.archived_at) "
        "leaving.current = focusSuccessor(triggerRef.current?.closest('[data-slot=\"card\"]')); onToggleArchive(); }}"
    ) in menu
    assert "ref={triggerRef}" in menu
    page = _squash(_BASE_LIST)
    assert '<section aria-label="Your base resumes" tabIndex={-1} className="flex flex-col gap-4 outline-none">' in page
    assert "hidesArchived={!showArchived}" in page


def test_deleting_a_card_hands_focus_to_the_next_card():
    # A confirmed delete removes the card and the ⋯ Base UI would return to.
    # Mutants: the successor never handed over on success; Cancel sent to the
    # successor too (it must return to ⋯); Delete natively disabled.
    menu = _squash(_function(_BASE_LIST, "function CardMenu("))
    assert "onClick={() => onDelete(focusSuccessor(triggerRef.current?.closest('[data-slot=\"card\"]')))}" in menu
    page = _squash(_BASE_LIST)
    assert "onDelete={(next) => { deleteNext.current = next; setDeleteTarget(r); }}" in page
    success = page[page.index("const del = useMutation(") :]
    assert 'toast.success("Deleted"); afterDelete.current = deleteNext.current; setDeleteTarget(null);' in success
    assert (
        "<DialogContent finalFocus={() => { const back = afterDelete.current; afterDelete.current = null; "
        "return back ? finalFocusOn(back()) : true; }} >"
    ) in page
    button = _button_with(_BASE_LIST, "onClick={() => deleteTarget && del.mutate(deleteTarget.slug)}")
    assert "focusableWhenDisabled" in button and "data-disabled:opacity-50" in button


_TRACKER = _read("app/applications/page.tsx")
_STATUS_CHIP = _read("components/status-chip.tsx")


def test_a_status_change_that_filters_out_its_row_hands_focus_to_the_next_chip():
    # Under a status filter, picking another status takes the row (and the
    # chip focus went back to) out of the list once the refetch lands: focus
    # fell to <body>. The successor is read when the status is picked, while
    # the row is there, and handed over after the commit that drops it.
    # Mutants: the successor read in the effect (the row is gone by then); a
    # passive effect (focus sits on <body> for a frame, until after paint); the
    # `filter` guard dropped (a change that keeps the row arms a stale move);
    # `leaving` not cleared on a failed PATCH; no control, so focus lands on
    # the next row instead of its chip; the marker gone from the chip.
    page = _squash(_TRACKER)
    assert "const leaving = useRef<{ key: string; next: () => HTMLElement | null } | null>(null);" in page
    patch = page[page.index("const patchStatus = useMutation(") : page.index("const deleteApp = useMutation(")]
    assert "onError: (err: Error) => { leaving.current = null; toast.error(err.message); }," in patch
    assert (
        "useLayoutEffect(() => { const l = leaving.current; if (!l || filtered.some((r) => rowKey(r) === l.key)) return; "
        "leaving.current = null; focusIfDropped(l.next()); }, [filtered]);"
    ) in page
    assert (
        'onSelect={(status) => { if (filter !== "all" && filter !== status) leaving.current = { key, '
        'next: focusSuccessor( document.querySelector(`[data-row="${key}"]`), "[data-status-chip]", ), }; '
        "patchStatus.mutate({ id: r.app.id, status }); }}"
    ) in page
    assert "<TableRow key={key} data-row={key}" in page
    chip = _squash(_function(_STATUS_CHIP, "export function StatusChip("))
    assert '<button type="button" data-status-chip' in chip


# --- The studio's ⋯ → Role dialog ---------------------------------------------

_ROLE_PICKER = _read("components/role-picker.tsx")
_ROLE_DIALOG = _read("components/role-category-picker.tsx")


def test_the_role_picker_stays_focusable_while_its_pick_saves():
    # The dialog's picker disabled itself while the PATCH ran, and a disabled
    # input drops focus to <body> with the dialog still open. Mutants: the save
    # back in `disabled`; `readOnly` not forwarded to either Combobox.Root; the
    # picker's own Backspace and Enter handlers still committing while it saves.
    picker = _squash(_ROLE_DIALOG[_ROLE_DIALOG.index("<RolePicker") : _ROLE_DIALOG.index("/>", _ROLE_DIALOG.index("<RolePicker"))])
    assert "readOnly={save.isPending}" in picker
    assert "disabled={!options}" in picker
    roots = re.findall(r"<Combobox\.Root<[^>]*>[^>]*?>", _ROLE_PICKER, re.S)
    assert len(roots) == 2 and all("readOnly={props.readOnly}" in root for root in roots), roots
    keys = _squash(_ROLE_PICKER[_ROLE_PICKER.index("onKeyDown={(event) => {") :])
    assert keys.startswith("onKeyDown={(event) => { if (props.readOnly) return;"), keys[:120]


def test_escape_on_a_closed_role_list_never_clears_the_role():
    # Base UI clears the value on Escape when the list is closed and swallows
    # the key, so Esc meant for the Role dialog PATCHed the role to Unknown and
    # left the dialog open (focus on <body> while it saved). A role is cleared
    # from its Clear role row or Backspace. Mutant: the guard removed.
    keys = _squash(_ROLE_PICKER[_ROLE_PICKER.index("onKeyDown={(event) => {") :])
    assert (
        'if ( event.key === "Escape" && event.currentTarget.getAttribute("aria-expanded") !== "true" ) '
        "{ event.preventBaseUIHandler(); return; }"
    ) in keys
