"""Pins for the first-run path: the task before the checklist, one create
action per screen, the two required setup steps marked, and no dead ends
(Score tab with no base resumes; Extract with no API key)."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_empty_tracker_leads_with_the_task_not_the_checklist():
    page = _read("app/applications/page.tsx")
    empty = page[page.index("filtered.length === 0 ?") :]
    assert empty.index("<EmptyState") < empty.index("<GettingStartedCard")


def test_header_new_application_only_while_the_sidebar_fab_is_hidden():
    page = _read("app/applications/page.tsx")
    assert "useSidebarHidden()" in page
    assert "sidebarHidden ? (" in page


def test_required_setup_steps_are_marked():
    assert _read("components/setup/setup-steps.ts").count("required: true") == 2
    card = _read("components/setup/getting-started-card.tsx")
    assert "row.required && !row.done" in card


def test_score_tab_offers_import_when_there_is_nothing_to_score():
    panel = _read("components/ats-score-panel.tsx")
    assert "No base resumes to score against." in panel
    assert "<UploadDialog" in panel
    # A failed list fetch must never read as "you have none" (conventions).
    assert "bases.isSuccess && bases.data.length === 0" in panel
    assert panel.index("scores.isError") < panel.index(
        "No base resumes to score against."
    )
