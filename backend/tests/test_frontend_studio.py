"""Pins for the honest studio (docs/ux/research-studio-and-ui-direction.md,
Phase 1): the preview says when it is stale, the divider works from the
keyboard, save status lives in the header, Cmd/Ctrl+S saves, and the page
sits on a canvas with zoom presets."""

from __future__ import annotations

import re
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


def test_rename_resyncs_the_base_studio():
    # A rename PATCHes /identity and lands in the cache with the form already
    # holding the new name. Form == server is a re-sync, not an unsaved edit.
    assert "localSnap === liveSnap" in _BASE


def test_base_empty_preview_points_at_generate_not_save():
    # Save is dirty-gated, so a clean resume with no PDF cannot be saved.
    assert "Save the resume to render one." not in _BASE
    assert "No PDF yet. Generate one from More resume actions (⋯)." in _BASE
    overflow = _read("components/resume-editor/studio-overflow.tsx")
    assert 'aria-label="More resume actions"' in overflow


def test_base_regenerate_refreshes_the_gallery():
    # The gallery's "last render failed" badge reads the list query.
    block = _BASE[_BASE.index("const regenerate = useMutation(") :]
    block = block[: block.index("onError")]
    assert 'qc.invalidateQueries({ queryKey: ["base-resumes"] });' in block


def test_tailored_rescore_hint_reads_unsaved():
    # The button stays disabled on `dirty` (no re-score mid-render), but the
    # hint must not claim unsaved edits during the post-save gap.
    block = _TAILORED[_TAILORED.index("rescore.mutate({ announce: true })") :]
    block = block[: block.index("</Button>")]
    assert "disabled={busy || dirty}" in block
    assert re.search(r"title=\{\s*unsaved\s*\?", block)


def test_tailored_unsaved_equals_dirty_before_the_first_save():
    assert "savedSnapshot === null ||" in _TAILORED


def test_studio_overflow_menu_sizes_to_its_labels():
    # The primitive anchors a menu to its trigger's width: 28px for the ⋯
    # button, so every label wrapped at the 128px floor. Capped at the room
    # Base UI measures, so a long "Copy slug: …" cannot leave a narrow viewport,
    # and wrapped anywhere, since a slug's underscores never break.
    overflow = _read("components/resume-editor/studio-overflow.tsx")
    assert (
        'className="w-auto min-w-56 max-w-(--available-width) wrap-anywhere"'
        in overflow
    )


_PREVIEW = _read("components/resume-editor/pdf-pages-preview.tsx")


def test_preview_offers_zoom_presets_as_a_labelled_group():
    assert 'role="group"' in _PREVIEW and 'aria-label="Zoom"' in _PREVIEW
    assert "PREVIEW_ZOOMS" in _PREVIEW and "aria-pressed" in _PREVIEW
    assert "bg-canvas" in _PREVIEW


def test_preview_dpi_matches_the_backend_rasterizer():
    py = (_BACKEND / "app/services/pdf_preview.py").read_text()
    ts = _read("lib/studio.ts")
    backend_dpi = int(re.search(r"^DPI = (\d+)", py, re.M).group(1))
    frontend_dpi = int(re.search(r"export const PREVIEW_DPI = (\d+);", ts).group(1))
    assert backend_dpi == frontend_dpi


def test_preview_render_error_does_not_ask_for_a_dirty_gated_save():
    # Both studios' Save is disabled with nothing to save.
    assert "and save again" not in _PREVIEW
    assert "Fix the content or template, then save or regenerate the PDF." in _PREVIEW


def test_fit_page_is_bounded_by_the_preview_not_the_viewport():
    # The job page's Resume tab is an 80vh box and the studio pane loses height
    # to its header, stale strip and formatting panel: a viewport offset
    # overflowed both. The scroller is a size container; `cqh` measures it.
    assert "@container-[size]" in _PREVIEW
    assert "max-h-[100cqh]" in _PREVIEW
    assert "dvh" not in _PREVIEW
