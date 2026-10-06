"""The visual language applied to real screens (visual-language plan, Wave 4). Each surface task adds its pins here."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


# --- Task 16: the knock-out check strip --------------------------------------------


def test_knockout_pass_is_quiet_and_conflict_is_loud():
    src = _read("components/job-knockout-card.tsx")
    assert "bg-success-container" not in src  # a pass is not a filled band any more
    assert "bg-error-container" in src  # a conflict is
    assert "SUMMARY_BY_RESULT" in src
    # Icons come from the register, never lucide directly.
    assert src.count('from "lucide-react"') == 1 and "import type { LucideIcon }" in src
    for concept in ("done", "fails", "warning", "unknown", "none", "notRun"):
        assert f"{concept}: " in src and "CONCEPT_ICONS" in src, concept
    for word in ("OK", "Conflict", "Warning", "Add answer", "Not listed", "Not run"):
        assert f'"{word}"' in src, word


def test_knockout_rows_use_their_result_icon():
    src = _read("components/job-knockout-card.tsx")
    assert "AlertTriangle" not in src
    # The detail rows draw the icon of the chip's own result, not a fixed glyph.
    assert "const Icon = SUMMARY_BY_RESULT[c.result].icon;" in src


def test_knockout_not_run_chip_says_its_action_to_a_screen_reader():
    src = _read("components/job-knockout-card.tsx")
    assert '<span className="sr-only">{` — ${hint}`}</span>' in src
    assert "hint={item.link}" in src
    assert "what:" not in src and "field:" not in src  # the dead Unchecked fields are gone


def test_knockout_chip_text_is_label_then_word():
    src = _read("components/job-knockout-card.tsx")
    assert "`${label}: ${word}`" in src
    for label in ("Work auth", "OPT", "Pay", "Experience", "On-site"):
        assert f'"{label}"' in src, label


def test_knockout_requirements_not_stated_is_a_minus_not_a_question():
    src = _read("components/job-knockout-card.tsx")
    assert "\"No requirements listed\"" in src
    # The Minus (register `none`) is the "No requirements listed" line's icon and the Not listed chip's.
    assert '<NoneIcon aria-hidden className="size-4" />, label: "No requirements listed"' in src
    assert 'job_unstated: { icon: NoneIcon, word: "Not listed"' in src
    assert src.count("NoneIcon") == 3  # destructure + chip + line, nowhere else
    assert src.count("UnknownIcon") == 3  # destructure, the profile_missing chip, the incomplete banner
    assert "That doesn't mean you qualify." in src  # the safety meaning rides in the line's accessible text


# --- Task 17: the job header's best score and locked tabs ---------------------------


def test_job_header_shows_the_best_score_and_locks_tabs_with_an_icon():
    src = _read("app/jobs/[id]/page.tsx")
    assert "ScoreBar" in src and "CONCEPT_ICONS.locked" in src
    assert 'id={lockedReasonId} className="sr-only"' in src  # still the triggers' aria-describedby target
    # The pill's visible words repeat the meter's aria-label ("Best score, <resume>").
    assert 'aria-hidden="true" className="text-muted-foreground">Best</span>' in src
    assert 'aria-hidden="true" className="text-muted-foreground truncate">{baseName(best.target_id)}' in src
    assert 'queryKey: ["ats-scores", id]' in src and '.filter((s) => s.phase === "base")' in src


# --- Task 18: score and tailor cards ---------------------------------------------------


def test_score_cards_hoist_shared_warnings_and_mark_the_weakest():
    src = _read("components/ats-score-panel.tsx")
    assert "sharedWarnings" in src and "Weakest" in src
    assert "ProgressCount" in src and "useCountUp" in src
    assert "> of 100<" not in src
    # A gate warning is a warning, on the card as in the hoisted banner: one role, one icon.
    gate = src.split("gateWarnings.map((warning) =>", 1)[1].split("</li>", 1)[0]
    assert "text-warning" in gate and "WarningIcon" in gate and "text-destructive" not in gate
    assert "CircleAlert" not in src and "const WarningIcon = CONCEPT_ICONS.warning;" in src
    # The meter's aria-label carries each subscore's name, so the visible label is hidden from readers.
    assert 'aria-hidden="true" className="text-muted-foreground text-body-small">{label}' in src


def test_score_card_subscores_and_coverage_are_meters():
    src = _read("components/ats-score-panel.tsx")
    assert 'label="Skills covered"' in src and "valueText={`${matched} of ${extracted}`}" in src
    assert "useCountUp(score.composite)" in src
    # The best match leads: two columns wide, its subscores in two.
    assert "@3xl:col-span-2" in src and "@3xl:grid-cols-2" in src
    # Update scores' spinner is the Button's own; timings live in lib/motion.ts.
    assert "pending={run.isPending}" in src
    assert 'className={run.isPending ? "animate-spin"' not in src
    assert not any(n in src for n in ("1200", "400", "200"))


# --- Task 19: gap analysis -------------------------------------------------------------

_GAP_PAGE = "app/jobs/[id]/tailor/[sessionId]/page.tsx"


def test_gap_actions_carry_icons_and_explain_once():
    rc = _read("components/gap-analysis/resolution-controls.tsx")
    assert "ACTION_ICONS" in rc and "ACTION_HINTS" in rc
    assert "user_input: CONCEPT_ICONS.you" in rc and "attach_project: CONCEPT_ICONS.project" in rc
    assert "port_kb_point: CONCEPT_ICONS.careerHistory" in rc
    # Selected: Check IN PLACE of the action icon, one leading glyph.
    segment = rc.split("export function ActionSegment", 1)[1].split("export function Chip", 1)[0]
    assert "value === action ? (\n" in segment and "<Check" in segment and "aria-describedby" in segment
    card = _read("components/gap-analysis/gap-card.tsx")
    assert card.count("{CANNOT_CONFIRM_EXPLANATION}") == 1  # the resolved row only
    assert "ACTION_ICONS[resolution.action]" in card
    # The auto-resolved row leads with the action's icon too; its provenance chip alone names the source.
    auto = card.split("isAutoResolved(resolution)) {", 1)[1].split("<ProvenanceCaption", 1)[0]
    assert "ACTION_ICONS[resolution.action]" in auto and "CareerHistoryIcon" not in auto
    assert "skip: CONCEPT_ICONS.skip" in rc and "SkipForward" not in rc
    assert "skip: SkipForward" in _read("lib/concept-icons.ts")
    # Hidden hint spans still resolve for aria-describedby; only referenced hints exist.
    assert "id={actionHintId(action)} hidden>" in rc and "enable_entry: \"Shows" not in rc
    assert "port_kb_point: \"Adds a point" not in rc
    page = _read(_GAP_PAGE)
    assert "SegmentedBar" in page and "These gaps need your input." not in page
    assert page.count("<ActionHints") == 1  # one hidden span per action, once per page
    assert "About these suggestions" in rc and "About this field" not in rc and "Pick one to use it." in rc


def test_gap_suggested_chip_says_suggested_and_is_quieter_than_selected():
    rc = _read("components/gap-analysis/resolution-controls.tsx")
    chip = rc.split("export function Chip", 1)[1].split("const LOAD_ERROR_MESSAGE", 1)[0]
    assert "Sparkles" not in rc
    assert "Suggested" in chip and "border-muted-foreground text-foreground" in chip and "border-primary" not in chip


def test_gap_provenance_and_points_are_chips():
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "ActorChip" in card and "DeltaChip" in card
    assert 'prefix="up to"' in card and "formatPotentialPoints" not in card
    review = _read("components/resume-editor/diff-review.tsx")
    assert "ActorChip" in review
    assert 'kind: "ai"' in review and 'kind: "careerHistory"' in review and 'kind: "you"' in review
    assert "assistant" not in review.split("function ProvenanceChip(", 1)[1].split("\n}", 1)[0]


def test_gap_categories_count_handled_and_a_resolving_card_collapses():
    page = _read(_GAP_PAGE)
    assert "{counts.answered + counts.skipped}/{counts.total}" in page
    assert "handled" in page and "text-success" in page
    card = _read("components/gap-analysis/gap-card.tsx")
    assert 'className="collapse-exit data-leaving:pointer-events-none"' in card
    assert "data-leaving={leaving || undefined}" in card and "}, ROW_EXIT_MS);" in card
    assert "200" not in card


# --- Task 20: health rows and the question pass -------------------------------------


def test_health_rows_draw_the_evidence_ladder_and_priority_chip():
    src = _read("components/resume-health/finding-cards.tsx")
    assert "DotMeter" in src and "ChevronsUp" in src and "DeltaChip" in src
    assert "EVIDENCE_LEVELS.length - at" in src
    # An unknown level has no place on the ladder: the word alone, never a full meter.
    assert "if (at < 0) return <span" in src
    assert "bg-secondary-container" in src and "text-on-secondary-container" in src
    assert "Up to +" not in src
    assert "CONCEPT_ICONS.health" in _read("components/resume-health/health-badges.tsx")
    assert "ProgressCount" in _read("components/resume-health/question-pass.tsx")


def test_question_pass_rows_are_glyph_and_word_and_the_footer_has_a_bar():
    src = _read("components/resume-health/question-pass.tsx")
    for icon in ("NotRunIcon", "Loader2", "CircleX", "SkipIcon", "DraftsIcon", "Minus"):
        assert icon in src, icon
    assert "Clock" not in src and "SkipForward" not in src
    assert "CONCEPT_ICONS.notRun" in src and "CONCEPT_ICONS.skip" in src and "CONCEPT_ICONS.drafts" in src
    # "New wording ready" still needs the user's review: drafts, not a green done check.
    assert "CircleCheck" not in src and "text-success" not in src
    assert "animate-spin" in src
    # The count sits BESIDE the live words, not inside the polite region.
    assert '<p aria-live="polite">{progress.words}</p>' in src
    assert "<ProgressCount" in src and "showText={false}" in src


def test_preview_thumbnail_shows_a_skeleton_until_the_image_loads():
    src = _read("components/gallery/preview-thumbnail.tsx")
    assert "<Skeleton" in src and "onLoad" in src and "onError" in src and "No PDF yet" not in src
    # A cached image settles before hydration: handle its cached failure as well as its cached success.
    assert "else setFailedSrc(src)" in src and "img.naturalWidth > 0" in src


def test_analytics_draws_status_mix_and_trend():
    src = _read("components/analytics/analytics-overview.tsx")
    assert "SegmentedBar" in src and "Sparkline" in src
    assert 'name="Applications by status"' in src and "ScoreBar" in src
    assert 'label="Applied per day, last 28 days"' in src
    assert "bg-primary/10" not in _read("components/analytics/agent-pipeline-card.tsx")
    assert "bg-primary h-full rounded-full" in _read("components/analytics/agent-pipeline-card.tsx")
