"""Pins for the honest studio (docs/ux/research-studio-and-ui-direction.md,
Phase 1): the preview says when it is stale, the divider works from the
keyboard, save status lives in the header, Cmd/Ctrl+S saves, and the page
sits on a canvas with zoom presets."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_BACKEND = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


_SHELL = _read("components/resume-editor/editor-shell.tsx")


def test_divider_is_keyboard_operable():
    sep = _SHELL[_SHELL.index('role="separator"') :]
    sep = sep[: sep.index("/>")]
    for attr in (
        "tabIndex={0}",
        'aria-label="Resize preview"',
        "aria-valuenow={Math.round(editorPct)}",
        "aria-valuetext=",
        "aria-controls=",
        "aria-valuemin=",
        "aria-valuemax=",
        "onKeyDown=",
    ):
        assert attr in sep, attr
    assert "nextPreviewPct(" in _SHELL


def test_preview_says_when_it_is_stale():
    assert "previewStale" in _SHELL
    assert "Preview doesn't include your unsaved edits. Save to update it." in _SHELL


def test_preview_pane_is_a_canvas():
    assert "bg-canvas" in _SHELL
    assert "bg-muted/30" not in _SHELL


_BASE = _read("components/resume-editor/editor-body.tsx")


def test_base_studio_save_is_dirty_gated_and_keyed():
    assert "disabled={!canSave}" in _BASE
    assert "useSaveShortcut(" in _BASE
    assert 'aria-keyshortcuts="Meta+S Control+S"' in _BASE


def test_base_studio_can_rerender_with_nothing_to_save():
    assert "/render`" in _BASE
    assert '"Regenerate PDF"' in _BASE


def test_base_studio_reports_save_in_the_header_not_a_toast():
    assert "<SaveStatusText" in _BASE
    assert "Saved. PDF re-rendered." not in _BASE
    assert "previewStale={hasUnsavedChanges}" in _BASE


_TAILORED = _read("components/resume-editor/tailored-resume-studio.tsx")


def test_tailored_save_chain_fires_no_success_toasts():
    assert '"Saved. Rendering PDF…"' not in _TAILORED
    assert 'toast.success("PDF rendered")' not in _TAILORED
    # The chained re-score is silent; a manual Re-score still confirms, since
    # the score itself is not shown in the studio yet (Phase 2 chip).
    assert "if (opts?.announce)" in _TAILORED
    assert "rescore.mutate({ announce: true })" in _TAILORED


def test_tailored_studio_status_shortcut_and_stale_preview():
    assert "<SaveStatusText" in _TAILORED
    assert "useSaveShortcut(" in _TAILORED
    assert 'aria-keyshortcuts="Meta+S Control+S"' in _TAILORED
    assert "previewStale={unsaved}" in _TAILORED


def test_tailored_status_ignores_the_post_save_refetch_gap():
    # `dirty` still feeds the parent's adoption guard; the USER-facing signals
    # read `unsaved`, which forgets the gap before the remount.
    assert "savedSnapshot" in _TAILORED
    assert "dirty: unsaved" in _TAILORED
    assert "const canSave = unsaved && !busy;" in _TAILORED
    assert "onDirtyChange(dirty)" in _TAILORED
