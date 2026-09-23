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


def test_history_rail_is_gated_on_the_chat_column_not_the_viewport():
    assert "@container/chat" in _CHAT
    assert re.search(
        r'<aside className="hidden w-64 shrink-0 flex-col gap-3 @2xl/chat:flex"',
        _CHAT,
    )
    # The Sheet trigger shows exactly when the rail cannot.
    assert "@2xl/chat:hidden" in _CHAT
    assert "md:flex" not in _CHAT and "md:hidden" not in _CHAT


def test_history_sheet_closes_when_the_rail_can_show():
    assert "new ResizeObserver(" in _CHAT and "42 * rem" in _CHAT
    assert 'matchMedia("(max-width: 767px)")' not in _CHAT
