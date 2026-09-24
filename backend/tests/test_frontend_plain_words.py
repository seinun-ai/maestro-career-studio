"""The app speaks the user's words: edits are described, never printed as ops;
resumes are named, never slugged. Node tests are not in CI, so the behaviour of
lib/describe-edit.ts is pinned here: every op kind the backend accepts has a
case, and both surfaces render through it."""

import re
from pathlib import Path

from app.schemas.resume_edit import op_kinds

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_DESCRIBER = _read("lib/describe-edit.ts")


def test_every_op_kind_the_backend_accepts_has_words():
    body = _DESCRIBER[
        _DESCRIBER.index("function describeOne(") : _DESCRIBER.index("\nfunction advance(")
    ]
    cased = set(re.findall(r'case "([a-z_]+)":', body))
    assert cased == op_kinds(), {"missing": op_kinds() - cased, "unknown": cased - op_kinds()}


def test_the_fallback_never_prints_the_kind():
    assert "op.kind}" not in _DESCRIBER  # no template interpolating the key
    assert "// A kind this file does not know yet: plain words, never the key." in _DESCRIBER


def test_the_describer_takes_no_value_imports():
    # node --test loads it; `@/` and extensionless specifiers do not resolve there.
    assert not re.search(r"^import (?!type )", _DESCRIBER, re.M)


def test_both_surfaces_render_words():
    card = _read("components/chat/edit-proposal-card.tsx")
    sheet = _read("components/resume-editor/instruct-sheet.tsx")
    assert "describeEdits(proposal.ops, pending ? doc : null)" in card
    assert "onMutate: () => setFrozen(describeEdits(proposal.ops, doc))" in card
    # A stale kept proposal (UX next Task 14) names nothing from the moved copy.
    assert "describeEdits(proposal.ops, stale ? null : resume)" in sheet
    for rel, src in (("card", card), ("sheet", sheet)):
        assert "<EditWordsList edits=" in src, rel
        assert "font-mono" not in src, rel
        assert "describeOp" not in src, rel
    assert "resume={live?.data}" in _read("components/resume-editor/editor-body.tsx")


_CARD = _read("components/chat/edit-proposal-card.tsx")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i : src.index(end, i)]


def test_resolved_words_freeze_and_a_failed_apply_thaws_them():
    # Discard freezes the words it showed: the card stops fetching the document.
    discard = _block(_CARD, "onClick={() => {", "Discard")
    assert 'setResolution("discarded")' in discard
    assert "setFrozen(edits);" in discard
    # A failed Apply unfreezes: the card is live again and must track the document.
    assert "setFrozen(null);" in _block(_CARD, "onError:", "},")


def test_the_words_list_is_prose_not_code():
    words = _read("components/edit-words-list.tsx")
    assert "<ul" in words
    assert not re.search(r"font-mono|<code|<pre", words)


# A bare baseResumeLabel(x) is a slug dressed as a name. Allowed only as the
# fallback half of `display_name ?? baseResumeLabel(x)` / `|| ...`, or with a list.
_BARE = re.compile(r"(?<!\?\? )(?<!\|\| )baseResumeLabel\([^,()]*\)")


def test_no_resume_is_named_by_its_slug():
    offenders = [
        f"{p.relative_to(_FRONTEND)}:{n}"
        for root in ("app", "components")
        for p in sorted((_FRONTEND / root).rglob("*.tsx"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _BARE.search(line)
    ]
    assert offenders == [], offenders


_HOOK = _read("hooks/use-base-resume-label.ts")


def test_the_name_hook_reads_the_list_with_archived_rows():
    assert '"/api/base-resumes?include_archived=true"' in _HOOK
    assert "baseResumeLabel(slug, data)" in _HOOK
    assert 'return ["base-resumes", { includeArchived }] as const;' in _HOOK
    for hook in ("useBaseResumeLabel", "useBaseResumeName"):
        body = _block(_HOOK, f"export function {hook}(", "\n}")
        assert "useBaseResumes(true)" in body, hook


def test_a_soft_deleted_resume_is_named_from_its_own_row():
    body = _block(_HOOK, "export function useBaseResumeName(", "\n}")
    # Same key as the studios' and the edit card's detail query.
    assert 'queryKey: ["base-resumes", slug]' in body
    # Only once the list has loaded WITHOUT the slug, and only when asked.
    assert "enabled: enabled && list.isSuccess && !listed," in body


# Every surface that names ONE résumé that may be soft-deleted goes through
# useBaseResumeName, so they all say the same thing.
_ONE_SLUG_SURFACES = {
    "components/chat/change-card.tsx": "useBaseResumeName(card.resume_key,",
    "components/chat/proposal-card.tsx": "useBaseResumeName(proposal.target_key,",
    "components/chat/edit-proposal-card.tsx": "useBaseResumeName(proposal.target_key,",
    "components/proposals/proposals-section.tsx": "useBaseResumeName(base ??",
    "components/application-panel.tsx": "useBaseResumeName(app.base_resume, open && !app.base_resume_name)",
}


def test_one_resume_surfaces_share_the_name_hook():
    missing = [rel for rel, call in _ONE_SLUG_SURFACES.items() if call not in _read(rel)]
    assert missing == [], missing
    assert "{baseName}" in _read("components/proposals/proposals-section.tsx")
    tracker = _read("app/applications/page.tsx")
    assert "r.app.base_resume_name || baseName(r.app.base_resume)" in tracker


def test_humanize_slug_names_no_resume():
    """The slug's words are a FALLBACK inside baseResumeLabel. The one other
    caller is the role picker's own fallback, for role keys."""
    callers = [
        f"{p.relative_to(_FRONTEND)}"
        for root in ("app", "components", "hooks")
        for p in sorted((_FRONTEND / root).rglob("*.ts*"))
        if "humanizeSlug(" in p.read_text(encoding="utf-8")
    ]
    assert callers == ["components/role-category-picker.tsx"], callers


def test_one_selectable_list_query():
    """The selectable-list fetch lives in one hook. Prefix invalidation of
    ["base-resumes"] stays at the call sites; that is not a second fetch."""
    hook = _read("hooks/use-base-resume-label.ts")
    assert "export function useBaseResumes(" in hook
    assert "apiFetch<BaseResumeSummary[]>" in hook
    callers = (
        "components/ats-score-panel.tsx",
        "components/chat/chat-page.tsx",
        "components/career/send-to-resume-dialog.tsx",
        "components/resume-editor/project-port-dialog.tsx",
        "app/base-resumes/page.tsx",
    )
    missing = [rel for rel in callers if "useBaseResumes(" not in _read(rel)]
    copies = [
        f"{p.relative_to(_FRONTEND)}"
        for root, pattern in (("app", "*.tsx"), ("components", "*.tsx"), ("hooks", "*.ts"))
        for p in sorted((_FRONTEND / root).rglob(pattern))
        if p.name != "use-base-resume-label.ts"
        and "apiFetch<BaseResumeSummary[]>" in p.read_text(encoding="utf-8")
    ]
    assert missing == [], missing
    assert copies == [], copies


# A job's role family is the catalog's label, never its key: the job page's
# chip read "Ai ml engineer" (the key title-cased) and the /new summary badge
# printed `ai_ml_engineer`. `useRoleLabel` falls back to the acronym-safe
# humanizer only while the catalog loads or for a key it lacks.
_FIELDS = _read("components/job-extracted-fields.tsx")
_SUMMARY = _read("components/job-extraction-summary.tsx")


def test_a_job_role_family_is_the_catalog_label():
    assert 'import { useRoleLabel } from "@/components/role-category-picker";' in _FIELDS
    assert "const roleLabelOf = useRoleLabel();" in _FIELDS
    assert '["Role family", job.role_category ? roleLabelOf(job.role_category) : null],' in _FIELDS
    assert "const roleLabelOf = useRoleLabel();" in _SUMMARY
    assert "<Badge variant=\"outline\">{roleLabelOf(job.role_category)}</Badge>" in _SUMMARY


def test_the_extraction_summary_prints_no_enum_key():
    # `full_time`, `on_site`: the same words the job page's chips use.
    assert 'import { humanizeEnum } from "@/components/job-extracted-fields";' in _SUMMARY
    for field in ("level", "employment_type", "work_mode"):
        assert f'<Badge variant="outline">{{humanizeEnum(job.{field})}}</Badge>' in _SUMMARY, field


_RAW_ROLE = re.compile(
    r"humanize(?:Enum|Slug)\([^)]*role_category|^\s*\{[\w.?]*role_category\}\s*$|>\{[\w.?]*role_category\}<",
    re.M,
)


def test_no_role_key_reaches_the_screen():
    offenders = [
        f"{p.relative_to(_FRONTEND)}: {m.group(0).strip()}"
        for root in ("app", "components")
        for p in sorted((_FRONTEND / root).rglob("*.tsx"))
        for m in _RAW_ROLE.finditer(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], offenders


# --- Task 19 (appendix D §4): resumes, studios, health, templates -----------


def test_a_bullet_label_is_singular_in_its_slot():
    # D10.8: the group label ("Bullets") named each row: "Bullets 2 of 5",
    # "Move bullets 2 up". Each row reads its own singular label.
    src = _read("components/resume-editor/bullet-list.tsx")
    assert 'label = "Bullets",' in src and 'itemLabel = "Bullet",' in src
    assert "aria-label={`${itemLabel} ${i + 1} of ${value.length}`}" in src
    for verb in ("Move ${itemLabel.toLowerCase()} ${i + 1} up", "Move ${itemLabel.toLowerCase()} ${i + 1} down",
                 "Delete ${itemLabel.toLowerCase()} ${i + 1}"):
        assert f"aria-label={{`{verb}`}}" in src, verb
    assert "${label} ${i + 1}" not in src
    assert "label.toLowerCase()" not in src.replace("itemLabel.toLowerCase()", "")


def test_new_base_summary_hint_matches_a_prefilled_field():
    # D10.5: the plan drafts the summary (base_from_kb_plan), so the field is
    # filled when it shows. "Left blank on purpose" was false.
    src = _read("components/base-resumes/new-base-resume-dialog.tsx")
    assert "Left blank on purpose" not in src
    assert "Check this summary, or clear it." in src


def test_undo_claims_match_version_history():
    # D10.10: both write a version first (stage_resume_update, and the saved
    # resume for a section delete), so "can't be undone" was false.
    studio = _read("components/resume-editor/tailored-resume-studio.tsx")
    start_over = _block(studio, 'title: "Start over from your base resume?"', "confirmLabel")
    extra = _read("components/resume-editor/extra-sections-editor.tsx")
    section_delete = _block(extra, "title: `Delete ${sectionName}?`", "confirmLabel")
    for name, confirm in (("start over", start_over), ("section delete", section_delete)):
        assert "can't be undone" not in confirm and "You can't undo this." not in confirm, name
        assert "Version history keeps" in confirm, name


def test_a_failed_save_names_places_not_schema_paths():
    # A studio Save names where the form failed ("Experience, item 3, bullet 1"),
    # never `experience.2.bullets.0`; the raw path stays in the code view only.
    for rel in ("components/resume-editor/editor-body.tsx", "components/resume-editor/tailored-resume-studio.tsx"):
        src = _read(rel)
        assert "throw new Error(fieldsNeedFixing(validated.error.issues.map((i) => i.path)));" in src, rel
        assert 'path.join(".")' not in src, rel
    assert 'i.path.join(".")' in _read("components/resume-editor/raw-json-toggle.tsx")
    words = _block(_DESCRIBER, "export function describeFieldPath(", "\n}")
    assert 'words.push(`${ROW_NOUN[parent] ?? "item"} ${seg + 1}`);' in words
    assert 'seg.replace(/_/g, " ")' in words
    assert 'extra_sections: "Other sections",' in _DESCRIBER
    assert "return `Some fields need fixing: ${shown}${more}.`;" in _DESCRIBER


def test_health_counts_agree_with_their_nouns():
    # D10.8: "3 Note", "1 Gate", "2 gate · 1 note". Every count chip and the
    # studio's health summary go through countWords.
    cards = _read("components/resume-health/finding-cards.tsx")
    assert '{ key: "ask", one: "question", many: "questions",' in _flat(cards)
    assert "const noun = meta ? (count === 1 ? meta.one : meta.many) : key;" in cards
    assert "{countWords(key, count)}" in _read("components/resume-health/health-report-page.tsx")
    badges = _read("components/resume-health/health-badges.tsx")
    assert "[countWords(key, count)]" in badges
    assert "${count} ${key}" not in badges


def _flat(src: str) -> str:
    return " ".join(src.split())


# --- Task 20 (appendix D §5): Career history --------------------------------


def test_an_item_without_org_or_dates_claims_nothing():
    # D10.7: a card with no organization and no dates read "Independent".
    card = _read("components/career/entity-card.tsx")
    assert '"Independent"' not in card
    assert "{entity.org || dateRange ? (" in card


def test_item_counts_agree_with_their_nouns():
    # D10.8: "1 points", "1 drafts", "1 docs". Each Metric takes both nouns.
    card = _read("components/career/entity-card.tsx")
    for bare in ('label="points"', 'label="drafts"', 'label="docs"'):
        assert bare not in card, bare
    assert 'one="bullet" many="bullets"' in card
    assert 'one="document" many="documents"' in card
    assert "{value} {value === 1 ? one : many}" in card


def test_add_files_names_what_it_opens():
    # D10.6: "Add documents" opened the upload dialog on its Resumes tab.
    # The dialog's own title is components/setup/upload-dialog.tsx (lane 9).
    page = _read("app/career/page.tsx")
    assert "Add documents" not in page
    assert '<Upload aria-hidden="true" /> Add files' in page
    assert "<UploadDialog open={importOpen} onOpenChange={setImportOpen} />" in page


# One table names every item kind and status, so a kind is never "Custom
# section" on one screen and "Other section" on the next, and a status never
# prints its stored key.
_KIND_TABLE_USERS = (
    "components/career/entity-card.tsx",
    "components/career/entity-detail.tsx",
    "components/career/new-entity-dialog.tsx",
    "components/career/merge-entity-dialog.tsx",
    "components/base-resumes/new-base-resume-dialog.tsx",
)


def test_career_kinds_and_statuses_have_one_table():
    labels = _read("components/career/career-labels.ts")
    assert 'extra: "Other section",' in labels
    assert ': "Unknown";' in labels
    for rel in _KIND_TABLE_USERS:
        src = _read(rel)
        assert "KB_KIND_LABELS[" in src, rel
        assert "custom section" not in src.lower(), rel
    assert "kbStatusLabel(entity.status)" in _read("components/resume-editor/kb-import-drawer.tsx")
    assert "kbStatusLabel(entity.status)" in _read("components/career/entity-card.tsx")


def test_the_studio_pill_adds_to_career_history():
    pill = _read("components/kb-sync-pill.tsx")
    assert "Add to career history ({count})" in pill
    assert "Sync to KB" not in pill.replace("// ", "")
