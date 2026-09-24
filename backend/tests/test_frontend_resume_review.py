"""Lane 8 (Tasks 19-20) review and first-read fixes: resumes, health, templates, Career history.

Every sentence tells the truth, the honesty and can't-undo nuance survives every cut, one request per
click, and focus never falls to <body>. The pure helpers these screens word themselves with are
node-tested (`lib/*.test.ts`); these pins hold the screens to them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services import template_validation

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _flat(src: str) -> str:
    return " ".join(src.split())


def _block(src: str, start: str, end: str) -> str:
    at = src.index(start)
    return src[at : src.index(end, at)]


def _element(src: str, marker: str, tag: str = "<Button") -> str:
    """The `tag` element around `marker`, from its opening to its close."""
    at = src.index(marker)
    close = "/>" if tag in ("<IconButton", "<Input") else "</Button>"
    return src[src.rfind(tag, 0, at) : src.index(close, at)]


# --- Consequences survive (Goal Card: honesty and can't-undo nuance) --------

_CONSEQUENCES = [
    # M2: a base resume's delete says it is gone for good.
    ("app/base-resumes/page.tsx", "This removes the resume from your base resumes. You can&apos;t undo this."),
    # M4: a section delete says how to get it back.
    ("components/resume-editor/extra-sections-editor.tsx",
     "Version history keeps your saved versions, so you can restore it."),
    # M5: adding from career history can be undone.
    ("components/resume-editor/kb-import-drawer.tsx",
     "Choose the bullets to add. You can undo this from Version history."),
    # M9, M10: merging and deleting an item can't be undone.
    ("components/career/merge-entity-dialog.tsx", "is deleted. You can't undo this."),
    ("components/career/entity-detail.tsx", "its bullets and documents. You can't undo this."),
    # M11: a deleted bullet leaves resumes alone.
    ("components/career/points-list.tsx", "Resumes that used it keep their text."),
    # M12: nothing reaches a resume before you approve it.
    ("components/career/capture-box.tsx", "Nothing goes on a resume until you approve it."),
    # M13: marking a check OK changes the score only, and can be undone.
    ("components/resume-health/finding-cards.tsx",
     "Your resume isn&apos;t changed. You can undo this here."),
    # M14: a new base resume never rewrites your bullets.
    ("components/base-resumes/new-base-resume-dialog.tsx", "Your bullets are never rewritten."),
    # M16: asking for changes never invents facts.
    ("components/resume-editor/instruct-sheet.tsx",
     "AI won&apos;t add facts that aren&apos;t on your resume."),
    # M19: Add as is copies exactly.
    ("components/career/send-to-resume-dialog.tsx",
     "Adapt rewrites them to fit it. Add as is copies them exactly."),
    # M23 (review I3): Start over names every loss and where the saved copy is.
    ("components/resume-editor/tailored-resume-studio.tsx",
     "This replaces the tailored resume with a fresh copy of your base resume, removes its PDF and drops "
     "unsaved edits. Version history keeps the saved version."),
    # M24: Load latest drops unsaved edits for good.
    ("components/resume-editor/tailored-resume-studio.tsx",
     "Your unsaved edits will be lost. You can't undo this."),
    # M25: the fatal tier is the only "must fix".
    ("components/resume-health/finding-cards.tsx", '{ key: "gate", one: "must fix", many: "must fix",'),
    # M20: the pill's toast counts what it added from every count the server returns.
    ("components/kb-sync-pill.tsx", "{syncResultSentence(result)}"),
]


@pytest.mark.parametrize(("rel", "sentence"), _CONSEQUENCES, ids=[f"{r}:{s[:28]}" for r, s in _CONSEQUENCES])
def test_consequence_sentences_survive(rel: str, sentence: str):
    assert _flat(sentence) in _flat(_read(rel))


# --- C1: a template missing only TeX needs setup, it has no errors ----------

def test_the_tex_reason_is_the_servers():
    assert f'export const REQUIRES_TEX_REASON = "{template_validation.REQUIRES_TEX}";' in _read("lib/template-status.ts")


def test_a_template_missing_only_tex_says_needs_setup_only():
    gallery = _read("components/templates/template-gallery.tsx")
    has_errors = _block(gallery, "Has errors. Open to fix.", "</p>")
    guard = gallery[gallery.rindex("{", 0, gallery.index(has_errors)) : gallery.index(has_errors)]
    assert "templateHasErrors(template)" in guard and "template.last_error" not in guard
    fn = _block(_read("lib/template-status.ts"), "export function templateHasErrors(", "\n}")
    assert "last_error !== REQUIRES_TEX_REASON" in fn
    # The editor says the same: no "The template has an error" for a missing TeX.
    editor = _read("app/templates/[id]/page.tsx")
    assert "compileError === REQUIRES_TEX_REASON" in editor
    assert "res.error === REQUIRES_TEX_REASON" in editor


def test_the_needs_setup_tooltip_names_the_real_fallback():
    # pdf_render.resolve_render_template: the first ready Typst template, else no PDF.
    badge = _flat(_read("components/templates/requires-tex-badge.tsx"))
    assert "a similar template" not in badge
    assert "made with another ready template that doesn&apos;t need TeX" in badge or (
        "made with another ready template that doesn't need TeX" in badge
    )


# --- I1, I2: the studio pill -------------------------------------------------


def test_the_pill_says_what_is_ready_and_what_it_added():
    pill = _read("components/kb-sync-pill.tsx")
    assert "Ready to add to your career history" in pill
    assert "Not yet in your career history" not in pill
    assert "Added {created} new" not in pill
    assert "syncBreakdownLines(status)" in pill
    words = _read("lib/kb-sync-words.ts")
    fn = _block(words, "export function syncResultSentence(", "\n}")
    assert "result.items_added" in fn and "result.skills_added.length" in fn and "result.drifted" in fn


def test_the_pill_add_now_keeps_focus_while_it_runs():
    pill = _read("components/kb-sync-pill.tsx")
    add = _element(pill, "onClick={() => syncOnce()}")
    assert "focusableWhenDisabled" in add and "data-disabled:opacity-50" in add


def test_the_sync_result_type_carries_the_item_count():
    types = _read("lib/types.ts")
    block = types[types.index("export interface SyncResult") :]
    assert "items_added: number;" in block[: block.index("\n}")]


# --- I4: the career profile says what it feeds ------------------------------


def test_the_profile_says_what_starts_from_it():
    panel = _read("components/career/profile-panel.tsx")
    line = "Your contact details and skills. Resumes built from your career history start from these."
    assert panel.count(line) == 2
    assert "shared by all your resumes" not in panel


# --- I5: a retired bullet ------------------------------------------------------


def test_a_retired_bullet_is_not_used_and_says_what_that_means():
    points = _read("components/career/points-list.tsx")
    assert 'label: "Not used",' in points
    stop = _block(points, 'approved: {\n    label: "Stop using",', "},")
    assert 'hint: "Stop offering this bullet. Resumes that have it keep it."' in stop
    assert 'retired: "Won\'t be offered again",' in points
    assert '"Using this bullet again"' in points
    assert "Bullet no longer used" not in points and '"Bullet restored"' not in points
    # A retired bullet still sitting on resumes says "Still on", never plain "On".
    assert 'point.state === "retired" ? "Still on" : "On"' in points


# --- I6, item 14: fields in the user's words --------------------------------

_DESCRIBER = _read("lib/describe-edit.ts")
# Every editor that labels a resume field.
_EDITORS = [
    "components/resume-editor/contact-form.tsx",
    "components/resume-editor/experience-editor.tsx",
    "components/resume-editor/project-editor.tsx",
    "components/resume-editor/education-editor.tsx",
    "components/resume-editor/skills-editor.tsx",
    "components/resume-editor/extra-sections-editor.tsx",
]


def test_field_words_are_the_labels_on_screen():
    table = _block(_DESCRIBER, "const FIELD_WORDS: Record<string, string> = {", "};")
    pairs = re.findall(r'^\s+(\w+): "([^"]+)",$', table, re.M)
    assert len(pairs) >= 20
    screens = "\n".join(_read(rel) for rel in _EDITORS)
    for key, word in pairs:
        shown = (f'label="{word}"', f'label: "{word}"', f">{word}</Label>", f'aria-label="{word}"')
        assert any(s in screens for s in shown), (key, word)
    for key, word in (("institution", "School"), ("category", "Group name"), ("tech", "Tools used"),
                      ("gpa", "GPA"), ("linkedin", "LinkedIn"), ("github", "GitHub")):
        assert (key, word) in pairs, key
    fn = _block(_DESCRIBER, "export function describeFieldPath(", "\n}")
    assert 'FIELD_WORDS[seg] ?? seg.replace(/_/g, " ")' in fn


def test_the_code_view_names_fields_and_lines_not_paths():
    raw = _read("components/resume-editor/raw-json-toggle.tsx")
    assert 'path.join(".")' not in raw
    assert "setError(schemaIssuesWords(result.error.issues));" in raw
    assert "setError(jsonErrorWords(text, e));" in raw
    assert "(e as Error).message" not in raw
    fn = _block(_DESCRIBER, "export function jsonErrorWords(", "\n}")
    assert "Check for a missing comma or quote." in fn


# --- I7: one "must fix" count everywhere --------------------------------------


def test_must_fix_counts_only_failed_fatal_checks():
    report = _read("lib/health-report.ts")
    fn = _block(report, "export function healthCounts(", "\n}\n")
    assert 'g.tier === "fatal"' in fn and 'g.status === "fail"' in fn
    line = _block(report, "export function scoreCompositionLine(", "\n}")
    assert "one must-fix problem" not in line
    cards = _read("components/resume-health/finding-cards.tsx")
    assert '<h2 className="text-sm font-medium">Checks</h2>' in cards
    assert '{ key: "serious", one: "serious problem", many: "serious problems",' in _flat(cards)
    group = _block(_read("components/resume-editor/diff-review.tsx"), "function GatesGroup(", "\n}")
    assert ">\n        Checks\n      </p>" in group and ">\n        Must fix\n" not in group


def test_every_health_surface_says_the_same_count():
    page = _read("components/resume-health/health-report-page.tsx")
    assert "const counts = body ? healthCounts(body) : {};" in page
    assert "body.counts?.[key]" not in page
    assert '{ id: "gates", label: "Checks"' in page
    assert "leftToFix(counts, nonNote.length)" in page
    assert "checkDoneWords(result)" in page and "Check done. Grade ${result.grade}." not in page
    assert "scoreCompositionLine(body.score, body.score_breakdown, gates)" in page
    assert "summarizeCounts(healthCounts(data))" in _read("components/resume-health/health-badges.tsx")


# --- I8: a document says what reading it did --------------------------------


def test_a_document_says_what_reading_it_did():
    panel = _read("components/career/documents-panel.tsx")
    assert "documentAddedWords(document, drafted)" in panel
    assert "documentReadAgainWords(document, drafted)" in panel
    assert "documentStatusLabel(document)" in panel
    assert "New bullets are ready to review." not in panel
    words = _read("lib/document-words.ts")
    assert "Document added. Couldn't suggest bullets from it. Try Read again." in words
    assert '"Couldn\'t suggest bullets"' in words
    assert "has_text: boolean;" in _block(_read("lib/types.ts"), "export interface KBDocumentOut", "\n}")


# --- Minor copy (item 9) -------------------------------------------------------


def test_deleting_an_archived_resume_offers_no_archive():
    page = _flat(_read("app/base-resumes/page.tsx"))
    assert "This deletes the resume and its PDF." not in page
    assert '{deleteTarget?.archived_at ? null : " To keep it out of the way instead, archive it."}' in page


def test_the_template_picker_says_which_templates_are_archived():
    select = _read("components/templates/template-select.tsx")
    assert '"All ready templates are archived. Restore one on the Templates page."' in select
    assert "`${defaultTemplate.display_name} (default)`" in select


def test_the_unreadable_tailored_resume_names_its_button():
    studio = _flat(_read("components/resume-editor/tailored-resume-studio.tsx"))
    assert "This tailored resume couldn&apos;t be opened. Choose Create draft to start again from your base resume." in studio


def test_bullet_origins_are_true_and_said_once():
    points = _read("components/career/points-list.tsx")
    assert 'user_authored: "From your own material",' in points
    assert 'user_cannot_confirm: "You couldn\'t confirm this",' in points
    assert '"You wrote it"' not in points
    fn = _block(points, "function originLabel(", "\n}")
    assert "`From ${agent}`" in fn and "agentDisplayName(point.origin_detail)" in fn
    assert 'point.origin === "manual" && point.provenance === "user_stated"' in points


def test_resume_usage_names_tailored_resumes_by_their_job():
    points = _read("components/career/points-list.tsx")
    assert "useResumeKeyLabel(usageKeys)" in points and "useBaseResumeLabel()" not in points
    hook = _read("components/career/use-resume-key-label.ts")
    assert 'queryKey: ["applications"]' in hook
    assert 'return job ? `Tailored resume for ${job}` : "A tailored resume";' in hook


def test_other_sections_add_item_names_its_subheading():
    dialog = _read("components/career/new-entity-dialog.tsx")
    org = _block(dialog, "const ORG_LABELS: Record<KBEntityKind, string> = {", "};")
    assert 'extra: "Subheading",' in org and 'certification: "Issued by",' in org


def test_update_pdf_is_pending_as_updating():
    studio = _read("lib/studio.ts")
    fn = _block(studio, "export function pdfActionWords(", "\n}")
    assert '"Updating…"' in fn and '"update the PDF"' in fn and '"create the PDF"' in fn
    for rel in ("components/resume-editor/editor-body.tsx", "components/resume-editor/tailored-resume-studio.tsx"):
        src = _read(rel)
        assert "pdfActionWords(" in src, rel
        assert '"Creating…"\n' not in src.replace(" ", ""), rel


def test_item_statuses_come_from_the_one_table():
    detail = _read("components/career/entity-detail.tsx")
    table = _block(detail, "const STATUSES:", "];")
    assert "label: KB_STATUS_LABELS." in table
    assert 'label: "Ongoing"' not in table


def test_the_project_fields_line_up():
    project = _read("components/resume-editor/project-editor.tsx")
    assert '<div className="grid grid-cols-2 gap-3 sm:items-end">' in project


def test_health_copy_first_read():
    # The zone orders the fix list and sets severity; it never weights the score (health_score).
    assert 'ATTENTION_BADGE_LABEL = "Higher priority";' in _read("components/attention-zone.tsx")
    page = _read("components/resume-health/health-report-page.tsx")
    assert "addNumbersLabel(metricAsks.length)" in page and "number questions" not in page
    assert "` · Version ${body.resume_version_number}`" in page
    assert "number questions" not in _read("components/resume-health/batch-ask-dialog.tsx")
    cards = _read("components/resume-health/finding-cards.tsx")
    assert "This rating is wrong…" in cards and ">\n            Change rating\n" not in cards


def test_career_copy_first_read():
    kb = _read("components/career/inbox-panel.tsx")
    assert "New bullets wait here as drafts until you approve them." in kb
    assert "Check AI-written bullets" not in kb
    labels = _read("lib/extra-sections.ts")
    # "Items", not the first read's "Entries": the glossary says item, never entry.
    assert 'entries: "Items with dates",' in labels and 'bullets: "Simple list",' in labels
    drawer = _read("components/resume-editor/kb-import-drawer.tsx")
    assert "unapproved" not in drawer and "bulletsAdded" in drawer
    assert '{entity.draft_count === 1 ? "draft bullet" : "draft bullets"} not shown' in drawer
    assert "Update file" in _read("components/career/exports-card.tsx")


def test_studio_copy_first_read():
    studio = _read("components/resume-editor/tailored-resume-studio.tsx")
    assert "This tailored resume was changed somewhere else." in studio
    assert "This draft changed outside the editor." not in studio
    assert "how an applicant tracking system rates this resume for the job" in studio
    body = _read("components/resume-editor/editor-body.tsx")
    assert "Copy resume ID" not in body and "Copy ID for connected agents" in body


def test_versions_and_review_copy_first_read():
    versions = _read("components/resume-versions/version-history-sheet.tsx")
    assert "versionSummaryWords(v.summary)" in versions
    assert "Restored as Version ${created.version_number}" in versions
    assert "diffChangeWords(c)" in _read("components/resume-versions/version-diff-view.tsx")
    review = _read("components/resume-editor/diff-review.tsx")
    assert "value === \"llm\"" in _block(review, "function ProvenanceChip(", "\n}")


def test_formatting_units_are_spelled_out():
    formatting = _read("components/resume-editor/formatting-panel.tsx")
    assert "`${n}pt`" not in formatting and "in`" not in formatting
    assert "pointsLabel" in formatting and "inchLabel" in formatting


def test_template_and_new_resume_copy_first_read():
    assert "may read some words as joined together" in _read("components/templates/template-gallery.tsx")
    templates = _read("app/templates/page.tsx")
    assert "Used in this template&apos;s web address and by connected agents." in templates
    nbr = _read("components/base-resumes/new-base-resume-dialog.tsx")
    assert "createBlockedReason" in nbr and "aria-describedby={blocked ? ids.blocked : undefined}" in nbr
    assert "e.point_count - e.draft_count" in nbr


# --- Item 11: one request per click, focus kept while working ---------------

_KEEP_FOCUS = [
    ("components/resume-health/finding-cards.tsx", "onClick={() => waiveOnce()}"),
    ("components/resume-health/finding-cards.tsx", "onClick={() => unwaiveOnce()}"),
    ("components/resume-health/finding-cards.tsx", "onClick={() => draftOnce()}"),
    ("components/resume-health/health-report-page.tsx", "onClick={() => analyzeOnce()}"),
    ("components/resume-editor/tailored-resume-studio.tsx", "onClick={() => rescoreOnce({ announce: true })}"),
    ("components/career/inbox-panel.tsx", 'data-draft-action="approve"'),
    ("components/career/inbox-panel.tsx", 'data-draft-action="discard"'),
    ("components/career/points-list.tsx", "onClick={() => changeState(action.to)}"),
    ("components/career/merge-entity-dialog.tsx", "onClick={() => mergeOnce(picked)}"),
    ("components/resume-editor/kb-import-drawer.tsx", "onClick={() => importOnce()}"),
    ("app/templates/[id]/page.tsx", "onClick={() => recompileOnce()}"),
]


@pytest.mark.parametrize(("rel", "marker"), _KEEP_FOCUS, ids=[m[:32] for _, m in _KEEP_FOCUS])
def test_a_button_that_works_keeps_focus_while_it_runs(rel: str, marker: str):
    button = _element(_read(rel), marker)
    assert "focusableWhenDisabled" in button, marker
    assert "data-disabled:opacity-50" in button, marker


# --- Item 12: focus never to <body> -----------------------------------------


def test_restoring_a_version_hands_focus_to_the_restored_version():
    sheet = _read("components/resume-versions/version-history-sheet.tsx")
    assert "landOn.current = created.version_number;" in sheet
    assert "row.focus({ preventScroll: true })" in sheet and "data-version={v.version_number}" in sheet


def test_marking_a_check_ok_moves_focus_to_what_replaced_the_button():
    cards = _read("components/resume-health/finding-cards.tsx")
    failed = _block(cards, "function FailedGate(", "\nfunction WaivedGate(")
    # "Mark as OK…" opens the reason box with focus in it, and Cancel returns.
    assert "useEditToggle<HTMLDivElement>()" in failed
    assert "ref={editRef}" in failed and "ref={openerRef}" in failed
    # A waived check lands on its Undo, an undone one on its Mark as OK….
    banner = _block(cards, "export function GateBanner(", "\n}\n")
    assert "const [landOn, setLandOn] = useState<string | null>(null);" in banner
    assert banner.count("land={landOn === gate.id}") == 3
    assert "useLandFocus(land, openerRef);" in failed
    land = _block(cards, "function useLandFocus(", "\n}")
    assert "if (land) focusIfDropped(actionRef.current);" in land
    assert "const actionRef = useLandFocus(land);" in _block(cards, "function WaivedGate(", "\nfunction NotAssessedGate(")


def test_answer_and_review_hand_focus_into_the_opened_card():
    cards = _read("components/resume-health/finding-cards.tsx")
    for card in ("export function FixCard(", "export function AskCard("):
        body = _block(cards, card, "\n}\n")
        assert "focusNext(cardRef);" in body, card
        assert "ref={cardRef}" in body, card
    ask = _block(cards, "export function AskCard(", "\n}\n")
    assert "onSuccess: (result) => {\n      setLocalSuggestion(result.suggestion);\n      focusNext(cardRef);" in ask


def test_checking_again_keeps_focus_on_a_check_button():
    page = _read("components/resume-health/health-report-page.tsx")
    assert page.count("<FocusHandoff to={checkRef}") == 3
    assert "{analyzeButton(checkRef)}" in page


def test_update_score_keeps_its_one_guard():
    studio = _read("components/resume-editor/tailored-resume-studio.tsx")
    assert "const rescoreOnce = useSingleFlight(rescore.mutate);" in studio
    assert "rescoreOnce({ announce: false });" in studio


def test_an_approved_or_discarded_draft_hands_focus_to_the_next_draft():
    inbox = _read("components/career/inbox-panel.tsx")
    # On the row's way out (a layout cleanup, while it is still attached), so a
    # re-render that lands after the request settles can't strand the focus.
    handoff = _block(inbox, "useLayoutEffect(() => {\n    const row = articleRef.current;", "}, []);")
    assert "const next = draftSuccessor(row, \"approve\");" in handoff
    assert "queueMicrotask(() => focusIfDropped(next()));" in handoff
    assert '<Card id="inbox" tabIndex={-1}' in inbox


def test_a_bullet_state_change_keeps_focus_on_its_one_action():
    points = _read("components/career/points-list.tsx")
    assert "const action = STATE_ACTIONS[point.state];" in points
    assert "focusIfDropped(actionRef.current);" in points


def test_merging_hands_focus_to_the_surviving_item():
    merge = _read("components/career/merge-entity-dialog.tsx")
    assert "survivor.current = target.id;" in merge
    assert "finalFocus={() =>" in merge and 'a[href="/career/${id}"]' in merge


def test_update_preview_keeps_focus():
    editor = _read("app/templates/[id]/page.tsx")
    assert "const recompileOnce = useSingleFlight(recompileM.mutate);" in editor


# --- Item 13: no horizontal scroll at 375 -------------------------------------


def test_finding_rows_wrap_inside_their_cards():
    cards = _read("components/resume-health/finding-cards.tsx")
    row = _block(cards, "function CollapsedRow(", "\nexport function FindingGroupHeader(")
    assert '<div className="flex min-w-0 flex-wrap items-start gap-2">' in row
    assert '<span className="flex min-w-0 flex-wrap items-center gap-1.5">' in row
    chrome = _block(cards, "export function ExpandedFindingChrome(", "\nfunction ClassificationOverrideDialog(")
    assert "whitespace-normal" in chrome and "flex-wrap" in chrome


# --- Item 14: the number question starts empty ------------------------------


def test_the_number_question_starts_with_no_unit():
    metric = _read("components/resume-health/metric-ask-input.tsx")
    empty = _block(metric, "export function emptyMetricAsk(", "\n}")
    assert 'unit: "",' in empty and '"users"' not in empty
    ctx = _block(metric, "export function metricContextFromValue(", "\n}")
    assert 'if (!value.unit) return "";' in ctx


def test_career_history_fits_375():
    # An auto grid track grew to its cards' min-content (317px in a 271px
    # column): /career scrolled sideways at 375 (scrollWidth 397).
    capture = _read("components/career/capture-box.tsx")
    assert '<div className="flex flex-wrap items-center gap-2">' in capture
    # The page's one column may shrink below its content's widest line.
    assert '<div className="grid grid-cols-[minmax(0,1fr)] gap-6">' in _read("app/career/page.tsx")
