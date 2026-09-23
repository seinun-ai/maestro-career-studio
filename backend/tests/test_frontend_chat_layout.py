"""The chat history rail is gated on the chat column, not the viewport.

At 768 the pinned sidebar leaves the column too narrow for a 256px rail plus
the composer. A `md:` class cannot see the sidebar, so the rail uses a
container query. See UX next Task 10.
"""

from __future__ import annotations

import re
from pathlib import Path

_CHAT = (
    Path(__file__).resolve().parents[2] / "frontend/components/chat/chat-page.tsx"
).read_text()


def _tag(marker: str) -> str:
    """The JSX opening tag that contains `marker`."""
    at = _CHAT.index(marker)
    end = re.compile(r"\n\s*/?>").search(_CHAT, at)
    assert end is not None
    return _CHAT[_CHAT.rindex("<", 0, at + 1) : end.start()]


def test_history_rail_is_gated_on_the_chat_column_not_the_viewport():
    # The container is the root the rail and the thread share, not any element.
    assert re.search(r'ref=\{rootRef\}\s*className="@container/chat ', _CHAT)
    assert re.search(
        r'<aside ref=\{railRef\} className="hidden w-64 shrink-0 flex-col gap-3 @2xl/chat:flex"',
        _CHAT,
    )
    # The Sheet trigger shows exactly when the rail cannot.
    assert '<div className="flex items-center pb-2 @2xl/chat:hidden">' in _CHAT
    assert "md:flex" not in _CHAT and "md:hidden" not in _CHAT


def test_the_collapsed_rails_edge_button_uses_the_same_gate():
    edge = _tag('aria-label="Show chat history"')
    assert re.search(r'className="[^"]* hidden [^"]*@2xl/chat:flex"', edge)


def test_history_sheet_closes_when_the_rail_can_show():
    assert "new ResizeObserver(" in _CHAT
    assert "if (entry.contentRect.width >= 42 * rem) setHistorySheetOpen(false);" in _CHAT
    assert 'matchMedia("(max-width: 767px)")' not in _CHAT


def test_closing_the_sheet_never_focuses_its_hidden_opener():
    # Cmd+B at 768 widens the column, the observer closes the Sheet, and the
    # "Chat history" opener is display:none: focus went to <body>.
    assert "finalFocus={historySheetFinalFocus}" in _tag("<SheetContent")
    assert "if (opener && opener.getClientRects().length > 0) return opener;" in _CHAT
    assert "return railRef.current ?? showRailRef.current;" in _CHAT
    assert "ref={historyButtonRef}" in _tag('aria-label="Chat history"')
    assert "ref={railRef}" in _tag("<aside")
    assert "ref={showRailRef}" in _tag('aria-label="Show chat history"')


def test_the_conversation_column_is_a_focus_target():
    assert re.search(r"<main tabIndex=\{-1\} className=\"[^\"]*outline-none", _CHAT)


def test_a_long_pinned_resume_name_truncates_instead_of_widening_the_row():
    trigger = _tag('aria-label="Pinned resume"')
    assert re.search(r'className="[^"]*\bw-auto max-w-48 min-w-0\b', trigger)
    assert "title={pinnedName}" in trigger
    assert '<span className="truncate">{pinnedName}</span>' in _CHAT
