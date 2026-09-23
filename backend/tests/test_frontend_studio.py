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


def test_template_editor_fills_the_viewport_and_contact_fits():
    page = _read("app/templates/[id]/page.tsx")
    assert "<FullscreenEditorPage>" in page
    contact = _read("components/resume-editor/contact-form.tsx")
    assert "minmax(0,1fr)" in contact
    assert "wrap-anywhere" in contact
    assert "grid-cols-[8rem_1fr]" not in contact


def test_divider_has_a_pointer_alternative():
    assert 'aria-label="Widen preview"' in _SHELL
    assert 'aria-label="Narrow preview"' in _SHELL


def test_divider_tracks_the_pointer_on_the_shell():
    assert "onPointerCancel=" in _SHELL
    assert "setPointerCapture(" in _SHELL
    assert "window.innerWidth" not in _SHELL
    show = _SHELL.index('aria-label="Show PDF preview"')
    button = _SHELL.rfind("<button", 0, show)
    block = _SHELL[button : _SHELL.index("</button>", show)]
    assert "absolute" not in block


def test_divider_drag_persists_on_release_only():
    # A drag re-renders from `dragPct`; storage is written on release, so a
    # drag is not a localStorage write per pointer move.
    drag = _SHELL[_SHELL.index("onDrag={") :]
    drag = drag[: drag.index("onDragEnd={")]
    assert "setDragPct(" in drag
    assert "setStoredPct" not in drag
    end = _SHELL[_SHELL.index("onDragEnd={") :]
    assert "setStoredPct(" in end[: end.index("onReset={")]


def test_divider_sizes_from_the_shell_and_resets_on_double_click():
    splitter = _SHELL[_SHELL.index("function Splitter(") :]
    assert "parentElement!.getBoundingClientRect()" in splitter
    assert "onDoubleClick={onReset}" in splitter


def test_stored_preferences_are_not_hydrated_in_an_effect():
    for rel in (
        "components/resume-editor/editor-shell.tsx",
        "components/resume-editor/pdf-pages-preview.tsx",
        "components/chat/chat-page.tsx",
    ):
        assert "set-state-in-effect" not in _read(rel), rel


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


def test_save_button_keeps_focus_when_it_disables_itself():
    # A disabled native <button> drops focus to <body>, and Save disables
    # itself on every click. `disabled:` matches only the native attribute, so
    # the dimming is restated on `data-disabled`.
    assert "focusableWhenDisabled" in _SAVE_BUTTON
    assert "data-disabled:opacity-50" in _SAVE_BUTTON


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
    # read `unsaved`, which forgets the gap before the refetch moves the baseline.
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
    # No re-score while the chain's render is out (`render.isPending`); the
    # gate and the hint both read `unsaved`, so the post-save gap does not
    # claim edits the server already has. `busy` stays free of the render:
    # Save must still work for text typed while a PDF is rendering.
    busy = _TAILORED[_TAILORED.index("const busy =") :]
    busy = busy[: busy.index(";")]
    assert "render.isPending" not in busy
    block = _TAILORED[_TAILORED.index("rescore.mutate({ announce: true })") :]
    block = block[: block.index("</Button>")]
    assert "disabled={busy || render.isPending || unsaved}" in block
    assert re.search(r"title=\{\s*unsaved\s*\?", block)


def test_generate_pdf_gate_reads_unsaved():
    # ⋯ Generate PDF renders the server copy, so it waits on edits the server
    # has not seen (`unsaved`), not on the post-save `dirty` gap.
    click = _TAILORED.index('onClick={() => render.mutate()}')
    start = _TAILORED.rfind("<DropdownMenuItem", 0, click)
    block = _TAILORED[start:click]
    assert "disabled={busy || render.isPending || unsaved}" in block
    review = _TAILORED[_TAILORED.index("<DiffReviewPanel") :]
    review = review[: review.index("/>")]
    assert "dirty={unsaved}" in review


# Formatting knobs are diffed (`diffFrom`) against the panel's baseline, so an
# edit made before every layer of it has loaded drops an explicit override equal
# to the incomplete one. The panel takes a `FormattingBaseline` state and enables
# its knobs only on "ready"; lib/formatting.test.ts pins the layer combinators.
_HOOKS = _read("components/templates/template-select.tsx")
_PANEL = _read("components/resume-editor/formatting-panel.tsx")


def _function(src: str, name: str) -> str:
    body = src[src.index(f"function {name}(") :]
    return body[: body.index("\n}\n")]


def test_templates_query_is_defined_once_and_shared():
    # The picker and the baseline must read one query: a second copy of the key
    # could point at a different endpoint and resolve a different template.
    assert _HOOKS.count('queryKey: ["templates", "all"]') == 1
    assert 'queryKey: ["templates", "all"]' in _function(_HOOKS, "useTemplatesQuery")
    assert "useTemplatesQuery()" in _function(_HOOKS, "TemplateSelect")


def test_template_baseline_is_never_ready_without_the_templates_list():
    hook = _function(_HOOKS, "useTemplateBaseline")
    assert "useTemplatesQuery()" in hook
    guard = "if (q.data === undefined) return unloadedLayer(q,"
    assert guard in hook
    assert hook.index(guard) < hook.index('status: "ready"')


def test_formatting_panel_requires_an_explicit_baseline_state():
    props = _PANEL[_PANEL.index("export function FormattingPanel(") :]
    props = props[: props.index("}) {")]
    assert "baseline: FormattingBaseline;" in props
    assert "supportedKeys" not in props
    assert 'const ready = baseline.status === "ready";' in _PANEL
    assert "!ready || unsupported(key)" in _PANEL
    assert "diffFrom(inheritedValues," in _PANEL


def test_formatting_panel_reports_a_failed_baseline_with_a_retry():
    # A failed fetch is a third state: never the "Loading…" line forever.
    loading = _PANEL.index('baseline.status === "loading" &&')
    error = _PANEL[_PANEL.index('baseline.status === "error" &&') :]
    error = error[: error.index("/>")]
    assert "<LoadErrorState" in error
    assert "onRetry={baseline.retry}" in error
    assert "retrying={baseline.retrying}" in error
    assert "Loading {baseline.what}" in _PANEL[loading : loading + 200]


def test_formatting_retry_never_drops_focus_to_body():
    # Try again disables itself while retrying and then unmounts with the error:
    # a disabled native <button> and an unmounted one both drop focus to <body>.
    button = _read("components/load-error-state.tsx")
    assert "focusableWhenDisabled" in button
    assert "data-disabled:opacity-50" in button
    # Recovery hands focus to the panel body through LoadErrorState. The body
    # wrapper stays tabIndex={-1} so it is the handoff's target.
    assert "refocusWhenReady" not in _PANEL
    error = _PANEL[_PANEL.index('baseline.status === "error" &&') :]
    assert "onRetry={baseline.retry}" in error[: error.index("/>")]
    wrapper = _PANEL[: _PANEL.index('baseline.status === "error" &&')]
    wrapper = wrapper[wrapper.rindex("<div") :]
    assert re.search(r"tabIndex=\{-1\}", wrapper)


def test_every_formatting_panel_caller_passes_a_baseline_state():
    for rel in (
        "components/resume-editor/tailored-resume-studio.tsx",
        "components/resume-editor/editor-body.tsx",
    ):
        src = _read(rel)
        assert "baseline={formattingBaseline}" in src, rel
        assert "useTemplateBaseline(templateId)" in src, rel
    page = _read("app/templates/[id]/page.tsx")
    # Mounted only once its own template query resolves, whose row IS the
    # baseline (the schema constant plus that row's key list).
    assert "if (tq.isLoading || !tq.data)" in page
    assert "supportedKeys: tq.data.supported_fmt_keys," in page


def test_tailored_baseline_waits_for_the_base_resume_layer():
    # The application inherits the base resume's formatting; an edit diffed
    # against the template layer alone drops an override equal to it.
    assert "const baseResume = useQuery({" in _TAILORED
    assert "overlayBaseline(\n    templateBaseline,\n    baseResume," in _TAILORED
    assert "baseResume?.formatting" not in _TAILORED


def test_tailored_unsaved_equals_dirty_before_the_first_save():
    assert "savedSnapshot === null ||" in _TAILORED


def test_tailored_own_saves_adopt_in_place():
    # A one-shot "the next key is ours" flag never said WHICH key: a
    # formatting-only save left it armed, and the next chat/MCP edit remounted
    # the editor over unsaved edits. Own keys are now queued by content
    # (`serverKey`: the query cache keeps old key order in unchanged subtrees)
    # and move the baseline without a remount; only a copy that replaces the
    # content bumps `editorGen`.
    assert "adoptNextServerKey" not in _TAILORED
    assert "serverKey(application.customized_json)" in _TAILORED
    assert re.search(
        r"const key = serverKey\(result\.customized_json\);\s*onSaved\(key\);",
        _TAILORED,
    )
    assert "adoptServerKey(" in _TAILORED
    # Before paint: the refetch renders the new live key first, and a passive
    # effect let that frame paint the "changed outside the editor" banner.
    assert re.search(r"useLayoutEffect\(\(\) => \{\s*const next = adoptServerKey\(", _TAILORED)
    assert "key={editorGen}" in _TAILORED
    assert "key={adoptedKey}" not in _TAILORED


def test_rebuild_replaces_the_editor_even_when_its_key_does_not_move():
    # The adoption effect runs only when a key moves. A Rebuild whose content
    # equals the adopted (or the live) copy moves nothing, so it replaces the
    # editor from its own success path; any other Rebuild arms `forcedKey`.
    materialize = _mutation(_TAILORED, "materialize")
    assert "replaceEditor(key)" in materialize
    assert "forcedKey.current = key" in materialize
    # The response goes straight into the cache: until the refetch landed, a
    # remounted clean editor adopted the STALE foreign copy the banner was
    # about, and painted it.
    assert 'qc.setQueryData(["application", applicationId], result)' in materialize


def test_tailored_dirty_compares_formatting_by_content():
    # A content-only refetch keeps the OLD formatting object (structural
    # sharing) while local state holds the PATCH response. Equal content in a
    # different key order (Postgres-migrated or MCP-written formatting) left
    # `dirty` stuck: Re-score and Generate disabled, the leave-page prompt
    # armed, foreign edits bannered, under "All changes saved".
    assert "const serverFormatting = serverKey(application.formatting);" in _TAILORED
    assert "serverKey(formatting) !== serverFormatting" in _TAILORED
    assert "JSON.stringify(application.formatting" not in _TAILORED


def test_save_responses_keep_edits_made_while_saving():
    # A save's response used to overwrite the form wholesale: text typed during
    # the PATCH (the base studio's PUT renders inline, so for seconds) vanished
    # under "All changes saved".
    assert "keepIfEdited(" in _TAILORED
    assert "sentData" not in _TAILORED
    assert "keepIfEdited(" in _BASE
    assert "adoptBaseResumeDetail(" not in _mutation(_BASE, "save")


_RAW_JSON = _read("components/resume-editor/raw-json-toggle.tsx")


def test_raw_json_drafts_count_as_unsaved():
    # The typed JSON lived only in the pane: status said "All changes saved",
    # Save and Cmd/Ctrl+S were off, the leave-page prompt stayed quiet, and
    # Cancel or "Form view" dropped the text. The pane now reports a pending
    # draft up, and both studios fold it into their unsaved signals.
    assert "onPendingChange" in _RAW_JSON
    for studio in (_TAILORED, _BASE):
        assert "useRawJsonDraft(" in studio
        assert "{...raw.bind}" in studio
    assert re.search(r"const unsaved =\s*raw\.pending \|\|", _TAILORED)
    # `dirty` too: the leave-page warning and the adoption guard read it, so a
    # foreign edit shows the banner instead of remounting over the draft.
    assert re.search(r"const dirty = useMemo\(\s*\(\) =>\s*raw\.pending \|\|", _TAILORED)
    assert "const hasUnsavedChanges = raw.pending ||" in _BASE
    # A server copy is never adopted underneath a pending draft: a later Apply
    # would silently overwrite it.
    assert "localSnap === lastSyncedRef.current && !raw.pending" in _BASE


def test_save_applies_a_pending_raw_draft_first():
    # Apply is the pane's commit step, as blur is a chip input's: Save and the
    # chord apply a valid draft, then save exactly what was applied (setData is
    # async). An invalid draft saves nothing; the pane's alert says why.
    for studio in (_TAILORED, _BASE):
        assert "raw.commitThen(setData, (applied) =>" in studio
        assert "data: applied ?? data" in studio
        assert "raw.commitThen(setData, () => setRawMode(false))" in studio
    assert "if (committed === null) return;" in _RAW_JSON
    assert 'role="alert"' in _RAW_JSON


def test_raw_json_cancel_confirms_before_discarding():
    assert "Discard your JSON edits?" in _RAW_JSON
    assert re.search(r"if \(\s*pending &&\s*!\(await confirm\(", _RAW_JSON)
    # Wired: an unwired `cancel` leaves the button closing the pane silently.
    assert "onClick={cancel}" in _RAW_JSON


def test_raw_json_pending_reaches_the_studio():
    # The pane reports every change of `pending`, and closing it clears the
    # studio's flag: a pane that unmounts mid-draft left "Unsaved changes" on.
    assert re.search(
        r"useEffect\(\(\) => \{\s*onPendingChange\(pending\);\s*\}, \[pending, onPendingChange\]\);",
        _RAW_JSON,
    )
    assert "useEffect(() => () => onPendingChange(false), [onPendingChange]);" in _RAW_JSON
    # The Save button and the chord run the apply-then-save handler.
    for studio in (_TAILORED, _BASE):
        assert "onSave={onSave}" in studio


def test_raw_json_error_clears_with_its_draft():
    # Invalid JSON, Save (alert), undo back to the form's copy, then a template
    # change saved: the save succeeded under a red "Unexpected token" alert.
    assert "onChange={edit}" in _RAW_JSON
    assert "if (!jsonDraftDiffers(next, value)) setError(null);" in _RAW_JSON
    assert re.search(
        r"if \(!pending\) \{\s*setError\(null\);\s*return undefined;", _RAW_JSON
    )


def test_raw_json_pane_resyncs_to_the_saved_copy():
    # Raw mode survives a Save (no remount), and the pane's text was set once:
    # after apply-then-save it still held the pre-save text. A value that
    # changes under text matching the PREVIOUS value re-syncs; comparing with
    # the new value would lock a normalized save into "pending".
    assert "if (value !== shown) {" in _RAW_JSON
    assert "if (!jsonDraftDiffers(text, shown)) setText(" in _RAW_JSON
    assert "jsonDraftDiffers(text, value)" in _RAW_JSON


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
    assert "shownSectionOrder(baseline.section_order)" in _read("lib/formatting.ts")


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


# --- Task 18: keys typed with Cmd/Ctrl+S are never lost (F3) --------------


def _squash(source: str) -> str:
    return re.sub(r"\s+", " ", source)


def _body(src: str, head: str, end: str = "\n  };\n") -> str:
    start = src.index(head)
    return src[start : src.index(end, start)]


_SHORTCUT = _read("hooks/use-save-shortcut.ts")


def test_save_shortcut_commits_a_draft_with_no_gap():
    handler = _body(_SHORTCUT, "const onKeyDown = (event: KeyboardEvent) =>", "\n    };\n")
    # The blur's commit lands NOW, and focus is back before the handler
    # returns, so a key queued behind the chord lands in the field.
    assert "setTimeout" not in _SHORTCUT, "a refocus on the next task drops the keys typed in between"
    assert "const back = focusReturnPoint(field);" in handler[: handler.index("flushSync(")]
    tail = handler[handler.index("flushSync(() => field.blur());") :]
    assert tail.index("focusIfDropped(back());") < tail.index("save();")
    assert 'import { flushSync } from "react-dom";' in _SHORTCUT


def test_a_chip_edit_that_closes_hands_focus_to_the_add_row():
    chips = _read("components/ui/chip-input.tsx")
    assert "const focusNext = useFocusOnNextCommit();" in chips
    for head in ("const commitEdit = () =>", "const cancelEdit = () =>"):
        body = _body(chips, head)
        # Armed before any early exit that follows the close.
        assert "setEditingIndex(null);\n    focusNext(addRowRef);" in body, head
    add_row = chips[chips.rindex("<input") :]
    assert "ref={addRowRef}" in add_row[: add_row.index("/>")]


def test_a_rename_that_closes_hands_focus_to_its_button():
    sections = _read("components/resume-editor/extra-sections-editor.tsx")
    commit = _body(sections, "const commitRename = () =>")
    assert "setRenaming(false);\n    focusNext(renameButtonRef);" in commit
    escape = _squash(sections[sections.index('if (e.key === "Escape") {') :])
    escape = escape[: escape.index("} else if")]
    assert "setRenaming(false); focusNext(renameButtonRef);" in escape
    # Focus lands on the button during Enter's keydown; without this, Enter's
    # activation pressed it and reopened the rename.
    enter = _squash(sections[sections.index('} else if (e.key === "Enter" && !titleCollides) {') :])
    assert "e.preventDefault(); commitRename();" in enter[: enter.index("}", 1)]
    button = sections[sections.index("ref={renameButtonRef}") :]
    assert button.index('aria-label={renaming ? "Done renaming" : "Rename section"}') < 200


def test_the_title_input_hands_focus_back_to_its_pencil():
    title = _read("components/resume-editor/editable-title.tsx")
    assert "setEditing(false);\n    focusNext(pencilRef);" in _body(title, "const commit = () =>")
    escape = _squash(title[title.index('} else if (e.key === "Escape") {') :])
    assert "setEditing(false); focusNext(pencilRef);" in escape[: escape.index("}", 1)]
    pencil = title[title.index("<IconButton") :]
    assert "ref={pencilRef}" in pencil[: re.search(r"\n\s*/>", pencil).end()]
