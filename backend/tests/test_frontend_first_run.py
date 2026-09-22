"""Pins for the first-run path: the task before the checklist, one create
action per screen, the two required setup steps marked, and no dead ends
(Score tab with no base resumes; Extract with no API key)."""

from __future__ import annotations

import re
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
    # The condition must wrap the HEADER's button, not some other use of the
    # flag: slice from the actions slot to the header button's own link.
    start = page.index("actions={")
    header_actions = page[start : page.index('<Link href="/new">', start)]
    assert "sidebarHidden ? (" in header_actions


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
    # A job the engine cannot score (422) is a job-level fact an import cannot
    # fix, so its reason outranks the import prompt.
    assert panel.index("const unscorable") < panel.index(
        "No base resumes to score against."
    )


def test_score_tab_import_keeps_focus_and_awaits_the_refetch():
    """Import → Done must return focus to a stable wrapper, and the run must
    stay pending until the score list refetches so "No ATS scores yet." never
    paints between the prompt and the cards."""
    panel = _read("components/ats-score-panel.tsx")
    assert re.search(r"onSuccess:\s*\(\)\s*=>\s*qc\.invalidateQueries", panel)
    assert "finalFocus={rootRef}" in panel
    assert "onOpenChange={onImportOpenChange}" in panel
    # The dialog is hoisted once, after renderBody(), so closing it does not
    # unmount the return-focus target with the empty-state prompt.
    assert panel.index("renderBody()") < panel.index("<UploadDialog")
    assert panel.count("<UploadDialog") == 1
    dialog = _read("components/setup/upload-dialog.tsx")
    assert "finalFocus" in dialog


def test_score_tab_rescores_once_after_an_import_never_twice():
    """A cached `[]` must not arm the post-import rescore before the refetch
    confirms it, and the rescore must not fire while a run is in flight: two
    concurrent runs race on the base-score unique key and toast an error."""
    panel = _read("components/ats-score-panel.tsx")
    assert "if (noBases && !bases.isFetching)" in panel
    assert "!importOpen && !run.isPending" in panel


def test_new_application_names_the_key_before_the_paste():
    page = _read("app/new/page.tsx")
    assert "setup.data?.model_key.done === false" in page
    assert "disabled={disabled || busy || needsKey}" in page
    # Placeholders are example values only (conventions: microcopy rules).
    assert "Paste the full job description here" not in page
    assert '<Label htmlFor="source_url" optional>' in page
    assert "The job is listed under Saved. Scoring comes next." in page


def test_disabled_extract_explains_itself():
    page = _read("app/new/page.tsx")
    assert "id={keyNoticeId}" in page
    assert "aria-describedby={needsKey ? keyNoticeId : undefined}" in page
    assert "Add an API key to extract." in page


def test_saving_model_settings_refreshes_setup_status():
    """Every setup-status reader (checklist, strip, /new's key notice) must
    see a newly saved key without waiting out the stale window."""
    models = _read("components/settings/models-section.tsx")
    start = models.index("export function useSaveModelSettings")
    hook = models[start : models.index("\nexport function", start + 1)]
    assert 'invalidateQueries({ queryKey: ["setup-status"] })' in hook
