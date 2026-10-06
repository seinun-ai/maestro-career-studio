"""Every action answers (visual-language plan, Wave 2).

The Button primitive owns its loading state: `pending` shows a spinner, keeps the button focusable and
busy, and ignores presses. Base UI marks a disabled button `data-disabled`, which the primitive styles
itself, so call sites stop repeating the class by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_the_button_has_a_pending_state():
    src = _read("components/ui/button.tsx")
    assert "pending?: boolean" in src
    assert "aria-busy={pending || undefined}" in src
    assert "focusableWhenDisabled={pending || focusableWhenDisabled}" in src
    assert "disabled={disabled || pending}" in src and "Loader2" in src


def test_the_button_styles_data_disabled_itself():
    src = _read("components/ui/button.tsx")
    assert "data-disabled:pointer-events-none" in src and "data-disabled:opacity-50" in src


# file -> the slow-action labels it owns; each one's Button passes `pending=` (the lookbehind keeps
# `data-pending={` and `aria-pending={` from counting).
_PENDING_SITES = {
    "app/new/page.tsx": ["Save job"],
    "components/qa-tab.tsx": ["Answer questions", "Write cover letter"],
    "components/resume-health/finding-cards.tsx": ["Apply suggestion", "Write new wording"],
    "components/resume-health/demonstrate-skill-dialog.tsx": ["Write new wording"],
    "components/resume-health/question-pass.tsx": ["Write N new wordings"],
    "components/career/send-to-resume-dialog.tsx": ["Adapt and preview"],
    "app/jobs/[id]/page.tsx": ["Queue in Agent inbox"],
    "components/proposals/triage-actions.tsx": ["Skip (dialog)", "Queue (bulk)"],
    "components/career/inbox-panel.tsx": ["Approve"],
}


def test_slow_actions_show_pending():
    for rel, labels in _PENDING_SITES.items():
        found = len(re.findall(r"(?<![-\w])pending=\{", _read(rel)))
        assert found >= len(labels), f"{rel}: {labels} need {len(labels)} pending=, found {found}"


def test_approve_does_not_say_saving():
    row = _read("components/career/inbox-panel.tsx").split("function DraftRow(", 1)[1]
    assert "Approving…" in row and '"Saving…"' not in row


def test_only_the_bulk_queue_spins():
    bar = _read("components/proposals/triage-actions.tsx").split("export function BulkBar(", 1)[1]
    queue = bar.split("onClick={onQueue}", 1)[1].split("</Button>", 1)[0]
    skip = bar.split("onClick={onDecline}", 1)[1].split("</Button>", 1)[0]
    assert "pending={queuePending}" in queue
    assert "pending={" not in skip and "disabled={pending}" in skip


def test_status_change_is_optimistic_and_awaits_the_refetch():
    page = _read("app/applications/page.tsx")
    # Up to the next mutation, as test_frontend_focus.py slices it: the body itself contains "});".
    block = page.split("const patchStatus = useMutation", 1)[1].split("const deleteApp = useMutation(", 1)[0]
    assert "onMutate" in block and "setQueriesData" in block
    assert "onSettled" in block and "return qc.invalidateQueries" in block
    assert "qc.setQueryData(key, rows)" in block  # a failed PATCH rolls back


def test_the_job_header_status_patch_is_optimistic_too():
    panel = _read("components/application-panel.tsx")
    block = panel.split("const patch = useMutation", 1)[1].split("const deleteApp = useMutation(", 1)[0]
    assert "onMutate" in block and "setQueryData" in block and "onError" in block
    assert "onSettled" in block and "return qc.invalidateQueries" in block


def test_a_pending_status_chip_cannot_be_changed_again():
    chip = _read("components/status-chip.tsx")
    body = chip.split("export function StatusChip", 1)[1]
    # Focusable while pending: a native disabled button drops focus to <body> when the menu closes.
    assert "aria-disabled={pending || undefined}" in body
    assert not re.search(r"(?<![-\w])disabled=\{pending\}", body)
    assert "open={open && !pending}" in body and "if (!pending && s !== current)" in body


def test_the_status_chip_cross_fades_and_confirms():
    chip = _read("components/status-chip.tsx")
    assert "transition-[background-color,color" in chip
    assert "data-confirm" in chip and "animate-confirm" in chip
    # A plain class cannot take a variant: it must be a registered utility.
    css = _read("app/globals.css")
    assert "@utility animate-confirm" in css and ".animate-confirm {" not in css


def test_the_confirm_pulse_skips_a_rollback():
    body = _read("components/status-chip.tsx").split("export function StatusChip", 1)[1]
    assert "if (pending || settled.current === current) return;" in body


def test_inbox_actions_toast_from_the_hook():
    hook = _read("components/proposals/triage-actions.tsx")
    assert 'toast.success("Queued. A connected agent can apply to it now.")' in hook
    assert 'toast.success("Proposal skipped")' in hook
    assert "Kept. It's back in To review." in hook
    assert '"Queued" : "Skipped"' in hook and '"proposal" : "proposals"' in hook  # the bulk sentences
    page = _read("app/jobs/[id]/page.tsx")
    assert "Queued. A connected agent" not in page and "Kept. It's back" not in page
    assert 'toast.success("Skipped")' not in page


def test_inbox_rows_leave_with_an_exit_transition():
    section = _read("components/proposals/proposals-section.tsx")
    assert "data-leaving" in section and "collapse-exit" in section and "grid-rows-[0fr]" not in section
    assert "actingIds" in section and 'data-pending={acting ? "true" : undefined}' in section
    hook = _read("components/proposals/triage-actions.tsx")
    assert "actingIds" in hook and "ROW_EXIT_MS" in hook


def test_the_bulk_bar_slides_up_on_mount():
    bar = _read("components/proposals/triage-actions.tsx").split("export function BulkBar(", 1)[1]
    assert "animate-in slide-in-from-bottom-2 fade-in-0 duration-(--duration-short4)" in bar


def test_reversible_actions_offer_undo():
    for rel in ("components/career/inbox-panel.tsx", "components/career/points-list.tsx", "app/base-resumes/page.tsx"):
        src = _read(rel)
        assert 'label: "Undo"' in src, rel
    # Undo answers too: its own failure toast, and the draft Approve stays pinned to its busy label.
    assert "couldnt(\"undo the approval\"" in _read("components/career/inbox-panel.tsx")
    assert "couldnt(\"undo the archive\"" in _read("app/base-resumes/page.tsx")
    # Skip and Queue are not reversible by the server (D8): no Undo in the triage hook.
    assert 'label: "Undo"' not in _read("components/proposals/triage-actions.tsx")


def test_a_leaving_entry_is_pruned_when_the_refetch_drops_it():
    section = _read("components/proposals/proposals-section.tsx")
    effect = section.split("// Clear an id once the refetched list no longer holds it as it was", 1)[1].split("}, [items, leavingIds]);", 1)[0]
    assert "now.get(id) === status" in effect and "setLeavingIds(new Map(rest))" in effect
    assert "[&_button]:opacity-0!" in section  # beats the button's own data-disabled:opacity-50


def test_copy_uses_one_hook_with_an_error_path():
    hook = _read("hooks/use-copy.ts")
    assert "navigator.clipboard.writeText" in hook and "catch" in hook and "couldnt(" in hook
    assert "onError" in hook
    for rel in ("components/qa-tab.tsx", "components/automations/automation-card.tsx",
                "components/resume-editor/editor-body.tsx"):
        src = _read(rel)
        assert "useCopy" in src or "CopyButton" in src, rel
        assert "navigator.clipboard" not in src, rel


def test_the_copy_button_confirms_in_place_and_aloud():
    btn = _read("components/copy-button.tsx")
    assert "Copied" in btn and 'aria-live="polite"' in btn and "data-show" in btn
    # D2: a done state is CircleCheck, never Check.
    # Tailwind v4 translate-y-* sets `translate`, not `transform`, so that is what must transition.
    assert "transition-[opacity,translate]" in btn and "transform" not in btn
    assert "CircleCheck" in btn and not re.search(r"\bCheck\b", btn.replace("CircleCheck", ""))


def test_qa_history_waits_before_saying_empty():
    src = _read("components/qa-tab.tsx")
    # The skeleton stands in while the history query has no data; "No answers yet." only after it loaded.
    pending = src.index("entries === undefined ?")
    assert "<Skeleton" in src[pending : src.index("No answers yet.")]
    assert "No answers yet." in src[src.index("entries.length === 0") :]


def test_an_existing_chat_does_not_greet_while_loading():
    src = _read("components/chat/chat-page.tsx")
    start = src.index("sessionId !== null && detail.isPending ?")
    branch = src[start : src.index("What are we working on?")]
    assert "<Skeleton" in branch and 'aria-busy="true"' in branch
