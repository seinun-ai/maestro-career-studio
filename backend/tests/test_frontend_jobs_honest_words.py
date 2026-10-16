"""Jobs, tracking and the gap page say only what is true (IA wave 3, lane 7 review).

Appendix D rewrote several sentences into claims the code does not back: a
knock-out "clear" that has warnings, "No requirements listed" on a job that
lists pay, Quick tailor filling "every" gap. Each pin reads the sentence and,
where the truth lives in the backend, the backend fact it rests on. Node tests
cover the `lib/` helpers but are not in CI, so their branches are pinned here.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest

from app.schemas.job_extraction import RequirementLevel
from tests._jsx_pins import open_tag
from app.services import gap_analysis, knockout
from app.services.ats.config import load_config

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_GAP_PAGE = "app/jobs/[id]/tailor/[sessionId]/page.tsx"
_JOB_PAGE = "app/jobs/[id]/page.tsx"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


# --- The knock-out card -------------------------------------------------------


def test_a_clear_knockout_claims_no_more_than_no_conflict():
    # `clear` is any pass OR warning (knockout.py), so "you meet" was false.
    src = Path(knockout.__file__).read_text(encoding="utf-8")
    assert 'elif results & {"pass", "warning"}:\n        status = "clear"' in src
    card = _read("components/job-knockout-card.tsx")
    # The quiet line says only that nothing conflicts; its words live in lib/knockout-line.ts.
    assert 'label: "No knock-outs"' in _read("lib/knockout-line.ts") and "{shown.label}" in card
    assert "Nothing rules you out" not in card and "conflicts with your profile" not in card
    assert "meet the listed" not in card and "match what the job lists" not in card


def test_an_unstated_knockout_says_what_it_could_not_check():
    # The salary and experience checks are omitted, not failed, when the profile lacks the answer.
    src = Path(knockout.__file__).read_text(encoding="utf-8")
    assert "if desired is None:\n        return None" in src
    assert "if job.years_experience_min is None or years_experience is None:\n        return None" in src
    card = _read("components/job-knockout-card.tsx")
    # The unstated line carries the caution in its accessible text; the Not run chips name what was skipped.
    assert "Nothing here to check. That doesn't mean you qualify." in card
    assert "uncheckedSentence" not in card and "Can't check" not in card
    assert 'job.salary_period === "year" || (job.salary_period == null && ceiling >= 10000)' in card
    assert 'anchorHref("/profile", "autofill-preferences")' in card
    assert 'anchorHref("/profile", "job-preferences-years")' in card
    assert "<JobKnockoutCard scan={data?.knockout} job={job} />" in _read(_JOB_PAGE)


def test_an_unrun_knockout_names_the_check_and_its_salary_field():
    """Which check, and which of the two salary fields it reads: knockout reads
    preferences.desired_salary (the Autofill tab's), not Job preferences' Minimum salary."""
    src = Path(knockout.__file__).read_text(encoding="utf-8")
    card = _read("components/job-knockout-card.tsx")
    assert "uncheckedLabel" not in card and "check: not run yet" not in card
    assert 'const NOT_RUN: Summary = { icon: NotRunIcon, word: "Not run"' in card  # replaces the sentence
    assert 'label: "Not checked yet"' not in card
    assert '(preferences or {}).get("desired_salary")' in src
    # The chip's action names the field it opens: Autofill's desired salary, About you's years.
    assert 'href: anchorHref("/profile", "autofill-preferences"),' in card
    assert 'link: "Add your desired salary",' in card
    assert 'link: "Add your years of experience",' in card


# --- The gap page ---------------------------------------------------------------


def test_quick_tailor_fills_only_what_its_settings_allow():
    page = _read(_GAP_PAGE)
    assert '"Fills the open gaps your Quick tailor settings allow, then tailors. " +' in page
    assert '"Your answers stay as they are. You can review and undo each change afterward."' in page
    assert "Fills every open gap" not in page


def test_replacing_a_draft_says_the_pdf_goes_and_history_keeps_it():
    page = _read(_GAP_PAGE)
    assert "\"Using your base resume as is replaces this job's tailored resume and removes its PDF. \" +" in page
    assert '"Version history keeps the old one.",' in page


def test_gap_counts_come_from_one_helper():
    lib = _read("lib/gap-counts.ts")
    assert 'if (!resolution) open += 1;\n    else if (resolution.action === "skip" || resolution.action === "cannot_confirm") skipped += 1;' in lib
    assert not re.search(r"^import (?!type )", lib, re.M)


def test_the_gap_page_and_score_tab_count_with_it():
    page = _read(_GAP_PAGE)
    assert page.count("gapCounts(") == 2  # the footer and each category
    # The footer is a SegmentedBar (its legend keeps the words); a category says how many are handled.
    assert 'name="Gap progress"' in page and "{done} of" not in page
    assert "{counts.answered + counts.skipped}/{counts.total}" in page and "Nothing open" not in page
    panel = _read("components/resume-step.tsx")
    assert "gapCounts(" in panel and "resolutions_json.length" not in panel
    # The count rides on ProgressCount above the button, so the button says only what it does.
    assert '<ProgressCount done={answered} total={totalGaps} noun="answered"' in panel
    assert "` · ${answered} answered`" not in panel


def test_auto_filled_banner_names_the_job_s_own_words():
    page = _read(_GAP_PAGE)
    assert 'resolutionProvenance(r)?.source === "wording_auto"' in page
    assert "filled in with the job's own words" in page
    assert "filled in from your resumes and career history" in page


def test_the_gap_page_names_the_ats_score_and_every_action():
    page = _read(_GAP_PAGE)
    assert "· Match score before tailoring:" in page
    # Each action is explained once, on its own control (the tooltip and aria-describedby), not in a page paragraph.
    assert "These gaps need your input." not in page
    controls = _read("components/gap-analysis/resolution-controls.tsx")
    hints = controls[controls.index("export const ACTION_HINTS") :]
    hints = hints[: hints.index("};")]
    for action in ("add_keyword", "user_input", "attach_project", "skip", "cannot_confirm"):
        assert f"{action}:" in hints, action
    labels = controls[controls.index("export const ACTION_LABELS") :]
    for word in ("Add keyword", "Answer", "Attach project", "Skip", "I can't confirm this"):
        assert f'"{word}"' in labels, word
    assert "→" not in page  # the score toast says "to"
    assert "`Match score: ${base.composite.toFixed(1)} to ${tailored.composite.toFixed(1)}" in page


def test_gap_rows_read_whole():
    # A truncated title or entry chip hides text at any width; nothing here is phone-only.
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "Skipped <span className=\"text-foreground font-medium\">{title}</span>" in card
    assert "Can&apos;t confirm <span className=\"text-foreground font-medium\">{title}</span>" in card
    assert ": skipped" not in card and "block truncate" not in card
    controls = _read("components/gap-analysis/resolution-controls.tsx")
    assert "label: `${entry.company}, ${entry.role}`," in controls
    assert '<span className="min-w-0 break-words">{children}</span>' in controls


def test_where_a_skill_was_found_is_labelled_and_cased():
    # evidence_entries are the entries the engine FOUND the skill in (ats/layers.py), not suggestions.
    layers = (Path(knockout.__file__).parent / "ats/layers.py").read_text(encoding="utf-8")
    assert "evidence_entries: list[str]  # entry labels where found (for the gap UI)" in layers
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "Mentioned in:" in card and "Could also go in" not in card
    assert "bits.push(`Matches “${matchedName(diagnostic.matched_term, gap.jd_skill)}”`);" in card
    assert 'entry.replace(" — ", ", ")' in card


# --- The ATS words ---------------------------------------------------------------


def _ts_keys(src: str, const: str) -> set[str]:
    body = src[src.index(f"const {const}") :]
    body = body[: body.index("};")]
    return set(re.findall(r"^\s+([a-z_]+):", body, re.M))


def test_every_engine_fix_hint_has_words():
    words = _read("lib/ats-words.ts")
    assert set(gap_analysis._HINT_TO_CATEGORY) <= _ts_keys(words, "FIX_HINT_LABELS")


def test_every_engine_placement_has_words():
    cfg = load_config()
    tiers = set(cfg.weights["placement_multipliers"])
    tiers |= {cfg.extras_config()["placement_tier"], cfg.credentials_config()["placement_tier"]}
    assert tiers <= _ts_keys(_read("lib/ats-words.ts"), "PLACEMENT_LABELS")


def test_every_requirement_level_and_subscore_has_words():
    words = _read("lib/ats-words.ts")
    assert set(typing.get_args(RequirementLevel)) <= _ts_keys(words, "REQUIREMENT_LABELS")
    subscores = set(re.findall(r'\{ key: "([a-z_]+)", label:', words))
    assert set(load_config().weights["composite_weights"]) == subscores


def test_ats_words_say_what_the_engine_measures():
    words = _read("lib/ats-words.ts")
    assert 'absent: "Not on your resume",' in words
    assert '{ key: "semantic_fit", label: "Job duties covered" }' in words
    assert 'extra_only: "Show it in your experience",' in words
    assert '"Add it"' not in words


# --- Match score, explained as a comparison using fixed rules -----------------


def test_the_ats_score_is_our_estimate_everywhere_it_is_explained():
    words = _read("lib/ats-words.ts")
    assert (
        '"A match score (0 to 100) uses fixed rules to compare each resume with this job\'s description."'
        in words
    )
    assert "{ATS_SCORE_LEAD}" in _read("components/resume-step.tsx")
    fit = _read("app/analytics/page.tsx")
    assert "{ATS_SCORE_LEAD_ALL_JOBS}" in fit
    assert fit.index("{ATS_SCORE_LEAD_ALL_JOBS}") < fit.index("<BaseSummaryCards />")
    conventions = " ".join((_FRONTEND.parent / "docs/frontend-conventions.md").read_text(encoding="utf-8").split())
    assert "uses fixed rules to compare each resume with this job's description" in conventions


# --- One request per click, focus never on <body> ---------------------------------


@pytest.mark.parametrize(
    ("rel", "marker"),
    [
        ("components/resume-step.tsx", "onClick={() => runOnce()}"),
        ("components/application-panel.tsx", "onClick={() => renderOnce()}"),
        (_GAP_PAGE, "applyAsIsOnce();"),
        ("app/referrals/page.tsx", 'type="submit"'),
    ],
)
def test_a_running_button_keeps_focus(rel: str, marker: str):
    src = _read(rel)
    starts = [m.start() for m in re.finditer(re.escape(marker), src)]
    assert starts, marker
    for at in starts:  # Update scores and Score my resumes both run the scoring
        button = src[src.rfind("<Button", 0, at) : src.index("</Button>", at)]
        assert "focusableWhenDisabled" in button and "data-disabled:opacity-50" in button


def test_find_gaps_keeps_focus_while_it_starts():
    step = _read("components/resume-step.tsx")
    # Analyze gaps, the step's own button: pending keeps focus on it while the gap analysis starts.
    button = step[step.rfind("<Button", 0, step.index('{creating ? "Analyzing gaps…" : "Analyze gaps"}')) :]
    button = button[: button.index("</Button>")]
    assert "focusableWhenDisabled" in button and "pending={creating}" in button
    assert '{creating ? "Analyzing gaps…" : "Analyze gaps"}' in button
    # Use resume as is keeps it too (one button, drawn in either state of the picked resume).
    as_is = step[step.index("const asIsButton = ") : step.index("Use resume as is\n")]
    assert "focusableWhenDisabled" in as_is and "pending={asIs.isPending}" in as_is


def test_step_two_has_one_filled_button():
    """Four blue "Find gaps and tailor" buttons, each with Start over and Mark applied under it, read as
    clutter. Step 2 now picks one resume from a chip row, so the view carries ONE filled button: Analyze
    gaps, or Continue gap analysis while the picked resume has an open gap analysis. Use resume as is is
    outline, and the rarer actions sit behind ⋯, whose items close onto ⋯ (it stays), so the confirms
    return there."""
    step = _read("components/resume-step.tsx")
    body = step[step.index("export function ResumeStep(") :]
    body = body[body.index("const asIsButton = ") : body.index("<UploadDialog")]
    # Filled = the default variant: no `variant=` on the two actions; everything else names its own.
    # The whole opening tag (open_tag skips the `>` of `=>` and braces), so a variant anywhere in it fails.
    analyze_at = body.rfind("<Button", 0, body.index('{creating ? "Analyzing gaps…" : "Analyze gaps"}'))
    analyze = open_tag(body[analyze_at:], "Button")
    assert "pending={creating}" in analyze and "variant=" not in analyze
    assert "disabled={busy || readOnly}" in analyze  # the tag's last attribute: the slice runs past onClick
    cont_at = body.rfind("<Button", 0, body.index("Continue gap analysis"))
    cont = open_tag(body[cont_at:], "Button")
    assert "Continue gap analysis" in cont and "variant=" not in cont
    # The two are the branches of one ternary on the picked resume's open gap analysis: never both.
    assert body.index("{openSession && !creating ? (") < cont_at < body.index(") : (") < analyze_at
    assert "onClick={() => void switcher.analyze(pickedSlug)}" in analyze
    buttons = _button_tags(body)
    unnamed = [b for b in buttons if "variant=" not in b]
    assert len(unnamed) == 2, unnamed  # Continue gap analysis, Analyze gaps
    assert '"Analyze gaps"' in body and "Find gaps" not in step
    as_is = body[: body.index("Use resume as is")]
    assert 'variant="outline"' in as_is
    # The ⋯: Update scores, Score them anyway (only with skipped countries), Mark applied, Import.
    menu = body[body.index('aria-label="More actions for resumes"') : body.index("</DropdownMenuContent>")]
    for item in ("Update scores", "Score them anyway", "Mark applied without tailoring", "Import resumes and documents",
                 "Restart gap analysis"):
        assert item in menu, item
    # Restart gap analysis: only while the picked resume has an open gap analysis; a new one replaces it.
    restart = menu[menu.index("{openSession && (") : menu.index("Restart gap analysis")]
    assert "disabled={busy || readOnly} onClick={() => void restartClick()}" in restart
    # With answers given it asks first (they are dropped), then the switch guard, then a new gap analysis.
    click = step[step.index("const restartClick = async () => {") : step.index("const chips = ")]
    assert "if (answered > 0) {" in click and 'title: "Start over?",' in click
    assert 'description: `Your ${answered} ${answered === 1 ? "answer" : "answers"} for ${pickedName} are dropped.`,' in click
    assert click.index("if (!ok) return;") < click.index("await switcher.analyze(pickedSlug, () => moreRef.current);")
    # One busy flag: every write in flight disables the others.
    assert "const busy = switcher.creating != null || asIs.isPending || appliedAsIs.isPending || run.isPending;" in step
    for item in ("restartClick()", 'runOnce("manual")', "onClick={scoreOtherCountries}", "appliedAsIsClick(pickedSlug)"):
        opener = menu[menu.rfind("<DropdownMenuItem", 0, menu.index(item)) : menu.index(item)]
        assert "disabled={busy || readOnly}" in " ".join(opener.split()), item
    assert '{run.isPending ? "Updating scores…" : "Update scores"}' in menu
    assert "{jobCountry && skipped.length > 0 && (" in menu
    assert "returnFocus: () => moreRef.current," in step  # the confirm returns to ⋯, not the gone item


def test_a_resume_pick_is_a_preview_and_the_writes_confirm():
    """A pick changes only the chip, the summary and the body. The actions that write with another resume than
    the job's (Analyze gaps, Continue gap analysis, Restart gap analysis, Use resume as is) ask first, through
    the one hook the gap page shares (Task 11), in words that match the job's state (lib/resume-pick.ts)."""
    step = _read("components/resume-step.tsx")
    assert "onPick={setChosen}" in step and "confirmSwitch" not in step[step.index("onPick=") - 200 : step.index("onPick=")]
    assert "const switcher = useResumeSwitch({ jobId, application, sessions: sessions.data ?? [] });" in step
    # Continue stays a link while nothing would be replaced; else the confirm goes first.
    cont = step[step.index("// A link while nothing would be replaced") : step.index("Continue gap analysis\n")]
    assert 'if (!switcher.switchWords(pickedSlug, "continue")) return;' in cont and "event.preventDefault();" in cont
    assert "void switcher.continueOn(pickedSlug, openSession.id);" in cont
    # Use resume as is: the switch words for another resume; the old Replace draft words for the same one.
    as_is = step[step.index("const asIsClick = async") : step.index("asIsOnce({ baseResume, sessionId });")]
    assert 'if (switcher.switchWords(baseResume, "as_is")) {' in as_is
    assert 'if (!(await switcher.confirmSwitch(baseResume, "as_is"))) return;' in as_is
    assert "} else if (application?.customized_json) {" in as_is and 'title: "Replace the existing tailored draft?",' in as_is
    hook = _read("hooks/use-resume-switch.ts")
    assert "const state = jobResumeState(application, sessions);" in hook
    assert "return words == null || confirm({ ...words, destructive: true, returnFocus });" in hook
    assert 'if (await confirmSwitch(slug, "analyze", returnFocus)) createOnce(slug);' in hook
    assert 'if (await confirmSwitch(slug, "continue", returnFocus)) go(`/jobs/${jobId}/tailor/${sessionId}`);' in hook
    assert "return open ? continueOn(slug, open.id, returnFocus) : analyze(slug, returnFocus);" in hook


def test_the_switch_confirm_says_what_the_job_holds():
    """Tailored comes from a tailored gap analysis, never from `customized_json` (a resume used as is has one
    too); applied from the status. Each state has its words; the node tests run every branch."""
    from tests.node_ts import run_node_test

    words = _read("lib/resume-pick.ts")
    assert 'if (application.status != null && application.status !== "draft") return "applied";' in words
    assert '(s.application_id === application.id || s.base_resume === application.base_resume),' in words
    assert "? `You applied with ${from}. ${doing} replaces that resume and its PDF. Version history keeps them.`" in words
    assert "? `This job already has a tailored ${from} resume. ${doing} replaces that draft and removes its PDF. ` +" in words
    assert "`Version history keeps the old one. Answers you gave in the gaps for ${from} stay with it.`" in words
    assert ": `This job's resume is ${from}, used as is. ${doing} replaces it and removes its PDF. ` +" in words
    for label in ('analyze: "Switch and analyze gaps",', 'continue: "Switch and continue",', 'as_is: "Switch and use as is",'):
        assert label in words, label
    result = run_node_test("lib/resume-pick.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_default_pick_is_set_once_both_lists_have_settled():
    step = _read("components/resume-step.tsx")
    assert "if (frozenPick == null && scores.isSuccess && sessionsSettled && available.length > 0) {" in step
    assert "setFrozenPick(pickDefault());" in step
    assert "(baseRows.length > 0 && !sessionsSettled) ||" in step  # the skeleton holds until then
    assert "defaultResumePick({ sessions: sessions.data ?? [], application, best: available[0] ?? null, available })" in step


def test_the_resume_chips_are_toggle_buttons():
    chips = _read("components/resume-chips.tsx")
    assert 'role="group" aria-label="Base resume"' in chips
    assert "aria-pressed={on}" in chips and "aria-disabled={busy || undefined}" in chips
    assert "if (!busy && !on) onPick(r.slug);" in chips  # focusable while busy, a press does nothing
    # FilterChips' look: 28px, label-medium, a 12px leading Check, secondary-container when on.
    cls = chips[chips.index('"inline-flex h-7') : chips.index('"border-border hover:bg-surface-container"')]
    for token in ("h-7", "rounded-full", "text-label-medium", "transition-colors", "duration-(--duration-short3)",
                  "ease-(--ease-standard)", "focus-visible:outline-ring",
                  "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"):
        assert token in cls, token
    assert '{on && <Check className="size-3 shrink-0" aria-hidden="true" />}' in chips
    assert '<span className="tabular-nums">{score}</span>' in chips
    assert '{isBest && <Badge variant="secondary">Best</Badge>}' in chips
    # The top 3, then a reveal that says it is expanded.
    assert "const CHIPS_SHOWN = 3;" in chips
    assert "aria-expanded={expanded}" in chips and '{expanded ? "Show fewer" : `${hidden} more`}' in chips


def test_the_score_summary_opens_its_breakdown_in_a_popover():
    summary = _read("components/score-summary.tsx")
    summary = summary[summary.index("export function ScoreSummary(") :]
    assert "bg-surface-container-low" in summary
    assert '<span className="text-muted-foreground">Skills covered</span>' in summary
    assert '<span className="text-muted-foreground">Weakest</span> {SUBSCORE_LABELS[weakestAt].label}' in summary
    assert "{weakestAt >= 0 && (" in summary  # all equal: no Weakest
    trigger = summary[summary.index("<PopoverTrigger") : summary.index("/>", summary.index("Score breakdown"))]
    assert "aria-expanded={open}" in trigger and "Score breakdown" in trigger
    # A new pick closes the popover, and the summary is not remounted: the score counts from the last resume.
    assert "const open = openFor === score.target_id;" in summary
    assert "key={pickedSlug}" not in _read("components/resume-step.tsx")


def test_low_coverage_on_every_resume_is_said_once():
    """The banner claims "fewer than a quarter": the engine's threshold, so a change there fails here."""
    from app.services.ats.engine import LOW_COVERAGE_THRESHOLD

    assert LOW_COVERAGE_THRESHOLD == 0.25
    assert "shows fewer than a quarter of this job's skills" in _read("lib/ats-words.ts")
    panel = _read("components/resume-step.tsx")
    assert "baseRows.length > 1 && baseRows.every((row) => coverageWarning(row) != null);" in panel
    assert "showCoverage={!lowCoverageEverywhere}" in panel


def test_a_gap_row_hands_focus_to_what_replaces_it():
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "const focusNext = useFocusOnNextCommit();" in card
    assert card.count("ref={rootRef}") == 5  # every branch GapCard renders
    for handler in ("reopenGap", "handOff"):
        assert f"const {handler} = " in card, handler
    # Skip, I can't confirm this, both Undos (via reopenGap), Edit twice, Done and the two library chips.
    assert card.count("handOff();") == 9
    assert 'commit("skip", {});\n      handOff();\n      return;' in card


# --- The job workspace ---------------------------------------------------------


def test_no_step_is_locked_and_a_future_step_says_what_opens_it():
    page = _read(_JOB_PAGE)
    steps = _read("components/job-steps.tsx")
    # A later step with nothing to show is plain text: not a button, never disabled, no lock, no tooltip.
    cell = steps[steps.index("              ) : (\n                <div") : steps.index("</li>")]
    assert "<div className={cn(CELL, edge)}" in cell and "<button" not in cell and "tabIndex" not in cell
    assert "disabled=" not in steps and "title=" not in steps and "Lock" not in steps and "Tooltip" not in steps
    for gone in ("LOCKED_REASON", "lockedReasonId", "CONCEPT_ICONS.locked", "aria-describedby", "Unlocks after you tailor"):
        assert gone not in page, gone
    # Its line says what opens it (lib/job-steps.ts, node-tested).
    lib = _read("lib/job-steps.ts")
    assert '"Review the changes, edit, Create PDF"' in lib and '"After Create PDF"' in lib
    # A link to step 3 or 4 before the job has its own resume shows a panel that says so, and points at step 2.
    assert '<p>Nothing tailored yet.</p>' in page and "Go to Resume and gaps" in page
    assert page.count('<NothingTailoredYet onOpenFit={() => setStep("fit")} />') == 2


def test_a_step_with_something_to_show_is_a_button():
    """Step 3 with a draft (one from before a re-analysis too) and step 4 whenever the job has an application
    are buttons: `reachable` in lib/job-steps.ts (node-tested) decides, and the stepper honours it."""
    page = _read(_JOB_PAGE)
    steps = _read("components/job-steps.tsx")
    assert "const button = step.reachable || step.state !== \"next\";" in steps and "{button ? (" in steps
    # The page hands the builder the application itself, so `hasApplication` and the draft come from it.
    assert "jobStepsInput({\n      job,\n      application,\n" in page


def test_step_one_reads_the_knockout_card_words():
    page = _read(_JOB_PAGE)
    assert 'import { knockoutWords } from "@/lib/knockout-line";' in page
    assert "knockout: knockoutWords(\n        data.knockout?.status ?? null,\n        data.knockout ? knockoutNotChecked(data.knockout, job) : false,\n      )," in page


def test_every_old_tab_link_still_lands_on_a_step():
    page = _read(_JOB_PAGE)
    lib = _read("lib/job-steps.ts")
    assert 'jd: "job", fit: "fit", output: "output", qa: "qa", submitted: "qa",' in lib
    # The writers keep their values: /new and the Companion open fit, the gap page and the studio's Back output.
    root = _FRONTEND.parent
    for rel, value in (
        ("frontend/app/new/page.tsx", "?tab=fit"),
        ("frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx", "?tab=output"),
        ("frontend/app/applications/[id]/resume/page.tsx", "?tab=output"),
        ("extension/panel/stages/resume.js", "?tab=fit"),
    ):
        assert value in (root / rel).read_text(encoding="utf-8"), rel
    # Given, the link's step; else the stage's (step 1 while a proposal waits on you).
    assert "Object.hasOwn(TAB_TO_STEP, requestedTab) ? stepForTab(requestedTab) : null" in page
    assert 'proposalStatus && PROPOSAL_WAITS_ON_YOU.has(proposalStatus) ? "job" : currentStep(stage);' in page
    # Fixed once, from the first data: a refetch or a triage never switches the panel under you.
    assert "if (chosenStep == null) setChosenStep(initialStep);" in page
    assert 'if (detailsOpen == null) setDetailsOpen(stage === "saved");' in page


def test_the_rare_actions_sit_behind_one_more_actions_menu():
    page = _read(_JOB_PAGE)
    header = page[page.index("<header") : page.index("</header>")]
    menu = header[header.index("<DropdownMenu>") : header.index("</DropdownMenu>")]
    items = [m.strip() for m in re.findall(r"\n\s*(?:\{promote\.isPending \? \"Queueing…\" : \"(Queue in Agent inbox)\"\}|\{reExtract\.isPending \? \"Refreshing…\" : \"(Refresh details)\"\}|(Delete job))", menu) for m in m if m]
    assert items == ["Queue in Agent inbox", "Refresh details", "Delete job"], items
    assert menu.count("<DropdownMenuItem") == 3 and 'label="More actions"' in menu
    assert menu.count("returnFocus: moreTrigger,") == 2  # each confirm returns to ⋯
    # Out of the header: the Details menu lives on step 4; nothing else is an icon-only delete.
    assert "<ApplicationDetailsMenu" not in header and 'label="Delete job"' not in page
    assert page.index('{visited.has("qa") ? (') < page.index("<ApplicationDetailsMenu")
    assert "actionsSlot=" not in page


def test_the_job_header_keeps_its_title_and_drops_empty_facts():
    page = _read(_JOB_PAGE)
    assert '<h1 className="text-title-large font-medium tracking-tight break-words">' in page
    assert "jobMetaLine([" in page
    meta = _read("lib/job-meta.ts")
    assert 'if (!part || part === "Not stated") continue;' in meta and "if (seen.has(key)) continue;" in meta
    assert "jobMetaLine([" in _read("components/proposals/proposals-section.tsx")


def test_delete_job_names_the_proposals_it_deletes():
    # application_proposals.job_id is ON DELETE CASCADE.
    model = (Path(knockout.__file__).parents[1] / "models/application_proposal.py").read_text(encoding="utf-8")
    assert 'ForeignKey("jobs.id", ondelete="CASCADE")' in model
    assert '"This also deletes its application, match scores, gap analyses, answers and any Agent inbox proposals for it.",' in _read(_JOB_PAGE)


def test_mark_applied_hides_once_the_job_is_applied():
    step = _read("components/resume-step.tsx")
    assert "const applied = applicationStatus != null && applicationStatus !== \"draft\";" in step
    menu = step[step.index('aria-label="More actions for resumes"') : step.index("</DropdownMenuContent>")]
    assert "{applied ? null : (" in menu and "Mark applied without tailoring" in menu
    # Its neighbour, Restart gap analysis, shows only while the picked resume has an open gap analysis.
    assert "{openSession && (" in menu and "<RefreshCw /> Restart gap analysis" in menu
    page = " ".join(_read(_JOB_PAGE).split())
    assert "<ResumeStep jobId={id} application={application} readOnly={!ownership.canWrite} onUsedAsIs={() => {" in page
    # Use resume as is opens step 3 and hides the button that held focus: the opened step takes it.
    assert 'focusOpenedStep.current = true; setStep("output"); }}' in page
    assert "stepsRef.current?.querySelector<HTMLElement>('[aria-current=\"step\"]')?.focus({ preventScroll: true });" in page


def test_the_tailored_resume_step_names_what_it_holds():
    panel = _read("components/application-panel.tsx")
    step = panel[panel.index("export function TailoredResumeStep(") : panel.index("function TailoredResumeMenu(")]
    # The stepper names the step: the card repeats no title. Its body is the changes, counted, and a resume
    # used as is (no changes) says so plainly rather than "tailored".
    assert "<CardTitle>" not in step
    assert "`Changes (${hunks.length})`" in step
    assert "No changes from your base resume." in step and "No changes yet." in step
    qa = _read("components/qa-tab.tsx")
    assert 'label="Write a new version"' in qa and 'label="Regenerate"' not in qa


def test_opt_and_proposal_dates_read_plainly():
    fields = _read("components/job-extracted-fields.tsx")
    assert 'label="OPT (US student work permit) accepted"' in fields
    panel = _read("components/proposals/proposal-agent-panel.tsx")
    assert "Proposed {formatShortDate(data.created_at)}" in panel
    assert " · expires ${formatShortDate(data.expires_at)}" in panel
    assert '<Fact label="Date">' not in panel and '<Fact label="Expires">' not in panel


def test_saved_twice_says_it_plainly():
    assert '"This job is already saved."' in _read("app/new/page.tsx")
    assert "This job is already saved." in _read("components/job-extraction-summary.tsx")


def test_the_tracker_says_where_agent_jobs_are():
    page = _read("app/applications/page.tsx")
    assert "Jobs a connected agent found are under Agents." in page


def test_the_inbox_explains_mcp_and_the_skill_once():
    inbox = _read("components/proposals/proposals-section.tsx")
    # The agents first, then how they connect (first-read pass: the MCP clause led).
    assert ("such as Claude, Codex or the ChatGPT desktop app. It connects through MCP "
            "(the standard way AI apps connect to tools).") in inbox
    assert "ready-made instructions for your agent" in inbox
    assert "May not accept OPT" in inbox


# --- Safety and consent sentences that a shortening must keep (review I9) ---------


@pytest.mark.parametrize(
    ("rel", "sentence"),
    [
        ("components/job-knockout-card.tsx", "That doesn't mean you qualify."),
        (_GAP_PAGE, "Version history keeps the old one."),
        ("components/resume-step.tsx", '"It replaces any tailored draft (Version history keeps it) " +'),
        (_GAP_PAGE, "Your changes here won&apos;t be saved."),
        (_GAP_PAGE, "You can review and undo each change afterward."),
        ("components/analytics/autofill-coverage-card.tsx", ", including which sites they were on and when.`"),
        ("components/analytics/autofill-coverage-card.tsx", '" You can\'t undo this." +'),
        ("components/application-panel.tsx", "This deletes its tailored resume, answers and PDF. The job stays saved."),
        ("components/qa-tab.tsx", "A new letter replaces the saved one, including any edits you made to it."),
        ("components/resume-step.tsx", "and closes any open proposal in your Agent inbox for this job."),
    ],
)
def test_a_safety_sentence_survives(rel: str, sentence: str):
    assert sentence in _read(rel)


def test_the_searchable_list_kind_keeps_its_own_word():
    card = _read("components/analytics/autofill-coverage-card.tsx")
    assert 'combobox: "Searchable list",' in card
    kinds = re.findall(r'^\s+[a-z]+: "([A-Z][a-z ]+)",', card, re.M)
    assert len(kinds) == len(set(kinds))  # two kinds under one word read as a repeat


# Sentence case: a tab, button or menu name capitalizes its first word and proper names only.
_PROPER = {"ATS", "PDF", "PDFs", "Q&amp;A", "Q&A", "OPT", "MCP", "Agent", "Agents", "Quick", "Companion", "AI"}
_NAME = re.compile(
    r'<TabsTrigger[^>]*>\s*([^<{]+?)\s*</TabsTrigger>|\blabel="([^"]+)"|confirmLabel: "([^"]+)"'
)


def _title_cased(name: str) -> list[str]:
    words = name.split()[1:]
    return [w for w in words if w[:1].isupper() and w.strip(".,?") not in _PROPER]


@pytest.mark.parametrize(
    "rel",
    [
        _JOB_PAGE,
        _GAP_PAGE,
        "components/resume-step.tsx",
        "components/application-panel.tsx",
        "components/qa-tab.tsx",
        "app/analytics/page.tsx",
        "components/analytics/analytics-overview.tsx",
        "components/job-knockout-card.tsx",
    ],
)
def test_names_are_sentence_case(rel: str):
    names = ["".join(g or "" for g in m.groups()) for m in _NAME.finditer(_read(rel))]
    offenders = {n: _title_cased(n) for n in names if _title_cased(n)}
    assert offenders == {}, offenders


def test_the_step_names_are_sentence_case():
    titles = 'const TITLES: Record<StepKey, string> = { job: "Job", fit: "Resume and gaps", output: "Tailored resume", qa: "Apply" };'
    assert titles in _read("lib/job-steps.ts")


# ── Unreadable job dates (Task 25): said plainly, with a format that works ──────


def test_the_score_tab_says_why_undated_jobs_score_low():
    """First-read pass: "Recent experience 11" with dates like 2021-03 and no word of why.
    The engine reads "Mon YYYY" only (accepting more is §11: it moves match scores)."""
    from app.services.ats import layers
    from tests.node_ts import ts_map

    words = _read("lib/ats-words.ts")
    assert 'const DATES_FLAG = "Some job dates can\'t be read";' in words
    assert "Write dates like Jul 2022 in your base resume." in words
    # The engine's flag is what the web app detects: one reword would silence the note.
    import inspect
    assert 'flags.append("Some job dates can\'t be read.' in inspect.getsource(layers.l5_format)
    assert ts_map("./lib/ats-words.ts", "datesUnreadable", [
        ["Some job dates can't be read. Write them like Jul 2022."], ["Section missing or empty: summary"],
    ]) == [True, False]
    panel = _read("components/score-summary.tsx")  # step 2's Score breakdown
    assert "{datesUnreadable(score.subscores_json.format_flags) && (" in panel
    assert "<p className=\"text-muted-foreground text-body-small\">{UNREADABLE_DATES_NOTE}</p>" in panel
    # Each subscore is a meter out of 100 (aria-valuemax); the visible " of 100" went, the headline keeps "/ 100".
    assert "> of 100<" not in panel and "aria-valuemax" not in panel and "<ScoreBar" in panel
    assert '<span className="text-muted-foreground text-body-medium"> / 100</span>' in panel


def test_a_skill_with_no_example_never_contradicts_mentioned_in():
    """"Skills with no example" beside "Mentioned in: Northwind" read as a contradiction:
    the entries were found, but their dates can't be read, so only the skills list counts."""
    words = _read("lib/ats-words.ts")
    assert 'return placement === "skills_list_only" && entries.length > 0;' in words
    assert "These don't count as examples yet because we can't read a date on them." in words
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "const undated = undatedEvidence(diagnostic.placement, entries);" in card
    assert "{undated ? <p className=\"text-muted-foreground basis-full text-body-small\">{UNDATED_EVIDENCE_NOTE}</p> : null}" in card


def test_the_tracker_names_its_match_score_column():
    page = _read("app/applications/page.tsx")
    assert 'header("ats", "Match score",' in page


def _button_tags(src: str) -> list[str]:
    """Each Button's whole opening tag (`open_tag` skips braces and the `>` of `=>`)."""
    return [open_tag(src[m.start() :], "Button") for m in re.finditer(r"<Button(?=[\s/>])", src)]


def test_step_three_has_one_filled_button_and_the_pdf_card_carries_its_actions():
    panel = _read("components/application-panel.tsx")
    step = panel[panel.index("export function TailoredResumeStep(") : panel.index("function TailoredResumeMenu(")]
    # One filled button: Create PDF before a PDF, Continue to Apply once one exists (the two arms of one ternary).
    filled = [t for t in _button_tags(step) if "variant=" not in t]
    assert len(filled) == 2, filled
    assert 'onClick={() => onOpenStep("qa")}' in filled[0] and "onClick={() => renderOnce()}" in filled[1]
    assert step.index("{hasPdf ? (") < step.index('onOpenStep("qa")') < step.index(") : (") < step.index(
        "{renderPdf.isPending ? pdfWords.pending : pdfWords.label}")
    # Edit resume is in the strip, an outline link; the page no longer places it above the step.
    assert "<Link href={`/applications/${app.id}/resume`}>" in step
    assert "Edit resume" not in _read(_JOB_PAGE)
    # The PDF card: the file's own actions as named icon buttons, then Update PDF (small, outline).
    card = step[step.index('<div className="bg-canvas') :]
    for name in ('label="Download PDF"', 'label="Open PDF in new tab"'):
        assert name in card
    assert '<ShowCopyButton applicationId={app.id} variant="ghost" iconOnly />' in card
    update = [t for t in _button_tags(card) if "renderOnce()" in t]
    assert len(update) == 1 and 'variant="outline"' in update[0] and 'size="sm"' in update[0]
    # Each change reverts on its own, and the rare actions sit behind the strip's ⋯.
    assert 'label="Revert this change"' in step and 'data-revert=""' in step
    menu = panel[panel.index("function TailoredResumeMenu(") :]
    assert 'label="More actions for the tailored resume"' in menu
    assert 'onClick={() => onOpenStep("fit")}' in menu and "Tailor again" in menu and "Delete application" in menu
    # Five changes, then the rest behind one toggle; once a PDF exists the list folds to its header.
    assert "const SHOWN_CHANGES = 5;" in panel and "`Show ${hunks.length - SHOWN_CHANGES} more changes`" in step
    assert "const listOpen = listShown ?? !hasPdf;" in step and "aria-expanded={listOpen}" in step
    # Only the rows fold: the 409 line, a load error and Check wording sit outside the folded block.
    fold = step[step.index("<div id={listId} hidden={!listOpen}") : step.index("{hunks.length > 0 ? (")]
    assert "No changes yet." not in fold and "Try again" not in fold and "Check wording" not in fold
    assert 'label="Revert this change"' in fold
    # The full compare (each skill Gained, Lost or Same, Update score) stays one click away.
    breakdown = step[step.index("<Popover open={breakdownOpen}") : step.index("</Popover>")]
    assert "aria-expanded={breakdownOpen}" in breakdown and "Score breakdown" in breakdown
    assert "shadow-level2" in breakdown and "<AtsComparePanel app={app} jobId={jobId} readOnly={readOnly} />" in breakdown
    # A failed Create PDF says so without naming an action it may not have been.
    assert "Creating the PDF failed. Try again." in step


def test_step_three_says_provenance_in_the_studios_words():
    panel = _read("components/application-panel.tsx")
    assert "PROVENANCE_CHIPS[value]" in panel and "const PROVENANCE:" not in panel
    assert '"Yours"' not in panel and '"From career history"' not in panel
    review = _read("components/resume-editor/diff-review.tsx")
    assert "export const PROVENANCE_CHIPS:" in review
    assert 'name: "From your career history"' in review and 'user: { kind: "you",' in review

