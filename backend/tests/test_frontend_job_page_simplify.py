"""Pins: the simpler job page and Agent inbox (docs/plans/2026-10-14-job-page-and-inbox-simplify.md).

The first thing on each page answers "what do I need to do, and where does this stand?". There is no
component test runner, so the pure rules are node-tested (lib/*.test.ts) and the wiring is pinned
from the source here.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_JOB = _read("app/jobs/[id]/page.tsx")


# ── A1: one status in the header ────────────────────────────────────────────


def test_the_header_shows_one_status_and_the_proposal_pill_reads_like_history():
    assert "headerProposalPill({" in _JOB and "hasApplication: hasApp" in _JOB
    assert "STATUS_LABELS[proposalStatus]" in _JOB  # the fallback label only
    assert "STATUS_BADGE_CLASS[pill.styleStatus]" in _JOB
    # The pill's reason comes from the proposal itself (the same query the Overview card shares).
    assert 'queryKey: ["proposal", proposalId]' in _JOB


# ── A2: a clear score ───────────────────────────────────────────────────────


def test_the_score_pill_says_what_it_scores():
    assert "const scoreShown = scorePill(scoreRows.data ?? [], application?.id ?? null);" in _JOB
    pill = _JOB[_JOB.index("{scoreShown ? (") :]
    pill = pill[: pill.index("{hasApp && application ? (")]
    assert "{scoreShown.label}" in pill and "(tailored)" in pill
    assert "Best</span>" not in pill
    # The tailored score belongs to the application, so its resume's name is the application's base.
    assert "application?.base_resume" in _JOB


# ── A3: where this stands ───────────────────────────────────────────────────


def test_the_page_says_where_the_job_stands_under_the_header():
    assert "const standing = standingLine({" in _JOB
    header_end = _JOB.index("</header>")
    line = _JOB[header_end : _JOB.index("<JobOwnershipNotice")]
    assert 'data-testid="job-standing"' in line and "{standing.text}" in line
    # View PDF only with a PDF; What was submitted only with filled answers; the pointer only on a draft.
    assert "standing.pdf && application" in line and "View PDF" in line
    assert "standing.submitted" in line and 'setTab("submitted")' in line
    assert 'standing.kind === "draft"' in line and "Tailor and Apply in the Companion" in line
    assert 'setTab("fit")' in line
    # Built from data the detail response already carries: no new request.
    assert "hasFilledAnswers: Boolean(data.has_filled_answers)" in _JOB
    # The detail names the application's resume (backend test_jobs_router.py); an older backend's gap
    # falls back to the label hook.
    assert "data.base_resume_name ?? baseName(application.base_resume)" in _JOB


# ── A4: knock-outs only when they block ─────────────────────────────────────

_KNOCKOUT = _read("components/job-knockout-card.tsx")


def test_the_knockout_banner_shows_only_when_it_blocks():
    banner = _KNOCKOUT[_KNOCKOUT.index("export function JobKnockoutCard(") : _KNOCKOUT.index("export function KnockoutLine(")]
    assert "!knockoutBanner(scan.status)" in banner and "return null;" in banner
    # The quiet outcomes are gone from the banner: they are the line's.
    for words in ("No knock-outs", "No requirements listed", "Checks not run yet"):
        assert words not in banner


def test_a_scan_that_blocks_nothing_is_one_line_in_the_job_details_card():
    assert "statusSlot={<KnockoutLine scan={data?.knockout} job={job} />}" in _JOB
    fields = _read("components/job-extracted-fields.tsx")
    assert "{statusSlot}" in fields and fields.index("{statusSlot}") < fields.index("<dl ")
    line = _KNOCKOUT[_KNOCKOUT.index("export function KnockoutLine(") :]
    assert "knockoutLine(scan.status, notChecked)" in line and "{shown.label}" in line
    # The chips ride under the line only when there is a warning or a check that could not run.
    assert "warned || unchecked.length > 0 || rows.length > 0" in line


# ── A5: the proposal card only when it carries something ────────────────────

_PANEL = _read("components/proposals/proposal-agent-panel.tsx")


def test_the_proposal_card_mounts_only_when_it_carries_something():
    tab = _JOB[_JOB.index('<TabsContent value="jd"') :]
    tab = tab[: tab.index("<JobKnockoutCard")]
    assert "proposalHasContent(proposalQuery.data)" in tab and "<ProposalAgentPanel proposalId={proposalId} />" in tab
    # A proposal that failed to load still shows its error card; one still loading shows nothing.
    assert "proposalQuery.isError ||" in tab
    assert "{proposalId ? <ProposalAgentPanel" not in _JOB


def test_expires_shows_only_while_the_proposal_can_still_expire():
    assert "data.expires_at && proposalCanExpire(data.status)" in _PANEL


# ── B1: one summary line instead of four tiles ──────────────────────────────

_STRIP = _read("components/proposals/arrivals-strip.tsx")
_SUMMARY_LIB = _read("lib/inbox-summary.ts")


def test_the_inbox_opens_with_one_summary_line_whose_parts_jump_to_their_lanes():
    for part in ('"inbox-needs-you"', '"inbox-queued"', '"inbox-history"', '"inbox-to-review"'):
        assert part in _SUMMARY_LIB
    assert '"needs" : "need"' in _SUMMARY_LIB and "applied this week" in _SUMMARY_LIB and "queued" in _SUMMARY_LIB
    assert "<button" in _STRIP and "StatTile" not in _STRIP


# ── B2: lanes in order of urgency, empty lanes hidden ───────────────────────

_SECTION = _read("components/proposals/proposals-section.tsx")


def test_the_lanes_run_needs_you_to_review_queued_applying_history_and_an_empty_one_is_not_drawn():
    marks = [
        _SECTION.index('anchor="inbox-needs-you"'),
        _SECTION.index('anchor="inbox-to-review"'),
        _SECTION.index('anchor="inbox-queued"'),
        _SECTION.index("title={`Applying · "),
        _SECTION.index('id="inbox-history"'),
    ]
    assert marks == sorted(marks)
    for guard in (
        "{needsYou.length > 0 ? (",
        "{triage.length > 0 ? (",
        "{queued.length > 0 ? (",
        "{inFlight.length > 0 ? (",
        "{historyAll.length > 0 ? (",
    ):
        assert guard in _SECTION, guard
    # History is still the collapsed one; the no-proposals empty state stays.
    assert "No history yet." not in _SECTION and 'title="No proposals yet"' in _SECTION
    # "new" jumps to the first lane there is when To review is not drawn.
    assert "section[id^=" in _STRIP


# ── B3: filters only for long lists ─────────────────────────────────────────


def test_search_and_filters_render_only_for_a_long_inbox_or_while_one_is_in_use():
    assert "{filtersShown(items.length, { q, role, board, minScore, sort }) ? (" in _SECTION
    toolbar = _SECTION[_SECTION.index("{filtersShown(") : _SECTION.index("{nothingMatches ? (")]
    assert "<ListToolbar>" in toolbar and 'label="Search the Agent inbox"' in toolbar
    assert toolbar.rstrip().endswith(") : null}")
    assert "total > FILTERS_FROM" in _read("lib/inbox-filter.ts") and "FILTERS_FROM = 10" in _read("lib/inbox-filter.ts")


# ── B4: daily limit only near it ────────────────────────────────────────────


def test_the_inbox_says_the_daily_limit_only_near_it_and_analytics_always_does():
    cap = _read("components/proposals/cap-today.tsx")
    assert "onlyNearLimit && !capNearLimit(cap.reserved_last_24h, cap.max_per_day)" in cap
    # A failed load is still shown before the readout, so the error never hides.
    assert cap.index("if (isLoadFailure(query))") < cap.index("onlyNearLimit &&")
    assert "<CapToday onlyNearLimit />" in _read("app/proposals/page.tsx")
    assert "<CapToday " in _read("components/analytics/agent-pipeline-card.tsx")
    assert "onlyNearLimit" not in _read("components/analytics/agent-pipeline-card.tsx")


def test_the_limit_threshold_node():
    from tests.node_ts import run_node_test

    result = run_node_test("lib/inbox-summary.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


# ── B5: Recent runs move to Automations ─────────────────────────────────────


def test_recent_runs_live_on_automations_and_the_inbox_keeps_one_line():
    automations = _read("app/automations/page.tsx")
    assert 'import { RecentRuns } from "@/components/automations/recent-runs";' in automations
    assert "<RecentRuns />" in automations
    dash = _read("components/proposals/inbox-dashboard.tsx")
    assert "<InboxRunNotice />" in dash and "RecentRuns" not in dash
    assert not (_FRONTEND / "components/proposals/recent-runs.tsx").exists()
    runs = _read("components/automations/recent-runs.tsx")
    assert "<details" in runs and "run.digest" in runs and "run.jobs.map" in runs  # expand-to-digest, job links


def test_the_inbox_line_names_the_run_and_links_to_see_runs():
    notice = _read("components/proposals/inbox-run-notice.tsx")
    assert "newJobsLine(data.items, formatTimeAgo)" in notice
    assert 'href="/automations"' in notice and "See runs" in notice
    # Nothing new, nothing shown.
    assert "if (!line && refused.length === 0) return null;" in notice
    # A refused request answers something you asked for, so it stays where you would look for it.
    assert "RefusedLine" in notice and "refused_requests" in notice


def test_the_run_line_node():
    from tests.node_ts import run_node_test

    result = run_node_test("lib/agent-runs.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_real_components_render_without_a_browser():
    """Renders the summary line, run line, daily limit, knock-out line and proposal card for real.

    Like backend/tests/sync/test_frontend_ownership.py: it needs the web app's installed packages, so
    the frontend CI job runs it (`node --test components/inbox-simplify.test.mjs`) and the backend job
    skips its copy.
    """
    import pytest

    from tests.node_ts import FRONTEND, _node_with_typescript, run_node_test

    if not (FRONTEND / "node_modules" / "typescript").is_dir():
        _node_with_typescript()
        pytest.skip("frontend packages are not installed; the frontend CI job runs this file")
    done = run_node_test("components/inbox-simplify.test.mjs")
    assert done.returncode == 0, done.stdout + done.stderr
