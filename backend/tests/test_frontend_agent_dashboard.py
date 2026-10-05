"""Pins: the Agent inbox's dashboard (docs/plans/2026-10-05-agent-dashboard-design.md).

Read-only: the strip and the Recent runs panel only read. The last visit lives in this browser
and blocked storage still renders the page. Source pins cover the UI contracts; Node executes
the visit hook's mount effect against invalid values and throwing storage without a browser.
"""

import json
import subprocess
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_PAGE = _read("app/proposals/page.tsx")
_DASH = _read("components/proposals/inbox-dashboard.tsx")
_STRIP = _read("components/proposals/arrivals-strip.tsx")
_RUNS = _read("components/proposals/recent-runs.tsx")
_VISIT = _read("hooks/use-inbox-visit.ts")
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
    assert "countsLine(" in _RUNS and "outcomeWord(" in _RUNS and "agentDisplayName(" in _RUNS


def test_recent_run_links_keep_the_leave_guard_and_inbox_sequence():
    assert 'from "@/components/guarded-link"' in _RUNS
    assert "?from=proposals" in _RUNS


def test_the_last_visit_survives_blocked_storage_and_reads_once():
    assert _VISIT.count("try {") >= 2  # the read and the write
    assert "useRef(false)" in _VISIT  # dev double-effect never reads its own write
    assert "24 * 60 * 60 * 1000" in _VISIT
    assert "let tabSince: string | null = null;" in _VISIT


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


_VISIT_SCRIPT = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require(require.resolve("typescript", { paths: [process.cwd()] }));
const config = __CONFIG__;
let now = Date.parse("2026-10-05T12:00:00.000Z");
let stored = config.stored;
const result = { since: null, reads: 0, writes: 0, saved: null };
let effects = [];
const react = {
  useState: () => [null, value => { result.since = value; }],
  useRef: value => ({ current: value }),
  useEffect: effect => effects.push(effect),
};
class FixedDate extends Date {
  constructor(value = now) { super(value); }
  static now() { return now; }
}
const storage = {
  getItem(key) {
    if (key !== "cs-inbox-last-visit") throw new Error("wrong key");
    result.reads++;
    if (config.readThrows) throw new Error("blocked read");
    return stored;
  },
  setItem(key, value) {
    if (key !== "cs-inbox-last-visit") throw new Error("wrong key");
    result.writes++;
    if (config.writeThrows) throw new Error("blocked write");
    result.saved = stored = value;
  },
};
const compiled = ts.transpileModule(fs.readFileSync("hooks/use-inbox-visit.ts", "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
function loadModule() {
  const moduleUnderTest = { exports: {} };
  vm.runInNewContext(compiled, {
    module: moduleUnderTest, exports: moduleUnderTest.exports,
    require: name => { if (name === "react") return react; throw new Error(name); },
    window: { localStorage: storage }, Date: FixedDate,
  });
  return moduleUnderTest.exports;
}
function mount(hook) {
  effects = [];
  result.since = null;
  assert.equal(hook.useInboxVisit(), null);
  effects.forEach(effect => { effect(); effect(); });
}
const hook = loadModule();
test("first mount survives storage errors and dev double-effect", () => {
  mount(hook);
  assert.equal(result.since, config.expected);
  assert.equal(result.reads, 1);
  assert.equal(result.writes, 1);
  assert.equal(result.saved, config.writeThrows ? null : new Date(now).toISOString());
});
test("returning from a job reuses this tab's visit without touching storage", () => {
  now += 60 * 60 * 1000;
  mount(hook);
  assert.equal(result.since, config.expected);
  assert.equal(result.reads, 1);
  assert.equal(result.writes, 1);
  assert.equal(result.saved, config.writeThrows ? null : "2026-10-05T12:00:00.000Z");
});
test("a full reload reads and writes storage again", () => {
  now += 60 * 60 * 1000;
  const expected = !config.readThrows && stored && !Number.isNaN(Date.parse(stored))
    ? stored : new Date(now - 24 * 60 * 60 * 1000).toISOString();
  mount(loadModule());
  assert.equal(result.since, expected);
  assert.equal(result.reads, 2);
  assert.equal(result.writes, 2);
  assert.equal(result.saved, config.writeThrows ? null : new Date(now).toISOString());
});
"""


@pytest.mark.parametrize(
    "stored,read_throws,write_throws,expected",
    [
        ("2026-10-03T09:30:00.000Z", False, False, "2026-10-03T09:30:00.000Z"),
        (None, False, False, "2026-10-04T12:00:00.000Z"),
        ("not a date", False, False, "2026-10-04T12:00:00.000Z"),
        ("", False, False, "2026-10-04T12:00:00.000Z"),
        ("   ", False, False, "2026-10-04T12:00:00.000Z"),
        ("2026-10-03T09:30:00.000Z", True, True, "2026-10-04T12:00:00.000Z"),
        ("2026-10-03T09:30:00.000Z", True, False, "2026-10-04T12:00:00.000Z"),
        ("2026-10-03T09:30:00.000Z", False, True, "2026-10-03T09:30:00.000Z"),
    ],
)
def test_visit_effect_keeps_the_old_time_and_survives_storage_errors(
    stored, read_throws, write_throws, expected, tmp_path,
):
    config = {"stored": stored, "readThrows": read_throws, "writeThrows": write_throws,
              "expected": expected}
    script = tmp_path / "inbox-visit.test.cjs"
    script.write_text(_VISIT_SCRIPT.replace("__CONFIG__", json.dumps(config)), encoding="utf-8")
    done = subprocess.run(
        ["node", "--test", "--test-reporter=tap", str(script)],
        cwd=_FRONTEND, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "# pass 3" in done.stdout and "# fail 0" in done.stdout
