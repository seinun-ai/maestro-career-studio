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
