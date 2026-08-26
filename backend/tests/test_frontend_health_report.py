"""Pins for the 2026-08-25 health report page redesign (lane B).

There is no JS test runner in CI for React; behaviour of the pure helpers is
covered by `frontend/lib/health-report.test.ts` (Node). This file pins the
structural properties CI can actually check from source.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PAGE = (_FRONTEND / "components/resume-health/health-report-page.tsx").read_text()
_CARDS = (_FRONTEND / "components/resume-health/finding-cards.tsx").read_text()
_TYPES = (_FRONTEND / "lib/types.ts").read_text()
_ZONES = (_FRONTEND / "lib/health-zones.ts").read_text()
_HELPERS = (_FRONTEND / "lib/health-report.ts").read_text()
_BADGES = (_FRONTEND / "components/resume-health/health-badges.tsx").read_text()
_GALLERY = (_FRONTEND / "components/base-resumes/base-resume-gallery.tsx").read_text()


def test_two_pane_not_page_measure():
    assert "PageMeasure" not in _PAGE
    assert "lg:grid-cols-[18.75rem_minmax(0,1fr)]" in _PAGE
    assert "lg:sticky" in _PAGE
    assert "Not enough evidence to grade" in _PAGE
    assert "scoreCompositionLine" in _PAGE


def test_groups_by_location_and_renames_heading():
    assert "groupFindings" in _PAGE
    assert "Weakest evidence first" in _PAGE
    assert "What it" not in _PAGE  # old "What it's costing you, in order"


def test_finding_at_rest_is_one_line():
    assert "CollapsedRow" in _CARDS
    assert "DetailsDisclosure" not in _CARDS
    assert "Override classification" in _CARDS
    assert "FindingOverflow" in _CARDS


def test_not_assessed_gate_is_visible():
    assert "Not assessed" in _CARDS
    assert "hasn&apos;t been certified" in _CARDS or "hasn't been certified" in _CARDS
    assert "not_assessed" in _CARDS


def test_notes_are_a_rule_table():
    assert "subject?: string" in _TYPES
    assert "rule?: string" in _TYPES
    assert "NotesTable" in _CARDS
    assert "groupNotesByRule" in _HELPERS


def test_stale_is_surfaced_and_apply_locks():
    assert "reportIsStale" in _PAGE
    assert "changed since" in _PAGE
    assert "re-analyze for current results" in _PAGE
    assert "STALE_APPLY_HINT" in _CARDS
    assert "disabled:pointer-events-auto" in _CARDS


def test_apply_sends_content_hash_and_handles_409():
    assert "expected_content_hash" in _CARDS
    assert "isContentChangedError" in _CARDS
    assert "content changed since analysis" in _HELPERS


def test_close_the_loop_footer_and_delta():
    assert "applied ·" in _PAGE
    assert "Re-analyze to update your grade" in _PAGE
    assert "scoreDelta" in _PAGE
    assert "ResolvedFinding" in _PAGE


def test_list_grade_chip():
    assert "HealthListChip" in _GALLERY
    assert "Blocked" in _BADGES
    assert "fatalGateFailed" in _BADGES


def test_close_the_loop_round2_surfaces():
    assert "Answer the number questions" in _PAGE
    assert "BatchAskDialog" in _PAGE
    assert "MetricAskInput" in _CARDS
    assert "DemonstrateSkillDialog" in _CARDS
    assert "ExpandedFindingChrome" in _CARDS
    assert "Condense" in _CARDS
    assert "draftRewrite" in _CARDS
    assert "explainScoreDelta" in _PAGE
    assert 'This bullet is ${lowered}' in _HELPERS
    assert "Something else" in (
        _FRONTEND / "components/resume-health/metric-ask-input.tsx"
    ).read_text()
    assert "draft-rewrite" in (
        _FRONTEND / "lib/api.ts"
    ).read_text()


def test_level_values_mirrored_in_health_zones():
    assert '"direct": 1.0' in _ZONES or "direct: 1.0" in _ZONES
    assert "analogue: 0.8" in _ZONES
    assert "adjacent: 0.5" in _ZONES
    assert "implied: 0.3" in _ZONES
    assert "unaddressed: 0.0" in _ZONES
    assert "direct: 1.0" in _HELPERS
