"""Pins for a failed settings autosave (UX next, Task 12, U4.3, plus the review fixes).

A rejected write used to leave the check mark up. These pins keep the failed
state, the retry, the leave guard on the cards that still show the unsaved
value, and focus that never jumps out of a field mid-typing.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _flat(source: str) -> str:
    return " ".join(source.split())


def _arrow(source: str, head: str) -> str:
    start = source.index(head)
    return source[start : source.index("\n  };", start)]


_HOOK = _read("lib/use-autosave.ts")
_STATUS = _read("components/settings/autosave-status.tsx")
_AUTOSAVE_CARDS = (
    "components/settings/quick-tailor-section.tsx",
    "components/settings/job-preferences-section.tsx",
)
_SERVER_VALUE_CARDS = (
    "components/settings/market-section.tsx",
    "components/settings/mcp-workflow-section.tsx",
)


def test_hook_returns_the_failed_state_and_retry():
    returned = _HOOK[_HOOK.index("return {") :]
    assert "failed" in returned
    assert "retry" in returned
    assert ".catch(() =>" not in _HOOK


def test_a_rejected_write_settles_as_failed():
    flush = _flat(_arrow(_HOOK, "const flush = () => {"))
    assert "commit(next).then( () => settle(true), () => settle(false), );" in flush


def test_only_the_newest_write_decides_failed():
    settle = _arrow(_HOOK, "const settle = (")
    early = _flat(settle[: settle.index("inFlight.current = null;")])
    # The early return keeps an outcome with a newer value queued from deciding.
    assert "if (queued.current !== inFlight.current) { flush(); return; }" in early
    assert "setFailed" not in early
    assert "setFailed(!ok);" in settle


def test_retry_resends_only_when_nothing_is_in_flight():
    retry = "const retry = () => { if (inFlight.current === null) flush(); };"
    assert retry in _flat(_HOOK)


def test_status_admits_the_failure():
    # The render, not the comment: "Saves automatically" is the !failed branch.
    body = _STATUS[_STATUS.index("return (") :]
    assert "Not saved" in body
    assert "!failed" in body[: body.index("Saves automatically")]
    assert 'failed && !pending ? "text-destructive"' in body  # never red while saving
    assert "{failed && onRetry ? (" in body


def test_try_again_calls_the_retry():
    click = _flat(_STATUS[_STATUS.index("onClick={() => {") :])
    assert click.startswith("onClick={() => { refocus.current = true; onRetry(); }}")


def test_focus_moves_only_after_a_successful_retry_and_only_if_dropped():
    # A layout effect: a passive one paints a frame with focus on <body> first.
    effect = _flat(_STATUS[_STATUS.index("useLayoutEffect(") : _STATUS.index("}, [failed, pending]);")])
    # Waits for the retry to settle, then disarms either way: a failed retry
    # left armed made the NEXT ordinary save pull focus mid-typing.
    assert "if (!refocus.current || pending) return; refocus.current = false;" in effect
    assert "if (!failed) focusIfDropped(statusRef.current);" in effect
    assert ".focus()" not in _STATUS


def test_autosave_cards_report_failure_retry_and_guard_leaving():
    for rel in _AUTOSAVE_CARDS:
        src = _read(rel)
        assert "<AutosaveStatus pending={pending} failed={failed} onRetry={retry} />" in src, rel
        assert "useLeaveGuard(failed)" in src, rel


def test_server_value_cards_report_failure_without_retry():
    # The control shows the server value, so re-picking is the retry and
    # nothing unsaved is on screen: no Try again, no leave guard.
    for rel in _SERVER_VALUE_CARDS:
        src = _read(rel)
        assert "<AutosaveStatus pending={save.isPending} failed={save.isError} />" in src, rel
        assert "useLeaveGuard(" not in src, rel


def test_mcp_switch_stays_focusable_while_saving():
    src = _read("components/settings/mcp-workflow-section.tsx")
    assert "disabled={save.isPending}" not in src
    assert "if (!save.isPending)" in src
