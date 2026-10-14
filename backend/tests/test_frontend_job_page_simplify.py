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
