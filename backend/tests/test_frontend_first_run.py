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


def _panel() -> str:
    return _read("components/ats-score-panel.tsx")


def _render_body(panel: str) -> str:
    """renderBody()'s own body: from its definition to the call site."""
    return panel[panel.index("function renderBody()") : panel.index("{renderBody()}")]


def test_score_tab_import_dialog_is_hoisted_out_of_the_prompt():
    """The dialog renders once, beside the {renderBody()} CALL, never inside a
    branch: the prompt unmounts on Done, and a dialog inside it would take its
    report and the return-focus target down with it."""
    panel = _panel()
    assert panel.count("<UploadDialog") == 1
    assert "<UploadDialog" not in _render_body(panel)
    assert panel.index("{renderBody()}") < panel.index("<UploadDialog")


def test_score_tab_wrapper_can_take_focus():
    """Focus falls back to the wrapper after Done, so it must be focusable."""
    panel = _panel()
    start = panel.index("<div ref={rootRef}")
    tag = panel[start : panel.index(">", start)]
    assert "tabIndex={-1}" in tag
    assert start < panel.index("{renderBody()}")  # it wraps the body


def test_score_tab_import_returns_focus_to_its_opener_while_it_is_there():
    """Cancel or Escape leaves the prompt up, so focus goes back to Import
    resumes; after an import the button is gone and the wrapper takes it."""
    panel = _panel()
    assert "finalFocus={importFinalFocus}" in panel
    assert "opener?.isConnected ? opener : rootRef.current" in panel
    assert "<Button ref={importButtonRef}" in panel
    assert "finalFocus" in _read("components/setup/upload-dialog.tsx")


def test_score_tab_rescore_awaits_the_refetch():
    """The run stays pending until the list refetches, so "No ATS scores yet."
    never paints between the prompt and the cards."""
    assert re.search(r"onSuccess:\s*\(\)\s*=>\s*qc\.invalidateQueries", _panel())


def test_score_tab_rescores_in_the_same_event_as_the_close():
    """mutate() inside the close handler marks the run pending before the
    render that drops the prompt, so that render paints the skeleton. Deferred,
    it paints "No ATS scores yet." for a frame."""
    panel = _panel()
    start = panel.index("const onImportOpenChange = (open: boolean) => {")
    handler = panel[start : panel.index("\n  };", start)]
    assert "setImportOpen(open);" in handler
    assert "run.mutate();" in handler
    for deferral in ("setTimeout", "queueMicrotask", "await", "requestAnimationFrame"):
        assert deferral not in handler, deferral


def test_score_tab_skeleton_never_hides_a_failed_fetch():
    """A failed refetch keeps its old `[]`, and the auto-run waits for success,
    so an idle run over that `[]` must not hold the skeleton: the error state
    and its Retry would never render."""
    panel = _panel()
    assert "run.isIdle && scores.isSuccess && scores.data.length === 0" in panel
    assert "scores.data?.length === 0" not in panel


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
