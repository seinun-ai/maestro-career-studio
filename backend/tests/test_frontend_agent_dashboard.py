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
const ts = require("typescript");
const config = JSON.parse(process.argv[1]);
const now = Date.parse("2026-10-05T12:00:00.000Z");
const result = { since: null, reads: 0, writes: 0, saved: null };
const effects = [];
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
    return config.stored;
  },
  setItem(key, value) {
    if (key !== "cs-inbox-last-visit") throw new Error("wrong key");
    result.writes++;
    if (config.writeThrows) throw new Error("blocked write");
    result.saved = value;
  },
};
const compiled = ts.transpileModule(fs.readFileSync("hooks/use-inbox-visit.ts", "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const moduleUnderTest = { exports: {} };
vm.runInNewContext(compiled, {
  module: moduleUnderTest, exports: moduleUnderTest.exports,
  require: name => { if (name === "react") return react; throw new Error(name); },
  window: { localStorage: storage }, Date: FixedDate,
});
result.initial = moduleUnderTest.exports.useInboxVisit();
effects.forEach(effect => { effect(); effect(); });
process.stdout.write(JSON.stringify(result));
"""


@pytest.mark.parametrize(
    "stored,read_throws,write_throws,expected",
    [
        ("2026-10-03T09:30:00.000Z", False, False, "2026-10-03T09:30:00.000Z"),
        (None, False, False, "2026-10-04T12:00:00.000Z"),
        ("not a date", False, False, "2026-10-04T12:00:00.000Z"),
        ("2026-10-03T09:30:00.000Z", True, True, "2026-10-04T12:00:00.000Z"),
        ("2026-10-03T09:30:00.000Z", False, True, "2026-10-03T09:30:00.000Z"),
    ],
)
def test_visit_effect_keeps_the_old_time_and_survives_storage_errors(
    stored, read_throws, write_throws, expected,
):
    config = {"stored": stored, "readThrows": read_throws, "writeThrows": write_throws}
    done = subprocess.run(
        ["node", "-e", _VISIT_SCRIPT, json.dumps(config)],
        cwd=_FRONTEND, capture_output=True, text=True, check=True,
    )
    result = json.loads(done.stdout)
    assert result["initial"] is None
    assert result["since"] == expected
    assert result["reads"] == result["writes"] == 1
    assert result["saved"] == (None if write_throws else "2026-10-05T12:00:00.000Z")
