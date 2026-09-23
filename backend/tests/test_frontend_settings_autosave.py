"""Pins for a failed settings autosave (UX next, Task 12, U4.3).

A rejected write used to leave the check mark up. These pins keep the failed
state, the retry, and the leave guard on the cards that still show the unsaved
value.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _fn(source: str, head: str) -> str:
    start = source.index(head)
    return source[start : source.index("\n}\n", start)]


_HOOK = _read("lib/use-autosave.ts")
_STATUS = _read("components/settings/autosave-status.tsx")
_CARDS = (
    "components/settings/quick-tailor-section.tsx",
    "components/settings/job-preferences-section.tsx",
    "components/settings/market-section.tsx",
    "components/settings/mcp-workflow-section.tsx",
)
_AUTOSAVE_CARDS = _CARDS[:2]


def test_hook_reports_failure_and_can_retry():
    assert "failed" in _HOOK[_HOOK.index("return {") :]
    assert "retry" in _HOOK[_HOOK.index("return {") :]
    assert ".catch(() =>" not in _HOOK
    settle = _fn(_HOOK, "const settle = (")
    early = settle.index("queued.current !== inFlight.current")
    assert "setFailed" not in settle[:early]
    assert early < settle.index("setFailed(!ok)")


def test_status_admits_the_failure():
    # The render, not the comment: "Saves automatically" is the !failed branch.
    body = _STATUS[_STATUS.index("return (") :]
    assert "Not saved" in body
    assert "!failed" in body[: body.index("Saves automatically")]


def test_cards_pass_the_failed_state():
    for rel in _CARDS:
        assert "failed=" in _read(rel), rel
    for rel in _AUTOSAVE_CARDS:
        src = _read(rel)
        assert "onRetry={retry}" in src, rel
        assert "useLeaveGuard(failed)" in src, rel


def test_mcp_switch_stays_focusable_while_saving():
    src = _read("components/settings/mcp-workflow-section.tsx")
    assert "disabled={save.isPending}" not in src
    assert "if (!save.isPending)" in src
