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
