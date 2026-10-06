"""Pins: the Agent inbox's dashboard (docs/plans/2026-10-05-agent-dashboard-design.md).

Read-only: the strip and the Recent runs panel only read. The last visit lives in this browser
and blocked storage still renders the page. Source pins cover the UI contracts; Node executes
the visit hook's mount effect against invalid values and throwing storage without a browser.
"""

import re
from pathlib import Path

from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_PAGE = _read("app/proposals/page.tsx")
_DASH = _read("components/proposals/inbox-dashboard.tsx")
_STRIP = _read("components/proposals/arrivals-strip.tsx")
_RUNS = _read("components/proposals/recent-runs.tsx")
_VISIT = _read("hooks/use-inbox-visit.ts")
_VISIT_LIB = _read("lib/inbox-visit.ts")
_SECTION = _read("components/proposals/proposals-section.tsx")


def test_the_page_renders_the_dashboard_in_order():
    assert "<InboxDashboard />" in _PAGE
    assert _DASH.index("<ArrivalsStrip") < _DASH.index("<RecentRuns") < _DASH.index("<ProposalsSection")
    assert "<ProposalsSection since={since} />" in _DASH


def test_the_strip_reads_the_summary_and_names_its_tiles():
    assert "/api/proposals/summary" in _STRIP
    assert '["proposals", "summary", since]' in _STRIP  # refetches with every inbox action
    for words in ("New since your last visit", "Ready to apply", "Needs you", "Applied this week"):
        assert words in _STRIP
    assert "scrollIntoView" in _STRIP
    assert "enabled: since != null" in _STRIP
    assert "disabled={!count}" in _STRIP
    assert "focus({ preventScroll: true })" in _STRIP


def test_recent_runs_reads_latest_and_fails_quietly():
    assert "/api/agent-runs/latest" in _RUNS
    assert "AGENT_RUNS_LATEST_KEY" in _RUNS
    assert "No runs yet. Set one up on Automations." in _RUNS
    assert "Couldn't load recent runs." in _RUNS
    assert "LoadErrorState" not in _RUNS
    assert "countsLine(" in _RUNS and "<RunOutcome" in _RUNS and "agentDisplayName(" in _RUNS


def test_recent_run_links_keep_the_leave_guard_and_inbox_sequence():
    assert 'from "@/components/guarded-link"' in _RUNS
    assert "?from=proposals" in _RUNS


def test_the_last_visit_survives_blocked_storage_and_reads_once():
    assert _VISIT.count("try {") >= 1  # storage access can itself be blocked
    assert _VISIT_LIB.count("catch {") >= 2  # read and write failures stay independent
    assert "useRef(false)" in _VISIT  # dev double-effect never reads its own write
    assert "24 * 60 * 60 * 1000" in _VISIT_LIB
    clock_pin = r"^const VISIT_CLOCK = createVisitClock\(\);$"
    assert re.search(clock_pin, _VISIT, re.M)
    indented_clock = _VISIT.replace("const VISIT_CLOCK = createVisitClock();", "  const VISIT_CLOCK = createVisitClock();")
    assert not re.search(clock_pin, indented_clock, re.M)
    assert "VISIT_CLOCK.resolve(storage, Date.now())" in _VISIT


def test_history_jump_opens_history_synchronously():
    assert "const history = useState(false);" in _DASH
    assert "<InboxHistoryContext.Provider value={history}>" in _DASH
    assert 'if (anchor === "inbox-history")' in _DASH
    assert "flushSync(() => history[1](true))" in _DASH
    assert "onJump={openHistory}" in _DASH


def test_history_jump_opens_before_the_strip_scrolls():
    assert _STRIP.index("onJump?.(anchor)") < _STRIP.index("scrollIntoView")
    assert "jumpTo(tile.anchor, onJump)" in _STRIP


def test_history_state_is_shared_and_accessibly_named():
    assert "useContext(InboxHistoryContext) ?? localHistory" in _SECTION
    assert "aria-expanded={historyOpen}" in _SECTION


def test_lane_targets_clear_the_sticky_toolbar():
    lane = _SECTION[_SECTION.index('<section ref={ref} tabIndex={-1} aria-labelledby={headingId}') :]
    history = _SECTION[_SECTION.index('<section tabIndex={-1} aria-labelledby={historyId}') :]
    assert "tall:scroll-mt-28" in lane.split('className="', 1)[1].split('"', 1)[0]
    assert "tall:scroll-mt-28" in history.split('className="', 1)[1].split('"', 1)[0]


def test_tiles_show_disabled_state_and_use_the_button_focus_ring():
    for cls in ("disabled:opacity-50", "disabled:[&_p]:text-muted-foreground",
                "outline-none", "border", "border-transparent", "focus-visible:border-ring",
                "focus-visible:ring-3", "focus-visible:ring-ring/50"):
        assert cls in _STRIP


def test_dashboard_tiles_use_the_shared_pattern_and_long_run_text_wraps():
    assert "<StatTile" in _STRIP
    assert "grid-cols-4" in _STRIP and "min-w-0" in _STRIP
    assert "min-w-0" in _DASH
    assert "whitespace-pre-wrap" in _RUNS
    assert "wrap-anywhere" in _RUNS
    for clipped in ("truncate", "line-clamp", "whitespace-nowrap"):
        assert clipped not in _RUNS


def test_visit_clock_uses_node_type_stripping_without_npm_packages():
    result = run_node_test("lib/inbox-visit.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_inbox_readiness_node():
    result = run_node_test("lib/inbox-readiness.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr
