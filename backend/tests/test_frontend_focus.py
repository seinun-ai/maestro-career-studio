"""Pins for the focus-return and single-flight helpers (UX next, Task 8).

Node tests cover `isLoadFailure`'s behaviour; they are not in CI, so the
predicate and the hook shapes are pinned here as source text.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


_HOOK = _read("hooks/use-focus-return.ts")


def test_focus_helpers_move_only_a_dropped_focus():
    body = _HOOK[_HOOK.index("export function focusIfDropped(") :]
    assert "active !== document.body" in body[: body.index("\n}\n")]


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
    body = _HOOK[_HOOK.index("export function focusReturnPoint(") :]
    assert "closest<HTMLElement>('[tabindex=\"-1\"]')" in body
    # An opted-in tabIndex={-1} ancestor wins over the main area.
    assert "chain.push(a);" in body
    assert "(chain.find((a) => a.isConnected) ?? document.getElementById(MAIN_CONTENT_ID))" in body
    assert '"main-content"' in _HOOK
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
    body = hook[hook.index("return (vars) =>") :]
    assert (
        body.index("if (inFlight.current) return;")
        < body.index("inFlight.current = true;")
        < body.index("mutate(vars")
    )
    assert "onSettled: () => { inFlight.current = false; }" in re.sub(r"\s+", " ", body)


def test_the_qa_history_is_a_named_focus_target():
    qa = _read("components/qa-tab.tsx")
    assert re.search(
        r"<section tabIndex=\{-1\} aria-labelledby=\{historyHeadingId\}[^>]*>\s*"
        r"<h3 id=\{historyHeadingId\}",
        qa,
    )
