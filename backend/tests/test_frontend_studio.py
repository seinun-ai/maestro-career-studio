"""Pins for the honest studio (docs/plans/2026-09-22-honest-studio.md): the
preview says when it is stale, the divider works from the keyboard, save
status lives in the header, Cmd/Ctrl+S saves, and the page sits on a canvas
with zoom presets."""

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


_SAVE_BUTTON = _read("components/resume-editor/studio-save-button.tsx")


def test_one_save_button_owns_the_click_and_the_shortcut():
    # Key and button read the one `canSave`, so they cannot disagree.
    assert "useSaveShortcut(" in _SAVE_BUTTON
    assert 'aria-keyshortcuts="Meta+S Control+S"' in _SAVE_BUTTON
    assert "disabled={!canSave}" in _SAVE_BUTTON


_BASE = _read("components/resume-editor/editor-body.tsx")


def test_base_studio_save_is_dirty_gated_and_keyed():
    assert "<StudioSaveButton" in _BASE
    assert "canSave={canSave}" in _BASE
    # The button owns the shortcut; a studio wiring its own would be a second
    # owner that can drift from the button.
    assert "useSaveShortcut(" not in _BASE


def test_base_studio_can_rerender_with_nothing_to_save():
    assert "/render`" in _BASE
    assert '"Regenerate PDF"' in _BASE


def test_base_studio_reports_save_in_the_header_not_a_toast():
    assert "<SaveStatusText" in _BASE
    assert "Saved. PDF re-rendered." not in _BASE
    assert "previewStale={hasUnsavedChanges}" in _BASE


_TAILORED = _read("components/resume-editor/tailored-resume-studio.tsx")


def _mutation(src: str, name: str) -> str:
    """`const <name> = useMutation(` up to its onError: the success path."""
    block = src[src.index(f"const {name} = useMutation(") :]
    return block[: block.index("onError")]


def test_tailored_save_chain_fires_no_success_toasts():
    assert '"Saved. Rendering PDF…"' not in _TAILORED
    assert 'toast.success("PDF rendered")' not in _TAILORED
    # Save -> render -> re-score. The save and render success paths toast
    # nothing; the chained re-score is silent, and a manual Re-score still
    # confirms, since the score itself is not shown in the studio yet (Phase 2
    # chip). That confirmation is the chain's ONE success toast.
    assert "toast.success(" not in _mutation(_TAILORED, "save")
    render = _mutation(_TAILORED, "render")
    assert "toast.success(" not in render
    assert "rescore.mutate({ announce: false })" in render
    rescore = _mutation(_TAILORED, "rescore")
    assert rescore.count("toast.success(") == 1
    assert 'if (opts?.announce) toast.success("Tailored resume re-scored");' in rescore
    assert "rescore.mutate({ announce: true })" in _TAILORED


def test_tailored_studio_status_shortcut_and_stale_preview():
    assert "<SaveStatusText" in _TAILORED
    assert "<StudioSaveButton" in _TAILORED
    assert "canSave={canSave}" in _TAILORED
    assert "useSaveShortcut(" not in _TAILORED
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


_STUDIO_LIB = _read("lib/studio.ts")


def test_base_empty_preview_points_at_generate_not_save():
    # Save is dirty-gated, so a clean resume with no PDF cannot be saved.
    assert "Save the resume to render one." not in _BASE
    assert "emptyMessage={emptyPreviewMessage(hasUnsavedChanges)}" in _BASE
    assert "No PDF yet. Generate one from More resume actions (⋯)." in _STUDIO_LIB
    overflow = _read("components/resume-editor/studio-overflow.tsx")
    assert 'aria-label="More resume actions"' in overflow


def test_tailored_empty_preview_never_points_at_a_disabled_save():
    # After Build draft or Rebuild from base the studio is clean with no PDF
    # and Save is disabled. Both studios name the action enabled right now:
    # Save while edits are unsaved, the ⋯ menu's Generate PDF otherwise.
    assert "Save your edits and it renders automatically." not in _TAILORED
    assert "emptyMessage={emptyPreviewMessage(unsaved)}" in _TAILORED
    assert '"No PDF yet. Save to render one."' in _STUDIO_LIB


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


def test_section_order_has_no_drag_path():
    # Reordering is up/down buttons (docs/frontend-conventions.md): drag added a
    # second, pointer-only path and a cursor-grab promise on every row.
    panel = _read("components/resume-editor/formatting-panel.tsx")
    assert "draggable" not in panel
    assert "cursor-grab" not in panel


def test_section_order_buttons_are_24px_targets():
    # Since the drag path went, these are the ONLY pointer reorder path, and two
    # adjacent 18px buttons fail WCAG 2.5.8. The shared icon-xs is 24px, 44px
    # on a coarse pointer, with the standard focus ring.
    panel = _read("components/resume-editor/formatting-panel.tsx")
    block = panel[panel.index("const sectionOrderRow = () => {") :]
    block = block[: block.index("const showContent")]
    assert 'size="icon-xs"' in block
    assert 'variant="ghost"' in block
    assert "<button" not in block


def test_section_order_shows_what_diff_compares():
    # One definition of what `null` shows: diffFrom compares the shown order
    # (lib/formatting.test.ts), so moving a section down and back up stores
    # nothing. A panel-local fallback would drift from that comparison.
    panel = _read("components/resume-editor/formatting-panel.tsx")
    assert "shownSectionOrder(" in panel
    assert "SECTION_ORDER_FALLBACK" not in panel


def test_preview_scroller_is_keyboard_reachable_and_named():
    start = _PREVIEW.index('role="region"')
    scroller = _PREVIEW[start:]
    scroller = scroller[: scroller.index(">")]
    assert 'aria-label="Page preview"' in scroller
    assert "tabIndex={0}" in scroller
    assert re.search(r'className="[^"]*\bpeer\b', scroller)
    # A ring on the scroller itself (box-shadow or negative-offset outline)
    # paints under its own content, so a scrolled page covers it. The ring is
    # a sibling overlay the scroller's focus lights up.
    assert "focus-visible:ring" not in scroller
    overlay = _PREVIEW[start:]
    overlay = overlay[overlay.index('aria-hidden="true"') :]
    overlay = overlay[: overlay.index("/>")]
    assert "pointer-events-none absolute inset-0" in overlay
    assert "peer-focus-visible:ring-2" in overlay


def test_render_error_banner_sits_above_the_scroller():
    # Inside the scroller it pushed page 1 below a Fit-page fold and scrolled
    # away with the pages.
    assert _PREVIEW.index("Preview is stale") < _PREVIEW.index('role="region"')


def test_actual_size_pages_hide_until_their_width_is_known():
    # The PNG is 150 DPI: unhidden, 100% paints it at 1275px before the onLoad
    # snaps it to 816px.
    assert 'zoom === "actual" && naturalWidth === null && "invisible"' in _PREVIEW


def _zoom_button() -> str:
    block = _PREVIEW[_PREVIEW.index("{PREVIEW_ZOOMS.map(") :]
    return block[: block.index("</button>")]


def test_zoom_buttons_grow_on_a_coarse_pointer():
    assert "pointer-coarse:min-h-11" in _zoom_button()
    assert "h-6" in re.search(r'"([^"]*pointer-coarse:min-h-11[^"]*)"', _zoom_button()).group(1).split()


def test_selected_zoom_preset_leads_with_a_check():
    # The secondary-container fill is about 1.16:1 against the group and its
    # label only 2.1:1 from an unselected one: the fill cannot say "on" alone.
    button = _zoom_button()
    assert "aria-pressed={zoom === option.value}" in button
    check = '{zoom === option.value && <Check className="size-3" aria-hidden="true" />}'
    assert check in button
    assert button.index(check) < button.index("{option.label}")


def test_save_button_keeps_its_label_while_saving():
    # "Saving…" in the button widened it from 52 to 89px mid-click. The header
    # status line carries the words; the button keeps "Save" and spins.
    assert "Saving…" not in _SAVE_BUTTON
    assert '{pending && <Loader2 className="animate-spin" aria-hidden="true" />}' in _SAVE_BUTTON
    assert re.search(r"/>\}\s*Save\s*</Button>", _SAVE_BUTTON)


def test_job_page_preview_box_has_no_hidden_fill():
    # The preview paints its own canvas over the whole box, so a fill on the
    # box is hidden weight. Checked per class token (variants included), so
    # reordering the class list cannot slip a background past the pin.
    panel = _read("components/application-panel.tsx")
    head = panel[: panel.index("<PdfPagesPreview")]
    tokens = re.findall(r'<div className="([^"]*)"', head)[-1].split()
    assert "h-[80vh]" in tokens
    assert not [t for t in tokens if t.split(":")[-1].lstrip("!").startswith("bg-")]
