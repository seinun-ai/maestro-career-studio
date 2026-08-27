"""Guard: a failed fetch must never render as "you have nothing".

react-query leaves `data` undefined after an error, so the common gate
`if (isLoading || !data) return <Skeleton/>` holds forever once the request
fails, and a list built from `data ?? []` falls straight into its empty state.
The Applications tracker showed the NEW-USER onboarding card — "No applications
yet. Capture a job description to get started." — to a user whose pipeline had
simply failed to load.

There is no JS test runner in this repo (the extension's tests parse source the
same way, `test_formatting_parity.py` is the cross-boundary precedent), so this
pins the structural property CI can actually check: every surface listed here
has an error branch, and that branch comes BEFORE the empty-state marker it
would otherwise be mistaken for.

A substring `assert "isError" in source` is not enough: a comment, an unrelated
query, or an error check sitting *after* the empty return all pass it, and it
false-fails every correct file that spells the check `.error`. The table below
is the pin that actually encodes the contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Conditional error-branch spellings this repo actually uses. A destructured
# `isError` that is never branched on must not count — that was the vacuous
# pin this file used to be. `onError` is a mutation handler and must not count.
_ERROR_BRANCH = re.compile(
    r"if \([^)]*\bisError\b"
    r"|\.isError \?"
    r"|\.isError \|"
    r"|\.isError &&"
    r"|[^.\w]isError \?"
    r"|loadFailed"
    r"|if \([^)]*\.error\b"
    r"|(?<!on)\.error \?(?!\?)"
    r"|error \?(?!\?)"
    r"|if \(error\)"
    r"|!error\b"
)

# (relpath, empty-state marker that must NOT be reachable on a failed fetch).
# Marker is the first unique string of the confirmed-empty / onboarding copy,
# or of the skeleton-forever gate that hid the failure.
_QUERY_SURFACES: list[tuple[str, str]] = [
    # Original guard set — already correct; ride along so a regression is a fail.
    ("app/applications/page.tsx", "<GettingStartedCard"),
    ("app/jobs/[id]/page.tsx", "isLoading || !data"),
    # The settings cards no longer own this branch — `SettingCard` does, and
    # `test_settings_cards_route_through_the_shared_shell` below pins that none
    # of them may go back to hand-rolling one.
    ("components/settings/setting-card.tsx", "<Skeleton"),
    ("components/proposals/proposal-agent-panel.tsx", "isLoading || !data"),
    ("app/base-resumes/[slug]/page.tsx", "query.isLoading || !query.data"),
    ("app/applications/[id]/resume/page.tsx", "query.isLoading || !query.data"),
    ("app/templates/[id]/page.tsx", "tq.isLoading || !tq.data"),
    # Already-correct surfaces that spell the check `.error`.
    ("components/analytics/analytics-overview.tsx", "Submitted · last 7 days"),
    ("components/career/profile-panel.tsx", "No skill groups yet."),
    ("components/proposals/funnel-strip.tsx", "if (!data) return null"),
    ("components/career/entity-detail.tsx", "The item may no longer exist."),
    ("app/career/page.tsx", "No custom sections yet"),
    ("components/career/inbox-panel.tsx", "Inbox clear"),
    ("components/analytics/agent-pipeline-card.tsx", "return null"),
    # Verified violations this round — each used to reach the marker on error.
    ("components/qa-tab.tsx", "No Q&amp;A entries yet."),
    ("components/proposals/proposals-section.tsx", "No agent proposals yet"),
    ("app/base-resumes/page.tsx", "No career-track resumes yet."),
    ("app/templates/page.tsx", "No templates yet."),
    ("components/chat/chat-page.tsx", "What are we working on?"),
    ("components/career/first-run-import-card.tsx", "Start with the resumes you already have"),
    ("components/ats-score-panel.tsx", "No ATS scores yet."),
    ("components/resume-health/health-badges.tsx", 'title="Check this resume\'s health"'),
    ("components/resume-health/health-report-page.tsx", "No health report yet."),
    ("components/setup/getting-started-card.tsx", "Getting started"),
    ("app/applications/[id]/page.tsx", "This application no longer exists."),
    ("app/profile/page.tsx", "<SetupStatusStrip"),
]


def _error_branch_index(source: str) -> int:
    match = _ERROR_BRANCH.search(source)
    if match is None:
        raise AssertionError(
            "renders a query result with no error branch: after a failed "
            "fetch it shows a loading skeleton or an empty state forever."
        )
    return match.start()


@pytest.mark.parametrize("relpath,empty_marker", _QUERY_SURFACES, ids=[p for p, _ in _QUERY_SURFACES])
def test_query_surface_error_branch_precedes_empty_state(relpath: str, empty_marker: str):
    source = (_FRONTEND / relpath).read_text()
    try:
        empty_at = source.index(empty_marker)
    except ValueError as exc:
        raise AssertionError(
            f"{relpath} no longer contains empty-state marker {empty_marker!r}; "
            "update the table if the copy moved, do not drop the pin."
        ) from exc
    try:
        error_at = _error_branch_index(source)
    except AssertionError as exc:
        raise AssertionError(f"{relpath} {exc}") from exc
    assert error_at < empty_at, (
        f"{relpath}: error branch at {error_at} must precede empty-state marker "
        f"{empty_marker!r} at {empty_at}. An isError check after the empty "
        "return is not a fix — the failed fetch still reads as 'you have nothing'."
    )


# Every settings card that reads the API. `appearance-section` is absent on
# purpose: it fetches nothing, so it has no failure to render.
_SETTINGS_CARDS = [
    "about-section.tsx",
    "auto-apply-section.tsx",
    "autofill-section.tsx",
    "job-preferences-section.tsx",
    "market-section.tsx",
    "mcp-workflow-section.tsx",
    "models-section.tsx",
    "persona-section.tsx",
    "prompts-section.tsx",
    "quick-tailor-section.tsx",
]


@pytest.mark.parametrize("filename", _SETTINGS_CARDS)
def test_settings_cards_route_through_the_shared_shell(filename: str):
    """No settings card may hand-roll its own load/error scaffold again.

    Pinning the shell alone is not enough: a new card that writes its own
    `Card → isLoading → editor` never appears in the table above, so it would
    ship the exact failure this module exists to catch — and four of them did,
    which is why `SettingCard` was extracted. This is the pin that makes the
    shell mandatory rather than merely available.
    """
    source = (_FRONTEND / "components/settings" / filename).read_text()
    assert "<SettingCard" in source, (
        f"{filename} does not render through SettingCard. Every card that reads "
        "the API must, so its failure state is the shell's, not its own."
    )
    assert "<CardHeader" not in source, (
        f"{filename} builds its own CardHeader — that is the shell's job, and "
        "hand-rolling it is how the loading and error branches drifted apart."
    )


def test_application_detail_distinguishes_missing_from_retryable():
    """A 500 / timeout is not a deletion. 404 keeps the existing copy; anything
    else must offer retry via LoadErrorState."""
    source = (_FRONTEND / "app/applications/[id]/page.tsx").read_text()
    assert "This application no longer exists." in source
    assert "LoadErrorState" in source
    assert "status === 404" in source
    assert source.index("if (isError)") < source.index(
        'title="Couldn\'t load this application."'
    )
    assert source.index("if (isError)") < source.index(
        "This application no longer exists."
    )


def test_new_application_clears_cached_job_when_source_url_changes():
    """Editing only the URL after an extraction used to re-ingest the stale job.

    `onRawTextChange` already cleared `savedJob`; the Source URL input must too.
    Two `setSavedJob(null)` call sites is the pin: one per field that feeds
    ingestJob.
    """
    source = (_FRONTEND / "app/new/page.tsx").read_text()
    assert source.count("setSavedJob(null)") >= 2, (
        "source_url onChange must clear the cached extraction, same as raw text; "
        "otherwise a URL-only edit silently reuses the previous job."
    )
