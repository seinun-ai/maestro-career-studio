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
    assert '["Role", job.role_category ? roleLabelOf(job.role_category) : null],' in _FIELDS
    assert "const roleLabelOf = useRoleLabel();" in _SUMMARY
    assert "<Badge variant=\"outline\">{roleLabelOf(job.role_category)}</Badge>" in _SUMMARY


def test_the_extraction_summary_prints_no_enum_key():
    # `full_time`, `onsite`: the same words the job page's chips use.
    assert 'import { humanizeEnum } from "@/components/job-extracted-fields";' in _SUMMARY
    for field in ("level", "employment_type", "work_mode"):
        assert f'<Badge variant="outline">{{humanizeEnum(job.{field})}}</Badge>' in _SUMMARY, field
    # The map keys the STORED value: `on_site` never matched, so every on-site
    # job read "Onsite" (appendix D10.4).
    assert 'onsite: "On-site"' in _FIELDS
    assert "on_site:" not in _FIELDS


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


# Jobs and tracking (plan Task 17, appendix D §2). Node tests cover
# lib/format-date.ts and lib/ats-words.ts; they are not in CI, so the branches
# that matter are pinned here too.


def test_analytics_never_calls_the_top_skills_mandatory():
    """D10.3: the top 30% is a cut by how many jobs ask, not a requirement."""
    assert "mandatory" not in _read("app/analytics/page.tsx").lower()
    chart = _read("components/charts/top-skills-chart.tsx")
    assert 'subtitle="Mandatory"' not in chart
    assert 'subtitle="Most asked for"' in chart


def test_status_maps_never_print_a_key():
    chip = _read("components/status-chip.tsx")
    assert chip.count('?? "Unknown"') == 2
    assert "?? status;" not in chip


def test_a_day_reads_as_words_and_never_shifts():
    lib = _read("lib/format-date.ts")
    # A date-only value is a calendar day: `new Date("2026-09-14")` is UTC
    # midnight, which read as Sep 13 west of Greenwich.
    assert "const DAY_ONLY = /^(\\d{4})-(\\d{2})-(\\d{2})$/;" in lib
    assert "new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]))" in lib
    assert "date.getFullYear() === now.getFullYear() ? {} : { year: \"numeric\" }" in lib
    assert not re.search(r"^import ", lib, re.M)
    tracker = _read("app/applications/page.tsx")
    assert 'return (value && formatShortDate(value)) || "—";' in tracker
    assert ".slice(0, 10)" not in tracker
    assert "tickFormatter={(value: string) => formatShortDate(value)}" in _read(
        "components/analytics/activity-chart.tsx"
    )
    assert "`Since ${formatShortDate(o.meta.since)}`" in _read("components/explore/explore-overview.tsx")


def test_ats_keys_have_one_set_of_words():
    words = _read("lib/ats-words.ts")
    for pair in ('experience_only: "Experience"', 'mirror_wording: "Use the job\'s words"',
                 'placement_recency", label: "Recent experience"', 'mentioned: "Mentioned"'):
        assert pair in words, pair
    assert not re.search(r"^import ", words, re.M)
    compare = _read("components/ats-compare-panel.tsx")
    assert "placementLabel(row.placement) : fixHintLabel(row.fix_hint)" in compare
    for raw in ("{row.placement}", "{row.fix_hint}", "const SUBSCORE_LABELS"):
        assert raw not in compare, raw
    assert "const SUBSCORE_LABELS" not in _read("components/ats-score-panel.tsx")


def test_the_score_tab_spells_out_the_ats_score():
    panel = _read("components/ats-score-panel.tsx")
    assert "{ATS_SCORE_LEAD}" in panel
    # Above the cards, and in the empty state: wherever the tab first shows a score.
    assert panel.count("<AtsScoreLead />") == 2


def test_a_skip_reason_reads_as_words():
    triage = _read("components/proposals/triage-actions.tsx")
    assert '"declined by user": "Not interested",' in triage
    assert ': "skipped by you"' not in triage
    panel = _read("components/proposals/proposal-agent-panel.tsx")
    assert '<Fact label="Reason">{reasonLabel(data.reason)}</Fact>' in panel


def test_job_market_bars_and_filters_print_words():
    market = _read("components/explore/explore-overview.tsx")
    for field in ("o.work_mode", "o.level_breakdown", "o.work_auth.opt", "o.work_auth.sponsorship"):
        assert f"toEnumBars({field})" in market, field
    page = _read("app/analytics/page.tsx")
    assert '{filterSelect("level", "Level", level, setLevel, options.levels, enumLabel)}' in page
    assert '"Employment type",' in page and "options.employment,\n        enumLabel," in page


def test_the_pipeline_card_says_the_cap_as_the_inbox_does():
    pipeline = _read("components/analytics/agent-pipeline-card.tsx")
    assert '<CapToday className="text-muted-foreground mt-0" />' in pipeline
    assert "remaining" not in pipeline


def test_autofill_coverage_names_field_kinds_in_words():
    card = _read("components/analytics/autofill-coverage-card.tsx")
    # The chart's rows carry the word (the tooltip reads it back); the table maps its own.
    assert "kind: kindLabel(kind.kind)," in card
    assert "{kindLabel(row.kind)}" in card
    assert card.count("{row.kind}") == 1  # RateTooltip, on a row already mapped


# The gap page (plan Task 18, appendix D §3).
_GAP_PAGE = "app/jobs/[id]/tailor/[sessionId]/page.tsx"


def test_the_gap_page_still_matches_the_server_quick_tailor_answer():
    # The one string code compares: D §9 keeps the server's "No actionable
    # resolutions to tailor" because this line reads it to pick its own words.
    page = _read(_GAP_PAGE)
    assert 'error.message === "No actionable resolutions to tailor"' in page
    assert '"Quick tailor had nothing to add here. Answer a gap yourself, or use your resume as is."' in page


def test_tailoring_notes_have_a_label_a_hint_and_no_placeholder():
    page = _read(_GAP_PAGE)
    notes = page[page.index('<Label htmlFor="tailor-instructions"') : page.index("rows={3}")]
    assert "optional>" in notes and "Tailoring notes" in notes
    assert "<p id={notesHintId}" in notes and "What to stress, or limits like page count." in notes
    assert "aria-describedby={notesHintId}" in notes
    assert "placeholder=" not in page
    assert "const notesHintId = useId();" in page


def test_the_honesty_warning_keeps_every_clause():
    """inv-honesty's screen half: shorter, but it still says the resume does
    not show the skill, to add it only if true, and that recruiters may ask."""
    controls = _read("components/gap-analysis/resolution-controls.tsx")
    assert (
        '"Your resume doesn\'t show this skill. Add it only if you have it. Recruiters may ask."'
        in controls
    )
    assert "{UNVERIFIED_WARNING}" in controls
    # cannot_confirm keeps its "never used" promise in plain words.
    assert '"We won\'t ask again, and it won\'t go on your resume."' in controls


def test_the_gap_page_says_done_and_gap_analysis():
    page = _read(_GAP_PAGE)
    assert '? "Not saved"' in page
    assert "Save failed" not in page
    assert "</span> answered\n" in page
    assert "gaps addressed" not in page
    assert "This gap analysis is out of date because {staleReason}." in page


def test_gap_cards_print_no_engine_key():
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "placementLabel(diagnostic.placement)" in card
    assert "title tier:" not in card
    assert "match_form}" not in card
    assert "{requirementLabel(gap.requirement_level)}" in card


def test_longer_words_wrap_instead_of_squeezing():
    """Browser-found at 375: the plainer words are longer. The gap page footer
    squeezed its counts into a column, and the compare card's title ran one
    word per line beside Update score."""
    page = _read(_GAP_PAGE)
    assert 'className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-x-3 gap-y-2"' in page
    assert "shrink-0 text-sm whitespace-nowrap tabular-nums" in page
    compare = _read("components/ats-compare-panel.tsx")
    assert 'CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-2"' in compare
