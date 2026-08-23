"""Source pins for the base→KB sync indicator and provenance labels.

There is no JS test runner in this repo (`test_frontend_query_error_states.py`
is the precedent), so these tests pin the structural contract CI can check.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_BACKEND = Path(__file__).resolve().parents[2] / "backend"


def test_types_declare_sync_status_and_result():
    source = (_FRONTEND / "lib/types.ts").read_text()
    assert "export interface SyncStatus" in source
    assert "export interface SyncResult" in source
    # Scoped to the SyncStatus block: whole-file assertions here were satisfied
    # by SyncResult, which already carried `last_kb_synced_at`, so the pin said
    # nothing about the interface it was written for.
    status_block = source.split("export interface SyncStatus")[1].split("export interface")[0]
    assert "skills_new" in status_block
    assert "recorded_drift" in status_block
    assert "last_kb_synced_at" in status_block


def test_kb_point_out_type_includes_nullable_provenance():
    source = (_FRONTEND / "lib/types.ts").read_text()
    point_block = source.split("export interface KBPointOut")[1].split("export interface")[0]
    assert "provenance" in point_block


def test_api_exposes_kb_sync_status_and_apply_fetchers():
    source = (_FRONTEND / "lib/api.ts").read_text()
    assert "kb-sync-status" in source
    assert 'method: "POST"' in source
    assert "/kb-sync" in source
    assert "getKbSyncStatus" in source
    assert "applyKbSync" in source


def test_kb_sync_pill_error_branch_precedes_the_reassuring_state():
    source = (_FRONTEND / "components/kb-sync-pill.tsx").read_text()
    assert "isError" in source
    assert "Sync now" in source
    assert "/career" in source
    error_at = source.index("isError")
    # The clean chip's title, not its "KB synced" label: the label's words also
    # appear in comments above the component, where index() would find them.
    clean_at = source.index("Career KB up to date")
    assert error_at < clean_at, (
        "a failed status fetch must not be able to render as the in-sync chip"
    )


def test_kb_sync_pill_count_excludes_recorded_drift():
    """The pill's number is work to do. UNRECORDED drift IS work — syncing is
    exactly how it becomes a filed note — so it counts. `recorded_drift` is
    already filed, and summing that in is what made the old bar nag about a
    resume with nothing to do.
    """
    source = (_FRONTEND / "components/kb-sync-pill.tsx").read_text()
    block = source.split("function actionableCount")[1].split("\n}")[0]
    assert "counts.new" in block
    assert "counts.drift" in block
    assert "skillsNew" in block
    assert "recorded_drift" not in block
    # recorded_drift still has to reach the UI — as its own muted line.
    assert "recorded_drift" in source


def test_kb_sync_pill_toast_counts_skill_items_not_categories():
    """`SyncResult.skills` is CATEGORY names. Counting it told the user one
    skill had been filed when two landed in the same category."""
    source = (_FRONTEND / "components/kb-sync-pill.tsx").read_text()
    assert "onSuccess:" in source, "mutation success handler anchor is gone"
    assert "onError:" in source, "mutation error handler anchor is gone"
    block = source.split("onSuccess:")[1].split("onError:")[0]
    assert "skills_added.length" in block
    assert "result.skills.length" not in block
    # Singular/plural, now that the number is worth reading.
    assert 'skill${added === 1 ? "" : "s"}' in block


def test_types_sync_result_carries_skills_added():
    source = (_FRONTEND / "lib/types.ts").read_text()
    assert "export interface SyncResult" in source
    block = source.split("export interface SyncResult")[1].split("export interface")[0]
    assert "skills_added" in block


def test_base_resume_studio_mounts_the_pill_not_a_page_bar():
    page = (_FRONTEND / "app/base-resumes/[slug]/page.tsx").read_text()
    assert "KbSyncCard" not in page
    body = (_FRONTEND / "components/resume-editor/editor-body.tsx").read_text()
    assert "KbSyncPill" in body
    # It belongs beside the health badges, in the toolbar's `status` slot.
    # Assert the anchors before slicing: a slot rename or reorder should fail
    # here with a sentence rather than as an IndexError from the split.
    assert "status={" in body, "StudioToolbar `status` slot anchor is gone"
    assert "tools={" in body, "StudioToolbar `tools` slot anchor is gone"
    assert body.index("status={") < body.index("tools={"), (
        "`status` must still precede `tools` for this slice to bound the slot"
    )
    status_block = body.split("status={")[1].split("tools={")[0]
    assert "KbSyncPill" in status_block
    assert "HealthBadges" in status_block


def test_kb_sync_card_is_gone():
    assert not (_FRONTEND / "components/kb-sync-card.tsx").exists()


def test_points_list_null_provenance_renders_unlabeled():
    source = (_FRONTEND / "components/career/points-list.tsx").read_text()
    assert '"unlabeled"' in source
    unlabeled_block_start = source.index("unlabeled")
    window = source[unlabeled_block_start : unlabeled_block_start + 400]
    assert "bg-emerald" not in window
    assert "bg-primary" not in window


def test_merge_picker_never_offers_a_target_the_server_would_refuse():
    """The merge endpoint 400s on a cross-kind merge, an `extra` section-key
    mismatch, and an archived TARGET (an archived source is how a duplicate is
    retired). The picker must not OFFER any of those — a user who can click it
    has already been told it will work.
    """
    source = (_FRONTEND / "components/career/merge-entity-dialog.tsx").read_text()
    assert "const candidates" in source, "candidate-list anchor is gone"
    block = source.split("const candidates")[1].split("}, [")[0]
    # Same kind, not the source itself, not archived.
    assert "entity.kind === source.kind" in block
    assert 'entity.status !== "archived"' in block, (
        "an archived target is a guaranteed 400; the picker must filter it out"
    )
    assert "entity.id !== source.id" in block
    # `extra` entities merge only within one section, matched the way the
    # server matches (services/career_kb.py `_section_key`): strip + casefold.
    assert "sectionKey(entity) === sourceSection" in block
    assert ".trim().toLowerCase()" in source


def test_merge_dialog_refetches_on_a_lost_race():
    """A 409 means the list on screen is a lie. Toasting without refetching
    would leave the stale card sitting there.

    Scoped to the `onError` handler on purpose: the earlier whole-file version
    of this pin passed with the 409 branch no-oped, because `409` still
    appeared in a comment and the invalidate still appeared in `onSuccess`.
    """
    source = (_FRONTEND / "components/career/merge-entity-dialog.tsx").read_text()
    assert "onError:" in source, "mutation error handler anchor is gone"
    block = source.split("onError:")[1].split("\n  });")[0]
    assert "error.status === 409" in block
    assert 'queryKey: ["kb", "entities"]' in block, (
        "the lost-race branch must refetch, not just toast"
    )
    assert "close()" in block


def test_api_exposes_the_merge_fetcher():
    """Scoped to the function body: a whole-file `method: "POST"` assertion is
    satisfied by any of the two dozen other POSTs in this module."""
    source = (_FRONTEND / "lib/api.ts").read_text()
    assert "export function mergeKbEntity" in source, "merge fetcher is gone"
    block = source.split("export function mergeKbEntity")[1].split("\n}")[0]
    assert "/merge" in block
    assert 'method: "POST"' in block, "merge is a POST; a GET would not mutate"
    assert "target_id" in block


def test_entity_card_reuses_the_gallery_shell_for_its_link_layering():
    """A `<button>` inside an `<a>` is invalid HTML and steals the click. The
    card does not hand-roll the fix — it reuses the gallery shell, whose link is
    a z-10 SIBLING and whose actions wrapper is z-20. A `<Link` reappearing in
    this file means someone went back to wrapping the card, which would swallow
    the actions menu.
    """
    source = (_FRONTEND / "components/career/entity-card.tsx").read_text()
    assert "Merge into…" in source
    assert "GalleryCard" in source
    assert "GalleryCardActions" in source
    assert "<Link" not in source, (
        "the card must not re-introduce a link WRAPPING its actions menu"
    )
    shell = (_FRONTEND / "components/gallery/gallery-card.tsx").read_text()
    assert "absolute inset-0 z-10" in shell
    # The full class run, not bare "z-20" — the gallery docblock PROSE also
    # says z-20, which made the bare form vacuous (mutation-verified).
    assert "relative z-20 ml-auto shrink-0" in shell


def test_point_out_schema_declares_provenance():
    source = (_BACKEND / "app/schemas/career_kb.py").read_text()
    block = source.split("class KBPointOut")[1].split("class ")[0]
    assert "provenance" in block
