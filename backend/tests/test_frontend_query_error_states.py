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
    r"|isLoadFailure\("
    r"|useLoadFailureError\("
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
    ("components/analytics/analytics-overview.tsx", "Applied · last 7 days"),
    ("components/career/profile-panel.tsx", "No skill groups yet."),
    ("components/career/entity-detail.tsx", "if (!entity.data) {"),
    ("app/career/page.tsx", "No other sections yet"),
    ("components/career/inbox-panel.tsx", "Nothing to review"),
    ("components/analytics/agent-pipeline-card.tsx", "return null"),
    # Verified violations this round — each used to reach the marker on error.
    ("components/qa-tab.tsx", "No answers yet."),
    ("components/proposals/proposals-section.tsx", "No proposals yet"),
    ("app/base-resumes/page.tsx", "No base resumes yet. Create one to start."),
    ("app/templates/page.tsx", "No templates yet."),
    ("components/chat/chat-page.tsx", "What are we working on?"),
    ("components/career/first-run-import-card.tsx", "Start with the resumes you already have"),
    ("components/ats-score-panel.tsx", "No ATS scores yet."),
    ("components/resume-health/health-badges.tsx", 'title="Check this resume\'s health"'),
    ("components/resume-health/health-report-page.tsx", "No health report yet."),
    ("components/setup/getting-started-card.tsx", "Getting started"),
    ("app/applications/[id]/page.tsx", "This application no longer exists."),
    ("app/profile/page.tsx", "<SetupStatusStrip"),
    ("app/referrals/page.tsx", "Add your first referral"),
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
    "llm-endpoint.tsx",
    "market-section.tsx",
    "mcp-workflow-section.tsx",
    "model-catalog-panel.tsx",
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
    # Not a substring test: `<SettingCardAction>` (the header slot) also starts with "<SettingCard".
    assert re.search(r"<SettingCard[\s>]", source), (
        f"{filename} does not render through SettingCard. Every card that reads "
        "the API must, so its failure state is the shell's, not its own."
    )
    assert "<CardHeader" not in source, (
        f"{filename} builds its own CardHeader — that is the shell's job, and "
        "hand-rolling it is how the loading and error branches drifted apart."
    )


def test_query_client_never_pauses_requests_for_being_offline():
    """A local API is reachable whether or not the machine has a network.

    react-query's default `networkMode: "online"` parks a query in
    `fetchStatus: "paused"` / `status: "pending"` when it believes the browser
    is offline. `isError` never flips, so every error branch pinned in this
    module becomes unreachable and the surface renders its pending state — a
    skeleton, or a confirmed-empty list — indefinitely.

    That default assumes a remote API. This one is FastAPI on the same machine:
    `navigator.onLine` says nothing about whether it is listening, and a laptop
    with the wifi off can still use every page here. `always` asks the only
    question that matters — did the request succeed.

    Demonstrated: with `navigator.onLine` forced false and an `offline` event
    dispatched, an `online`-mode query against `/api/version` parked at
    pending/paused and never ran, while an `always`-mode one succeeded — the
    local API listening throughout.

    SCOPE, so nobody over-reads this pin: it addresses the OFFLINE pause only.
    react-query separately pauses RETRIES while the window is unfocused, which
    is deliberate upstream behaviour and is not a bug — with a focused window a
    failed fetch surfaces the error state normally.
    """
    source = (_FRONTEND / "app/providers.tsx").read_text()
    assert source.count('networkMode: "always"') >= 2, (
        "app/providers.tsx must set networkMode 'always' for BOTH queries and "
        "mutations. Without it a failed request can pause instead of failing, "
        "and the error states pinned in this file become unreachable."
    )


def test_application_detail_distinguishes_missing_from_retryable():
    """A 500 / timeout is not a deletion. 404 keeps the existing copy; anything
    else must offer retry via LoadErrorState."""
    source = (_FRONTEND / "app/applications/[id]/page.tsx").read_text()
    assert "This application no longer exists." in source
    assert "LoadErrorState" in source
    assert "status === 404" in source
    assert source.index("if (lastError != null) {") < source.index(
        'title="Couldn\'t load this application."'
    )
    assert source.index("if (lastError != null) {") < source.index(
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


_LOAD_ERROR_CALLERS = sorted(
    str(p.relative_to(_FRONTEND))
    for d in ("app", "components")
    for p in (_FRONTEND / d).rglob("*.tsx")
    if "<LoadErrorState" in p.read_text() and p.name != "load-error-state.tsx"
)


# Each caller's failure BRANCH, exactly: a file-level `"isLoadFailure(" in src`
# stayed green with one of two branches in a file reverted to `.isError`. The
# 404-as-state callers read the remembered error instead (pinned below).
_FAILURE_BRANCHES = {
    "app/referrals/page.tsx": "{isLoadFailure(referrals) ? (",
    "app/base-resumes/page.tsx": "{isLoadFailure(resumes) ? (",
    "app/profile/page.tsx": "{isLoadFailure(setupStatus) ? (",
    "app/applications/page.tsx": "const loadFailed = isLoadFailure(apps) || isLoadFailure(savedJobs);",
    "app/applications/[id]/page.tsx": "if (lastError != null) {",
    "app/templates/page.tsx": "{isLoadFailure(templates) ? (",
    "app/jobs/[id]/page.tsx": "if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {",
    "components/qa-tab.tsx": "{isLoadFailure({ data: entries, isError, fetchStatus, errorUpdateCount }) ? (",
    "components/ats-score-panel.tsx": "if (isLoadFailure(scores)) {",
    "components/settings/setting-card.tsx": "const loadFailed = queries.some((q) => isLoadFailure(q));",
    "components/career/first-run-import-card.tsx": "if (isLoadFailure(entities)) {",
    "components/resume-health/health-report-page.tsx": "if (isLoadFailure(baseQuery)) {",
    "components/chat/chat-page.tsx": "const threadFailed = sessionId !== null && isLoadFailure(detail);",
    "components/setup/getting-started-card.tsx": "if (isLoadFailure(setupStatus)) {",
    "components/chat/scope-picker.tsx": "{isLoadFailure(kbEntities) ? (",
    "components/proposals/proposals-section.tsx": "if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {",
    "components/proposals/proposal-agent-panel.tsx": "if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {",
    # Analytics and the job market tab (Task 17): each card retries in place.
    "components/analytics/analytics-overview.tsx": "{isLoadFailure(activity) ? (",
    "components/analytics/base-summary-cards.tsx": "if (isLoadFailure(summaries)) {",
    "components/analytics/gap-tiers-panel.tsx": "if (isLoadFailure(areas)) {",
    "components/charts/top-skills-chart.tsx": "if (isLoadFailure(query)) {",
    "components/explore/explore-overview.tsx": "if (isLoadFailure(q))",
    "app/base-resumes/[slug]/page.tsx": "if (isLoadFailure(query)) {",
    "app/applications/[id]/resume/page.tsx": "if (isLoadFailure(query)) {",
    "app/templates/[id]/page.tsx": "if (isLoadFailure(tq)) {",
    "app/jobs/[id]/tailor/[sessionId]/page.tsx": "if (sessionError != null) {",
    "components/resume-versions/version-history-sheet.tsx": "{isLoadFailure(versions) && (",
}


def test_every_load_error_caller_has_a_pinned_failure_branch():
    unpinned = set(_LOAD_ERROR_CALLERS) - set(_FAILURE_BRANCHES) - {
        "components/resume-editor/formatting-panel.tsx"
    }
    assert not unpinned, f"add the failure branch of {sorted(unpinned)} to _FAILURE_BRANCHES"


@pytest.mark.parametrize("relpath", _LOAD_ERROR_CALLERS)
def test_a_retry_keeps_the_error_mounted(relpath: str):
    src = (_FRONTEND / relpath).read_text()
    if relpath.endswith("formatting-panel.tsx"):
        # unloadedLayer is the same rule, parity-tested in node and in
        # test_frontend_focus.py. The panel does not call isLoadFailure itself.
        assert "baseline.retrying" in src
        return
    assert _FAILURE_BRANCHES[relpath] in src
    assert not re.search(r"\.error as Error\)\.message", src), (
        "a retry clears `error`: use ?."
    )


# The RENDERED failure must precede the loading gate. A const earlier in the
# file is not the branch: applications computes `loadFailed` above the JSX,
# so the gate is the ternary, not the first `isLoadFailure(`.
_LOADING_GATES = [
    ("app/referrals/page.tsx", '<Skeleton className="h-40 w-full" />', "isLoadFailure(referrals) ?"),
    ("app/applications/page.tsx", "animate-shimmer h-12", "loadFailed ? ("),
    ("components/proposals/proposals-section.tsx", "if (isLoading) {", "if (isLoadFailure("),
    ("components/ats-score-panel.tsx", "scores.isLoading ||", "if (isLoadFailure(scores))"),
    ("components/chat/scope-picker.tsx", "Loading your career history…", "{isLoadFailure(kbEntities) ? ("),
    ("components/analytics/analytics-overview.tsx", "activity.isLoading ?", "isLoadFailure(activity) ?"),
    ("components/analytics/analytics-overview.tsx", "gaps.isLoading ?", "isLoadFailure(gaps) ?"),
    ("components/analytics/analytics-overview.tsx", "buildAreas.isLoading ?", "isLoadFailure(buildAreas) ?"),
    ("components/analytics/base-summary-cards.tsx", "summaries.isLoading", "isLoadFailure(summaries)"),
    ("components/analytics/gap-tiers-panel.tsx", "areas.isLoading", "isLoadFailure(areas)"),
    ("components/charts/top-skills-chart.tsx", "if (isLoading)", "isLoadFailure(query)"),
    ("components/explore/explore-overview.tsx", "q.isLoading", "isLoadFailure(q)"),
]


@pytest.mark.parametrize("relpath,marker,branch", _LOADING_GATES)
def test_a_retry_does_not_fall_into_the_skeleton(relpath: str, marker: str, branch: str):
    src = (_FRONTEND / relpath).read_text()
    assert src.index(branch) < src.index(marker), (
        f"{relpath}: the failure branch must render before the loading gate, "
        "or a retry of a data-less query paints the skeleton and drops focus."
    )


def test_load_error_state_hands_off_focus_and_keeps_its_words():
    src = (_FRONTEND / "components/load-error-state.tsx").read_text()
    assert "useFocusHandoff(rootRef)" in src
    assert "ref={rootRef}" in src
    assert "useLastSeen(detail)" in src
    assert "focusableWhenDisabled" in src


# A 404-as-state reads the REMEMBERED error (`useLoadFailureError`): a retry
# clears `query.error`, and a revisit's first render has none yet, so reading
# `query.error` flashed "Couldn't load… Retrying…" over the 404 wording.
def test_a_missing_application_reads_the_remembered_error():
    src = (_FRONTEND / "app/applications/[id]/page.tsx").read_text()
    assert "const lastError = useLoadFailureError(query);" in src
    assert "const missing = lastError instanceof ApiError && lastError.status === 404;" in src


def test_no_health_report_yet_reads_the_remembered_error_ahead_of_the_skeleton():
    src = (_FRONTEND / "components/resume-health/health-report-page.tsx").read_text()
    assert "const reportError = useLoadFailureError(report);" in src
    assert "const noReportYet = reportError instanceof ApiError && reportError.status === 404;" in src
    assert "const reportFailed = reportError != null && !noReportYet;" in src
    # A retry puts the report back into isLoading; the failure and the 404
    # state must win over the skeleton, or Try again unmounts mid-press.
    assert "if (baseQuery.isLoading || (report.isLoading && reportError == null)) {" in src


def test_a_missing_tailoring_session_reads_the_remembered_error():
    src = (_FRONTEND / "app/jobs/[id]/tailor/[sessionId]/page.tsx").read_text()
    assert "const sessionError = useLoadFailureError(session);" in src
    assert "sessionError instanceof ApiError && sessionError.status === 404;" in src


def test_the_remembered_error_is_null_until_one_was_seen():
    hook = (_FRONTEND / "hooks/use-last-seen.ts").read_text()
    body = hook[hook.index("export function useLoadFailureError(") :]
    assert "const error = useLastSeen(query.error);" in body
    assert "return isLoadFailure(query) ? (error ?? null) : null;" in body


def test_load_error_state_shows_the_remembered_detail():
    src = (_FRONTEND / "components/load-error-state.tsx").read_text()
    assert "{shownDetail ?? " in src
    assert "{detail ?? " not in src


_ROUTE_ERRORS = [
    "app/base-resumes/[slug]/page.tsx",
    "app/applications/[id]/resume/page.tsx",
    "app/templates/[id]/page.tsx",
    "app/jobs/[id]/tailor/[sessionId]/page.tsx",
]


@pytest.mark.parametrize("relpath", _ROUTE_ERRORS)
def test_a_route_level_error_can_retry(relpath: str):
    src = (_FRONTEND / relpath).read_text()
    assert "<LoadErrorState" in src
    assert "onRetry=" in src
    assert _FAILURE_BRANCHES[relpath] in src


# The two hand-rolled header retries (health grade, KB sync pill) used a native
# `disabled` and unmounted on retry, dropping focus to <body>. They share
# RetryChip: LoadErrorState's rules at chip size.
def test_retry_chip_stays_focusable_and_hands_off_focus():
    chip = (_FRONTEND / "components/retry-chip.tsx").read_text()
    assert "useFocusHandoff(ref);" in chip
    assert "aria-disabled={retrying || undefined}" in chip
    assert "if (!retrying) onRetry();" in chip
    assert "disabled=" not in chip.replace("aria-disabled=", "")


_CHIP_BRANCHES = [
    ("components/resume-health/health-badges.tsx", "if (failure != null && !missing) {"),
    ("components/kb-sync-pill.tsx", "if (isLoadFailure(query)) {"),
]


@pytest.mark.parametrize("relpath,branch", _CHIP_BRANCHES)
def test_a_header_chip_retry_keeps_the_chip_mounted(relpath: str, branch: str):
    src = (_FRONTEND / relpath).read_text()
    assert "<RetryChip" in src[src.index(branch) :][:200]


def test_the_health_chip_reads_a_404_from_the_remembered_error():
    src = (_FRONTEND / "components/resume-health/health-badges.tsx").read_text()
    assert "const failure = useLoadFailureError(report);" in src
    assert "const missing = failure instanceof ApiError && failure.status === 404;" in src


# A failed BACKGROUND refetch keeps the loaded editor (isLoadFailure is false
# while data is held); the editor routes say so with a toast instead.
_EDITOR_ROUTES = [
    ("app/base-resumes/[slug]/page.tsx", 'useRefreshFailedNotice(query, "this resume");'),
    ("app/applications/[id]/resume/page.tsx", 'useRefreshFailedNotice(query, "this tailored resume");'),
    ("app/templates/[id]/page.tsx", 'useRefreshFailedNotice(tq, "this template");'),
    ("app/jobs/[id]/tailor/[sessionId]/page.tsx", 'useRefreshFailedNotice(session, "this gap analysis");'),
]


@pytest.mark.parametrize("relpath,call", _EDITOR_ROUTES)
def test_an_editor_reports_a_failed_refresh_without_leaving(relpath: str, call: str):
    assert call in (_FRONTEND / relpath).read_text()


def test_the_refresh_notice_fires_only_over_loaded_data():
    hook = (_FRONTEND / "hooks/use-refresh-failed-notice.ts").read_text()
    assert "query.isError && query.data !== undefined ? query.errorUpdatedAt : 0" in hook
    assert "if (!failedAt) return;" in hook
