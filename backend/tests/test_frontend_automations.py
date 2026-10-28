"""Pins: the Automations page (docs/plans/2026-10-04-automations-page-design.md, rebuilt by the design
refresh, Task 4.4: status from reports only).

Copy-only: the page puts a prompt on the clipboard for any connected agent app
and schedules nothing. Nothing about the user goes into the copied text, Copy is
always on, and a failed clipboard write opens the prompt so it can be selected.
What a card says about runs comes only from the run log (`GET /api/agent-runs`,
written by MCP `record_run`): never a schedule, a connection state or a way to
start a run (owner rule D5). The branches that matter are pinned here from the
source; components/automations/automations-page.test.mjs renders the page.
"""

from __future__ import annotations

from pathlib import Path

from tests.node_ts import run_node_render_test, run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_SIDEBAR = _read("components/app-sidebar.tsx")
_PAGE = _read("app/automations/page.tsx")
_CARD = _read("components/automations/automation-card.tsx")
_RUNS = _read("components/automations/recent-runs.tsx")
_LIB = _read("lib/automations.ts")
_LIB_RUNS = _read("lib/agent-runs.ts")


def test_the_sidebar_lists_automations_between_agent_inbox_and_referrals():
    inbox = _SIDEBAR.index('{ href: "/proposals", label: "Agent inbox"')
    automations = _SIDEBAR.index('{ href: "/automations", label: "Automations"')
    referrals = _SIDEBAR.index('{ href: "/referrals"')
    assert inbox < automations < referrals


def test_the_page_reads_the_catalog_and_points_at_the_connect_guide():
    assert 'apiFetch<AutomationCatalog>("/api/automations")' in _PAGE
    assert 'title="Automations"' in _PAGE
    # No subtitle (D1): a three-step strip says how it works, and who owns the schedule.
    assert "subtitle=" not in _PAGE
    assert 'aria-label="How automations work"' in _PAGE
    for step in ("Copy a prompt", "Your agent schedules it", "Each run reports here"):
        assert step in _PAGE, step
    assert "CONNECT_AGENT_GUIDE_URL" in _PAGE
    assert "Connect your agent to Maestro first." in _PAGE
    assert "Agent apps that run only in a browser can't reach it yet." in _PAGE


def test_automations_show_no_schedule_or_connection_state_they_cannot_know():
    page = _PAGE + _CARD
    for invented in ("connected", "Runs weekdays", "Open in Claude", "logo"):
        assert invented not in page
    assert "<DayStrip" in page and "Copy prompt" in page


def test_one_tonal_copy_prompt_per_card_and_no_app_names():
    # One Copy prompt per card (D5); the board has no Show prompt, and the page's cards are not its one
    # filled button: Copy prompt is tonal.
    assert _CARD.count('"Copy prompt"') == 1 and "Show prompt" not in _CARD
    assert 'variant="tonal"' in _CARD and 'variant="default"' not in _CARD
    for app in ("Claude", "ChatGPT", "Codex", "Cursor", "Gemini"):
        assert app not in _CARD and app not in _PAGE, app


def test_one_prompt_for_every_agent_app():
    assert not (_FRONTEND / "components/automations/app-picker.tsx").exists()
    for src in (_PAGE, _CARD, _LIB):
        for word in ("AppPicker", "reachable", "AgentApp", "APP_STORE_KEY", "promptFor"):
            assert word not in src, word
    # Copy is always on; a disabled Copy would also lose keyboard focus.
    assert "disabled" not in _CARD


def test_a_failed_clipboard_write_opens_the_prompt_to_select():
    # useCopy owns the clipboard call (and the missing-API throw); the card handles the `false` branch.
    assert "useCopy" in _CARD and "navigator.clipboard" not in _CARD
    # The `false` branch (the hook already toasted via onError) opens the prompt.
    failed = _CARD[_CARD.index("if (ok)") :]
    failed = failed[: failed.index("\n  }\n")]
    assert "setOpen(true)" in failed and "else" in failed
    assert "select-all" in _CARD


def test_the_card_copy():
    assert "Prompt copied. Paste it into your agent app." in _CARD
    assert "Scheduled applying comes with full automation mode." in _CARD
    assert 'card.id === APPLY_CARD_ID && card.kind === "attended"' in _CARD


def test_reports_come_from_the_run_log_and_fail_quietly():
    # The 14-day strips need every retained run: the log keeps 200 (services/agent_runs.py), and the
    # list endpoint's limit tops out there (routers/agent_runs.py).
    assert "AGENT_RUNS_PATH" in _PAGE and 'AGENT_RUNS_PATH = "/api/agent-runs?limit=200"' in _LIB_RUNS
    assert "apiFetch<AgentRunList>(AGENT_RUNS_PATH)" in _PAGE
    # A failed background refetch keeps the cached runs; a read that never produced data fails quietly:
    # every card is a compact row with its Copy prompt, nothing claims "No reports yet", one line says why.
    assert "const byAutomation = runs.data ? runsByAutomation(runs.data.items) : null;" in _PAGE
    assert "Couldn't load reports." in _PAGE
    assert 'title="Couldn\'t load runs.' not in _PAGE
    assert _PAGE.count("<LoadErrorState") == 1  # the catalog's, not the runs'


def test_a_card_reports_while_a_run_sits_in_its_strip():
    # Reporting: a run in the strip's 14 days (lib/day-strip.ts reportedInStrip); the rest are compact rows.
    assert "reportedInStrip(byAutomation.get(card.id) ?? [], today)" in _PAGE
    assert "<AutomationCard" in _PAGE and "<AutomationRow" in _PAGE
    assert "Reporting <span" in _PAGE and '"No reports yet"' in _PAGE
    # A row whose last run is older than the strip says so: the heading never claims it never ran.
    assert '"No reports in 14 days"' in _PAGE and "Last report " in _CARD


def test_a_reporting_card_shows_its_days_and_its_newest_report():
    assert "<DayStrip runs={runs} />" in _CARD
    assert "reportLine(newest, agentDisplayName(newest.agent), formatTimeAgo)" in _CARD
    assert "<RunOutcome outcome={newest.outcome} />" in _CARD


def test_one_link_to_the_result():
    # Proposed jobs are in the Agent inbox; the run does not say how many are still open there, so the
    # link names the place and the count stays in the report line.
    assert "newest.counts.proposed ?? 0) > 0" in _CARD
    assert '<NextStep label="See in Agent inbox" href="/proposals" />' in _CARD
    # Otherwise the run's digest and job links open in place (the Recent runs line's own body).
    assert "Last report" in _CARD and "aria-expanded={reportOpen}" in _CARD
    assert "<RunReport run={newest}" in _CARD and "export function RunReport" in _RUNS


def test_recent_runs_and_what_each_one_never_does_are_folded():
    assert 'title="Recent runs"' in _PAGE and 'title="What each one never does"' in _PAGE
    assert _PAGE.index('title="Recent runs"') < _PAGE.index('title="What each one never does"')
    # The inbox's "See runs" link (#recent-runs) opens the fold it lands on.
    assert 'anchor === "#recent-runs"' in _PAGE and "useSyncExternalStore" in _PAGE
    assert "recentRunsSummary(" in _PAGE
    # Recent runs takes its title from the fold.
    assert "<h2" not in _RUNS


def test_the_catalog_stays_db_free():
    # The Last ran line comes from its own read; GET /api/automations reads no table.
    assert "agent-runs" not in _LIB


def test_the_card_copies_the_prompt_the_backend_built():
    assert "const text = card.prompt;" in _CARD


def test_no_cadence_picker_and_nothing_about_the_user_in_the_prompt():
    for src in (_PAGE, _CARD, _LIB):
        for word in ("cadence", "schedule_time", "cron("):
            assert word not in src, word
    assert "profile" not in _LIB


def test_small_surfaces_gain_their_glyphs():
    card = _CARD
    # No Scheduled / Attended badge: the schedule lives in the agent app (D5). A need's badge keeps its glyph.
    assert "KIND_LABEL" not in card and "CONCEPT_ICONS.scheduled" not in card
    assert "<CONCEPT_ICONS.cannot " in _read("components/settings/connected-agents-card.tsx")
    assert "CONCEPT_ICONS.cannot" in _CARD and "Globe2" in _CARD and "<Ban " not in _CARD
    assert "MessageSquareText" in _read("components/qa-tab.tsx")
    # The outcome glyph is Task 21's component, not a copy; lib/agent-runs.ts stays import-free.
    assert 'from "@/components/proposals/run-outcome"' in card
    assert "import " not in _LIB_RUNS


def test_the_connect_note_is_a_callout_until_a_run_reports():
    assert "bg-secondary-container text-on-secondary-container rounded-corner-md" in _PAGE
    # Any report proves an agent reached Maestro; after one the note goes.
    assert "const anyRan = !!runs.data && runs.data.items.length > 0;" in _PAGE
    # A failed runs query still shows the callout; nothing shows only while runs or the catalog are loading.
    assert "const noteReady = runs.isError || (!!runs.data && !!data);" in _PAGE
    assert "{noteReady && !anyRan ? (" in _PAGE


def test_email_and_cover_letter_have_one_glyph_each():
    assert "CONCEPT_ICONS.email" in _CARD and "AtSign" not in _CARD
    assert "CONCEPT_ICONS.coverLetter" in _read("components/qa-tab.tsx")
    assert "CONCEPT_ICONS.email" in _read("components/career/profile-panel.tsx")


def test_day_strip_node_suite():
    """The 14-day strip buckets runs by the local calendar day, worst outcome first (design refresh, Task 0.7)."""
    result = run_node_test("lib/day-strip.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_day_strip_is_round_status_dots_with_a_sentence_and_a_legend():
    src = _read("components/visual/day-strip.tsx")
    assert 'role="img"' in src and "aria-label={dayStripLabel(cells)}" in src
    assert "rounded-full" in src and "rounded-corner" not in src  # round means status
    for role in ("bg-success", "bg-warning", "bg-destructive", "bg-surface-container-high"):
        assert role in src, role
    assert "outcomeWord(" in src and "No report" in src  # the legend says each colour in words
    assert "<span>{`${days - 1} days ago`}</span>" in src  # the left end is the oldest dot's day
    assert 'export { DayStrip } from "./day-strip";' in _read("components/visual/index.ts")


def test_automations_page_node_suite():
    """The page rendered with seeded runs: Reporting cards, compact rows, the folds (Task 4.4)."""
    result = run_node_render_test("components/automations/automations-page.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr
