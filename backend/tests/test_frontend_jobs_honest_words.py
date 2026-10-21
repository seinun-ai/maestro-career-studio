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
from tests._jsx_pins import open_tag, squash
from app.services import gap_analysis, knockout
from app.services.ats.config import load_config

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_GAP_PAGE = "app/jobs/[id]/tailor/[sessionId]/page.tsx"
_JOB_PAGE = "app/jobs/[id]/page.tsx"
_STEP_THREE = "components/tailored-resume-step.tsx"
_STEPS_HOOK = "hooks/use-job-steps.ts"


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
    preferences.desired_salary (Profile's Start and pay), not Job preferences' Minimum salary."""
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
    # One set of words (lib/resume-pick.ts), asked through one hook by the gap page and step 2.
    words = _read("lib/resume-pick.ts")
    assert "\"Using your base resume as is replaces this job's tailored resume and removes its PDF. \" +" in words
    assert '"Version history keeps the old one.",' in words
    assert "confirm({ ...asIsOverDraftConfirm(applied), destructive: true, returnFocus })" in _read("hooks/use-resume-switch.ts")
    assert "if (await switcher.confirmAsIs(session.data.base_resume)) applyAsIsOnce();" in _read(_GAP_PAGE)
    assert "if (await switcher.confirmAsIs(baseResume)) asIsOnce({ baseResume, sessionId });" in _read(
        "components/resume-step.tsx"
    )
    for rel in (_GAP_PAGE, "components/resume-step.tsx"):
        assert "asIsOverDraftConfirm" not in _read(rel), rel


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


def test_the_gap_page_draws_step_two_with_the_resume_chips():
    """The gap page is step 2 of the same four steps: under its header, `JobSteps` with step 2 shown (fed by
    `jobStepsInput` from the job page's own queries) and `ResumeChips` with the analysis's resume picked. A chip goes
    through `useResumeSwitch` (step 2's confirm, then the resume's open gap analysis or a new one, replacing the
    address), after a save; the Tailor and Quick tailor confirm re-tailoring the resume you applied with."""
    page = _read(_GAP_PAGE)
    header_end = page.index("</header>")
    stepper = page.index('<JobSteps steps={steps} current="fit" onSelect={(key) => void openStep(key)} busy={stepsBusy} />')
    chips = page.index("<ResumeChips")
    assert header_end < stepper < chips < page.index("<GapLocked value=")
    chip_tag = open_tag(page[chips:], "ResumeChips")
    assert "picked={sessionBase}" in chip_tag and "onPick={(pick) => void pickResume(pick)}" in chip_tag
    assert "busy={switchBusy}" in chip_tag and "actions=" not in chip_tag
    assert "const sessionBase = session.data.base_resume;" in page
    assert "const switcher = useResumeSwitch({ jobId, application, sessions: sessions.data ?? [], replace: true });" in page
    assert "if (await saveNow()) await switcher.openOrCreate(pick);" in page
    # The steps come from the job page's own hook (the same keys, so the cache is shared), called before any
    # early return; the chips from step 2's.
    assert "const { scoreRows, sessions, baseName, steps } = useJobSteps(jobId, jobDetail.data, shownAnalysis);" in page
    assert page.index("useJobSteps(jobId, jobDetail.data, shownAnalysis)") < page.index("if (sessionError != null) {")
    assert "const { baseRows, chips } = useResumeChipOptions(scoreRows.data ?? []);" in page
    for gone in ("listAtsScores", "listTailoringSessions", "resumeDiffQuery", "standingLine", "jobStepsInput"):
        assert gone not in page, gone
    hook = _read(_STEPS_HOOK)
    for key in ('queryKey: ["ats-scores", jobId],', 'queryKey: ["tailoring-sessions", jobId],', 'queryKey: ["proposal", proposalId],'):
        assert key in hook, key
    assert "const standing = standingLine({" in hook and "rung: detail," in hook
    # Steps 1, 3 and 4 open the job page at the tab it already honours; step 2 is this page.
    assert 'const STEP_TABS: Partial<Record<StepKey, string>> = { job: "jd", output: "output", qa: "qa" };' in page
    assert "if (tab && (await saveNow())) router.push(`/jobs/${jobId}?tab=${tab}`);" in page
    # No switch before the confirm can be worded and the right gap analysis found.
    assert "!jobDetail.data || !sessions.data || switcher.creating != null || tailorBusy" in page
    assert '? switcher.confirmSwitch(session.data.base_resume, "tailor")' in page
    assert page.count("(await confirmTailorAgain()) &&") == 2  # Tailor and Quick tailor
    # The actions that confirm on the job's application need the detail: without it Use resume as is would replace a
    # tailored draft, and Tailor an applied resume, unasked. A failed detail says what waits, with Try again.
    # Use resume as is needs the gap analyses too: with none, a tailored draft reads as used as is.
    ends = {"onClick={onQuickTailorClick}": "|| !jobDetail.data}", "onClick={onTailorClick}": "|| !jobDetail.data}",
            "Use resume as is\n": "|| !jobDetail.data || !sessions.data}"}
    for label, end in ends.items():
        disabled = page.index("disabled={", page.rindex("<Button", 0, page.index(label)))
        assert page[disabled : page.index("\n", disabled)].endswith(end), label
    assert "jobDetail.isPending}" not in page
    # A failed gap analyses list locks Use resume as is and the chips too: the same block names it, and its one
    # Try again asks for both.
    assert "const detailFailed = isLoadFailure(jobDetail);" in page and "const sessionsFailed = isLoadFailure(sessions);" in page
    start = page.index("{detailFailed || sessionsFailed ? (")
    failed = squash(page[start : page.index(") : null}", start)])
    assert "\"Couldn't load this job, so Tailor, Use resume as is and the resume chips wait for it.\"" in failed
    assert "\"Couldn't load this job's gap analyses, so Use resume as is and the resume chips wait for them.\"" in failed
    assert 'detail={loadErrorDetail(detailFailed ? jobDetail.error : sessions.error, "job")}' in failed
    assert "retrying={jobDetail.isFetching || sessions.isFetching}" in failed
    assert "onRetry={() => { void jobDetail.refetch(); void sessions.refetch(); }}" in failed
    assert start < page.index('<div className="bg-background/95 sticky bottom-0')
    # A superseded or closed analysis made no draft: its way on is step 2, not step 3.
    done = page[page.index('if (session.data.status !== "open") {') :]
    done = done[: done.index("</main>")]
    assert 'const tailored = session.data.status === "tailored";' in done
    assert "tailored ? (" in done and "<Link href={`/jobs/${jobId}?tab=fit`}>Go to Resume and gaps</Link>" in done
    # An analysis whose resume has no chip says why.
    assert "is archived, so it has no chip here." in page and "has no Match score for this job, so it has no chip here." in page
    # Step 2's no-session panel says where Analyze gaps goes.
    assert "It opens on its own page, with these steps on top." in squash(_read("components/resume-step.tsx"))


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
        ("components/tailored-resume-step.tsx", "onClick={() => renderOnce()}"),
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
    # Analyze gaps, the step's own button, is the lead card's action (design refresh Task 4.3): pending keeps focus
    # on it while the gap analysis starts, because the lead card's button is always focusable when disabled.
    action = squash(step[step.index('label: creating ? "Analyzing gaps…" : "Analyze gaps",') :])
    action = action[: action.index("},")]
    assert "pending: creating," in action and "disabled: busy || readOnly," in action
    lead = _read("components/ui/lead-card.tsx")
    press = open_tag(lead[lead.rindex("<Button", 0, lead.index("pending={action.pending}")) :], "Button")
    assert "focusableWhenDisabled" in press and "disabled={action.disabled}" in press
    # Use resume as is keeps it too (one button, drawn in either state of the picked resume).
    as_is = step[step.index("const asIsButton = ") : step.index("Use resume as is\n")]
    assert "focusableWhenDisabled" in as_is and "pending={asIs.isPending}" in as_is


def test_step_two_has_one_filled_button():
    """Four blue "Find gaps and tailor" buttons, each with Start over and Mark applied under it, read as
    clutter. Step 2 now picks one resume from a chip row, so the view carries ONE filled button: Analyze
    gaps, or Continue gap analysis while the picked resume has an open gap analysis, or View tailored resume once
    its analysis tailored the job's resume. Since the design refresh (Task 4.3) the view is a LeadCard whose
    `action` is that one button; Use resume as is and Analyze gaps again are outline, beside it (`secondary`), and
    the rarer actions sit behind ⋯, whose items close onto ⋯ (it stays), so the confirms return there."""
    step = _read("components/resume-step.tsx")
    body = step[step.index("export function ResumeStep(") :]
    body = body[body.index("const asIsButton = ") : body.index("<UploadDialog")]
    # No Button in the view is filled by hand: each names its variant, and the filled one is the lead card's.
    buttons = _button_tags(body)
    assert buttons and all("variant=" in b for b in buttons), [b for b in buttons if "variant=" not in b]
    assert "<LeadCard eyebrow=\"Resume and gaps\" action={lead.action} secondary={lead.secondary}>" in body
    # The arms of one ternary on the picked resume's gap analysis (open, finished, none): one action each, in order.
    lead = squash(body[body.index("const lead: {") : body.index("return (")])
    arms = [lead.index("openSession && !creating ? {"), lead.index('label: "Continue gap analysis",'),
            lead.index(": finished ? {"), lead.index('label: "View tailored resume",'),
            lead.index('label: creating ? "Analyzing gaps…" : "Analyze gaps",')]
    assert arms == sorted(arms), arms
    assert lead.count("action: {") == 3
    analyze = lead[lead.index('label: creating ? "Analyzing gaps…" : "Analyze gaps",') :]
    assert "onClick: () => void switcher.analyze(pickedSlug), pending: creating, disabled: busy || readOnly," in analyze
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
    click = step[step.index("const restartClick = async () => {") : step.index("const asIsButton = ")]
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


def test_step_two_shows_the_gap_analysis_that_made_the_job_s_tailored_resume():
    """A job tailored from a finished gap analysis ("7 gaps answered, 1 skipped" on the step's line) offered a fresh
    Analyze gaps / Use resume as is card, as if no analysis had run. With no open one, the picked resume's finished
    analysis (lib/resume-pick.ts `finishedAnalysis`) shows its counts, View tailored resume (step 3, the filled button)
    and Analyze gaps again."""
    step = _read("components/resume-step.tsx")
    assert 'import { defaultResumePick, finishedAnalysis } from "@/lib/resume-pick";' in step
    assert ("const finished = openSession ? null : finishedAnalysis({ sessions: sessions.data ?? [], application, "
            "picked: pickedSlug });") in squash(step)
    done = _slice(step, ": finished\n", "          : {")
    # The counts are the gap page's own (lib/gap-counts), worded as the step's line words them.
    assert "gapCounts(" in step[step.index("const finishedCounts"):step.index(": finished\n")]
    assert '{`${finishedCounts.answered} ${finishedCounts.answered === 1 ? "gap" : "gaps"} answered, ' in done
    assert "${finishedCounts.skipped} skipped. Step 3 has the tailored resume.`}" in done
    assert '<p className="text-title-small">Gap analysis done</p>' in done
    # View tailored resume is the lead card's action (filled); Analyze gaps again sits beside it, outline.
    assert 'action: { label: "View tailored resume", onClick: () => onOpenTailored?.() },' in done
    again = open_tag(done[done.rfind("<Button", 0, done.index("Analyze gaps again")):], "Button")
    assert 'variant="outline"' in again and "onClick={() => void switcher.analyze(pickedSlug)}" in again
    assert "pending={creating}" in again and "focusableWhenDisabled" in again and "disabled={busy || readOnly}" in again
    # The job page opens step 3 from it, as from Use resume as is.
    page = squash(_read(_JOB_PAGE))
    assert "onOpenTailored={() => { focusOpenedStep.current = true; setStep(\"output\"); }}" in page


def test_the_gap_page_s_step_line_describes_the_analysis_on_screen():
    """The gap page's step 2 line read the analysis that made the job's draft ("7 answered, 1 skipped") while the page
    below it showed a newer one ("3 answered, 7 open"). The page hands the hook its own analysis and its working copy
    of the answers, so the line and the footer count the same gaps as they change (lib/job-steps.ts `shown`)."""
    page = squash(_read(_GAP_PAGE))
    assert ("const shownAnalysis = session.data?.status === \"open\" ? { base_resume: session.data.base_resume, "
            "gapIds: session.data.gaps_json.categories.flatMap((c) => c.gaps.map((g) => g.gap_id)), "
            "resolutions, } : null;") in page
    assert "useJobSteps(jobId, jobDetail.data, shownAnalysis);" in page
    # `resolutions` is the working copy (edited ?? stored), declared before the hook reads it.
    src = _read(_GAP_PAGE)
    assert src.index("const resolutions: Resolution[] = edited ??") < src.index("const shownAnalysis =")
    hook = squash(_read(_STEPS_HOOK))
    assert "export function useJobSteps(jobId: string, detail: JobDetail | undefined, shown?: ShownAnalysis | null)" in hook
    assert "countGaps: gapCounts, shown," in hook


def test_a_resume_pick_is_a_preview_and_the_writes_confirm():
    """A pick changes only the chip, the summary and the body. The actions that write with another resume than
    the job's (Analyze gaps, Continue gap analysis, Restart gap analysis, Use resume as is) ask first, through
    the one hook the gap page shares (Task 11), in words that match the job's state (lib/resume-pick.ts)."""
    step = _read("components/resume-step.tsx")
    assert "onPick={setChosen}" in step and "confirmSwitch" not in step[step.index("onPick=") - 200 : step.index("onPick=")]
    assert "const switcher = useResumeSwitch({ jobId, application, sessions: sessions.data ?? [] });" in step
    # Continue stays a link while nothing would be replaced; else the confirm goes first (the lead card's action).
    cont = step[step.index('label: "Continue gap analysis",') : step.index("secondary: answered === 0")]
    assert "// A link while nothing would be replaced" in cont and "href: `/jobs/${jobId}/tailor/${openSession.id}`," in cont
    assert 'if (!switcher.switchWords(pickedSlug, "continue")) return;' in cont and "event.preventDefault();" in cont
    assert "void switcher.continueOn(pickedSlug, openSession.id);" in cont
    # Use resume as is: the switch words for another resume; the old Replace draft words for the same one.
    hook = _read("hooks/use-resume-switch.ts")
    as_is = hook[hook.index("const confirmAsIs = async") : hook.index("/** Analyze gaps")]
    assert 'if (switchWords(slug, "as_is")) return confirmSwitch(slug, "as_is", returnFocus);' in as_is
    assert "if (!application?.customized_json) return true;" in as_is
    assert as_is.index('confirmSwitch(slug, "as_is"') < as_is.index("asIsOverDraftConfirm(applied)")
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
    # Tailor on another resume never asks: Analyze gaps or Continue asked on the way to the gap page.
    assert "Switch and tailor" not in words and 'if (action === "tailor") return null;' in words
    # Once applied, re-tailoring the same resume still asks; Use resume as is keeps its own words, "resume" once applied.
    # Only the gap page's Tailor replaces the draft: Analyze gaps and Continue never ask about the same resume.
    assert 'if (state !== "applied" || action !== "tailor") return null;' in words
    assert "description: `You applied with ${from}. Tailoring again replaces that resume and its PDF. Version history keeps them.`," in words
    assert 'confirmLabel: "Tailor again",' in words
    assert 'const noun = applied ? "resume" : "draft";' in words and "title: `Replace the existing tailored ${noun}?`," in words
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


def test_no_step_is_locked_and_a_future_step_shows_no_made_up_number():
    """Design refresh Task 4.3: a step says one number from the data ("18 skills", "6 of 6 closed", "72.3 → 84.0"),
    no sentences, so a later step's hint ("After Create PDF") went with the lines. A later step with nothing to show
    is still plain text, never locked."""
    page = _read(_JOB_PAGE)
    steps = _read("components/job-steps.tsx")
    # A later step with nothing to show is plain text: not a button, never disabled, no lock, no tooltip.
    cell = steps[steps.index("              ) : (\n                <div") : steps.index("</li>")]
    assert '<div className={cn(CELL, busy && "opacity-50")}' in cell and "<button" not in cell and "tabIndex" not in cell
    # Never natively disabled; `aria-disabled` only while the gap page's write runs (it stays focusable).
    assert not re.search(r"(?<!aria-)disabled=", steps)
    assert "title=" not in steps and "Lock" not in steps and "Tooltip" not in steps
    for gone in ("LOCKED_REASON", "lockedReasonId", "CONCEPT_ICONS.locked", "aria-describedby", "Unlocks after you tailor"):
        assert gone not in page, gone
    # No sentence under a step: its one number, or nothing where the data has none (lib/job-steps.ts, node-tested).
    lib = _read("lib/job-steps.ts")
    assert "summary" not in lib and "metric: string | null;" in lib
    for hint in ("Review the changes, edit, Create PDF", "After Create PDF", "Pick a resume and analyze its gaps"):
        assert hint not in lib, hint
    assert "{step.metric ? (" in steps
    # A link to step 3 or 4 before the job has its own resume shows a panel that says so, and points at step 2.
    assert '<p>Nothing tailored yet.</p>' in page and "Go to Resume and gaps" in page
    assert page.count('<NothingTailoredYet onOpenFit={() => setStep("fit")} />') == 2


def test_a_step_with_something_to_show_is_a_button():
    """Step 3 with a draft (one from before a re-analysis too) and step 4 whenever the job has an application
    are buttons: `reachable` in lib/job-steps.ts (node-tested) decides, and the stepper honours it."""
    page = _read(_JOB_PAGE)
    steps = _read("components/job-steps.tsx")
    assert "const button = step.reachable || step.state !== \"next\";" in steps and "{button ? (" in steps
    # The hook hands the builder the application itself, so `hasApplication` and the draft come from it.
    hook = _read(_STEPS_HOOK)
    assert "const application = detail?.application ?? null;" in hook
    assert "jobStepsInput({" in hook and "    application,\n" in hook
    assert "useJobSteps(id, data)" in page


def test_the_steps_read_the_details_own_stage():
    """The detail sends the rung beside `job` (schemas/job_detail.py), and the nested JobRead carries none: a page
    that read `data.job.stage` saw every job as saved, so step 2 was always current and step 4 never was."""
    detail = (Path(knockout.__file__).parents[1] / "schemas/job_detail.py").read_text(encoding="utf-8")
    assert "    job: JobRead\n" in detail and "    stage: Rung\n" in detail
    # The type says so: the detail's `job` leaves the rung out, so `detail.job.stage` does not compile, and the
    # builder takes the rung from the detail itself.
    types = _read("lib/types.ts")
    detail_type = types[types.index("export interface JobDetail {") :]
    detail_type = detail_type[: detail_type.index("\n}")]
    assert 'job: Omit<Job, "stage" | "open_session_id" | "gaps_done" | "gaps_total">;' in detail_type
    for field in ("stage?: Rung;", "open_session_id?: UUID | null;", "gaps_done?: number;", "gaps_total?: number;"):
        assert field in detail_type, field
    lib = _read("lib/job-steps.ts")
    assert 'rung: Pick<JobDetail, "stage" | "open_session_id" | "gaps_done" | "gaps_total">;' in lib
    assert "jobWithStage" not in lib
    assert "rung: detail," in _read(_STEPS_HOOK)
    page = _read(_JOB_PAGE)
    assert 'const stage = data.stage ?? "saved";' in page
    for rel in (_JOB_PAGE, _GAP_PAGE, _STEPS_HOOK):
        assert "job.stage" not in _read(rel), rel


def test_step_one_reads_the_knockout_card_words():
    hook = _read(_STEPS_HOOK)
    assert 'import { knockoutWords } from "@/lib/knockout-line";' in hook
    # Now the Job description fold's summary (design refresh Task 4.3): the step's own number is the skills.
    assert ("const jobLine = jobFacts( skillCount, knockoutWords( detail.knockout?.status ?? null, "
            "detail.knockout ? knockoutNotChecked(detail.knockout, job) : false, ), );") in squash(hook)
    assert 'title="Job description" summary={jobLine}' in squash(_read(_JOB_PAGE))


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
    # Step 1's details are open by default on every stage (owner, 2026-10-16); Hide details is the reader's choice.
    assert "const [detailsOpen, setDetailsOpen] = useState(true);" in page
    assert 'setDetailsOpen(stage === "saved")' not in page


def test_the_rare_actions_sit_behind_one_more_actions_menu():
    page = _read(_JOB_PAGE)
    # The loaded header (the loading one draws only Back and the morphing pair, design refresh Task 4.5).
    start = page.rindex("<header", 0, page.index("<DropdownMenu>"))
    header = page[start : page.index("</header>", start)]
    menu = header[header.index("<DropdownMenu>") : header.index("</DropdownMenu>")]
    items = [m.strip() for m in re.findall(r"\n\s*(?:\{promote\.isPending \? \"Queueing…\" : \"(Queue in Agent inbox)\"\}|\{reExtract\.isPending \? \"Refreshing…\" : \"(Refresh details)\"\}|(Delete job))", menu) for m in m if m]
    assert items == ["Queue in Agent inbox", "Refresh details", "Delete job"], items
    assert menu.count("<DropdownMenuItem") == 3 and 'label="More actions"' in menu
    assert menu.count("returnFocus: moreTrigger,") == 2  # each confirm returns to ⋯
    # Out of the header: the application's details are the Details and history fold (design refresh Task 4.3);
    # nothing else is an icon-only delete.
    assert "<ApplicationDetailsMenu" not in header and 'label="Delete job"' not in page
    assert page.index('{visited.has("qa") ? (') < page.index("<ApplyStep")
    fold = page[page.index('title="Details and history"') :]
    assert "{historyOpen && application ? (" in fold and "<ApplicationDetails" in fold
    assert "ApplicationDetailsMenu" not in _read("components/application-panel.tsx")
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
    step = _read(_STEP_THREE)
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
    assert 'toast.info("This job is already saved.");' in _read("app/new/page.tsx")


def test_save_job_opens_the_job_on_resume_and_gaps():
    """Save job left /new as it was and drew a summary card under the form, at or below the fold, so a save looked like
    nothing happened. The job is scored on save, so Save job opens it on step 2 (Resume and gaps), a new job or one
    already saved, and the toast says which. The button stays pending until the job page takes over."""
    page = _read("app/new/page.tsx")
    on_success = page[page.index("onSuccess: (job) => {") : page.index("onError:", page.index("onSuccess: (job) => {"))]
    assert on_success.index("toast.") < on_success.index("router.push(`/jobs/${job.id}?tab=fit`);")
    assert "JobExtractionSummary" not in page and "openResumeAndGaps" not in page
    assert not (_FRONTEND / "components/job-extraction-summary.tsx").exists()
    assert "const busy = extractJob.isPending || extractJob.isSuccess;" in page
    assert '{extractJob.isSuccess ? "Opening the job…" : extractJob.isPending ? "Saving…" : "Save job"}' in page
    assert "pending={busy}" in page


def test_the_tracker_says_where_agent_jobs_are():
    """The subtitle that said so went (owner decision D1); the source toggle under Filters says it in its
    segments, Tracked (your saved jobs and every application) and Agents."""
    page = _read("app/applications/page.tsx")
    assert "subtitle=" not in page
    assert 'allLabel="Tracked"' in page and 'if (next === "agent") void qc.prefetchQuery(savedJobsQuery("agent"));' in page


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
        ("lib/resume-pick.ts", '"Version history keeps the old one.",'),
        ("components/resume-step.tsx", '"It replaces any tailored draft (Version history keeps it) " +'),
        (_GAP_PAGE, "Your changes here won&apos;t be saved."),
        (_GAP_PAGE, "You can review and undo each change afterward."),
        ("components/settings/autofill-coverage-card.tsx", ", including which sites they were on and when.`"),
        ("components/settings/autofill-coverage-card.tsx", '" You can\'t undo this." +'),
        ("components/application-panel.tsx", "This deletes its tailored resume, answers and PDF. The job stays saved."),
        ("components/qa-tab.tsx", "A new letter replaces the saved one, including any edits you made to it."),
        ("components/resume-step.tsx", "and closes any open proposal in your Agent inbox for this job."),
    ],
)
def test_a_safety_sentence_survives(rel: str, sentence: str):
    assert sentence in _read(rel)


def test_the_searchable_list_kind_keeps_its_own_word():
    card = _read("components/settings/autofill-coverage-card.tsx")
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
        "components/tailored-resume-step.tsx",
        "components/qa-tab.tsx",
        "app/analytics/page.tsx",
        "components/analytics/applications-funnel.tsx",
        "components/analytics/search-tiles.tsx",
        "components/analytics/jobs-you-saved.tsx",
        "components/analytics/how-counted.tsx",
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
    # "Match" on the board; each meter is named "Match score" (or "Best match score") for a screen reader.
    page = _read("app/applications/page.tsx")
    assert '>Match</TableHead>' in page and '"Match score"' in page


def _button_tags(src: str) -> list[str]:
    """Each Button's whole opening tag (`open_tag` skips braces and the `>` of `=>`)."""
    return [open_tag(src[m.start() :], "Button") for m in re.finditer(r"<Button(?=[\s/>])", src)]


def _slice(src: str, start: str, end: str) -> str:
    return src[src.index(start) : src.index(end, src.index(start))]


def test_step_three_has_one_filled_button_and_the_pdf_card_carries_its_actions():
    src = _read(_STEP_THREE)
    step = _slice(src, "export function TailoredResumeStep(", "function ChangesList(")
    # One filled button, the lead card's action (design refresh Task 4.3): Create PDF before a PDF, Continue to
    # Apply once one exists (the two arms of one ternary). No Button in the file is filled by hand.
    assert all("variant=" in t for t in _button_tags(src)), [t for t in _button_tags(src) if "variant=" not in t]
    filled = squash(step[step.index("const filled: LeadAction = hasPdf") : step.index("const updatePdf")])
    assert '? { label: "Continue to Apply", onClick: () => onOpenStep("qa") }' in filled
    assert ": { label: renderPdf.isPending ? pdfWords.pending : pdfWords.label," in filled
    assert "onClick: () => renderOnce(), pending: renderPdf.isPending, disabled: busy || readOnly," in filled
    assert '<LeadCard eyebrow="Tailored resume" action={filled}' in squash(step)
    # Edit resume sits beside it, an outline link; the page no longer places it above the step.
    beside = step[step.index("secondary={") : step.index("</LeadCard>")]
    assert "<Link href={`/applications/${app.id}/resume`}>" in beside and 'variant="outline"' in beside
    assert "Edit resume" not in _read(_JOB_PAGE)
    # The PDF card: the file's own actions as named icon buttons, then Update PDF (small, outline).
    card = _slice(src, "function PdfCard(", "function TailoredResumeMenu(")
    assert "<PdfFileLine app={app} note={<ResumesFolderNote copyMissed={copyMissed} />} actions={update} />" in card
    line = _read("components/pdf-file-line.tsx")  # step 4 shows the same line
    for name in ('label="Download PDF"', 'label="Open PDF in new tab"'):
        assert name in line
    assert "<ShowCopyButton applicationId={app.id} variant=\"ghost\" iconOnly />" in line and "{actions}" in line
    update = [t for t in _button_tags(step) if "renderOnce()" in t and "variant=" in t]
    assert len(update) == 1 and 'variant="outline"' in update[0] and 'size="sm"' in update[0]
    # canvas is only the ground the preview paints: the card's own line sits on surface-container-low.
    assert "bg-canvas" not in src
    # The rare actions sit behind the lead card's ⋯.
    menu = src[src.index("function TailoredResumeMenu(") :]
    assert 'label="More actions for the tailored resume"' in menu
    assert 'onClick={() => onOpenStep("fit")}' in menu and "Tailor again" in menu and "Delete application" in menu
    # The full compare (each skill Gained, Lost or Same, Update score): a disclosure under the compact one, frameless.
    toggle = open_tag(step[step.rindex("<Button", 0, step.index("Score breakdown\n")) :], "Button")
    assert "aria-expanded={breakdownOpen}" in toggle and "aria-controls={breakdownId}" in toggle
    assert "<div id={breakdownId} hidden={!breakdownOpen}" in step
    assert "<AtsComparePanel app={app} jobId={jobId} readOnly={readOnly} bare />" in step
    # A failed Create PDF says so without naming an action it may not have been.
    assert "Creating the PDF failed. Try again." in step


def test_step_four_is_one_lead_card_with_the_details_folded():
    """Design refresh Task 4.3: step 4 is the page's lead card. The job's resume (its page, band and square), its Match
    score with the gain over its base resume, where the job stands, Open the job post (the one filled button), Mark
    applied (outline) and two tonal rows that open the cover letter and the application questions; History under it.
    What was submitted and the application's details are page folds."""
    src = _read("components/apply-step.tsx")
    flat = squash(src)
    # The job post opens in a new tab: its apply link, else its source link; without either, Mark applied is filled.
    assert "const postHref = job.apply_url || job.source_url || null;" in src
    assert '{ label: "Open the job post", icon: <ExternalLink className="size-4" />, href: postHref, external: true }' in flat
    lead = _read("components/ui/lead-card.tsx")
    assert '<a href={action.href} target="_blank" rel="noopener noreferrer" onClick={onClick} />' in lead
    # "and apply" was a promise to drop once applied; the label never makes it now, and the eyebrow says Ready to
    # apply only while the application is a draft.
    assert "Open the job post and apply" not in src
    assert 'eyebrow={isDraft ? "Ready to apply" : "Your application"}' in src
    # One filled button, the card's action: no Button in the step or the parts it lays out is filled by hand. The
    # cover letter editor's Save shows inside the card while a letter is open for editing, so it is tonal
    # (test_frontend_one_filled_button.py).
    qa = _read("components/qa-tab.tsx")
    filled = [t for t in _button_tags(src) + _button_tags(qa) if "variant=" not in t]
    assert filled == [], filled
    assert 'variant="tonal"' in next(t for t in _button_tags(qa) if "await onSave(draft)" in t)
    assert "{isDocument && editing ? (" in qa
    for click in ("onClick={() => askOnce(questions)}", "onClick={() => void generateCoverLetter()}"):
        assert 'variant="outline"' in next(t for t in _button_tags(qa) if click in t), click
    # Mark applied is the header chip's transition through the page's one guarded starter, and shows only while
    # the job is a draft; its line says what it sets and where the later statuses are.
    page = _read(_JOB_PAGE)
    assert "const setStatus = useSingleFlight(patch.mutate);" in page
    assert "onSelect={(status) => setStatus({ status })}" in page and "setStatus={setStatus}" in page
    assert 'setStatus({ status: "applied" });' in src and "patch" not in src
    mark = open_tag(src[src.rindex("<Button", 0, src.index("aria-describedby={markHintId}")) :], "Button")
    assert 'variant="outline"' in mark and "pending={statusPending}" in mark and "onClick={mark}" in mark
    assert "postHref && isDraft ? (" in src and src.count('{applying ? "Applying…" : "Mark applied"}') == 1
    assert 'label: applying ? "Applying…" : "Mark applied",' in src  # filled, when there is no job post to open
    assert "Sets today as the applied date." in src
    assert "Interviewing, Offer and Rejected come after, on the status chip." in src
    # The rows are headings, and each opens its editor (a real disclosure); the parts carry no title of their own.
    for title in ("Application questions", "Cover letter"):
        assert f'title="{title}"' in src, title
    assert '<h2 id={titleId} className="min-w-0 flex-1 text-title-small">{title}</h2>' in src
    row = src[src.index("function ApplyRow(") : src.index("export function ApplyStep(")]
    assert 'variant="tonal"' in row and "aria-expanded={open}" in row and "aria-controls={panelId}" in row
    assert "<div id={panelId} hidden={!open}" in row
    assert ">History</h2>" in qa and ">Cover letter</h2>" not in qa and ">Application questions</h2>" not in qa
    # The cover letter's row says whether one is written, only once the answers loaded.
    assert 'note={facts.hasCoverLetter === undefined ? null : facts.hasCoverLetter ? "Written" : "Not written"}' in src
    assert "hasCoverLetter: entries === undefined ? undefined : hasCoverLetter," in qa
    # The score is the draft's, with the gain over its base resume only when both are scored.
    assert "const gain = score?.score != null && score.base != null ? score.score - score.base : null;" in src
    assert "<DeltaChip value={gain} />" in src and "Match score" in src
    # The resume's square belongs on this card (D2): the band, the page and the name on the resume's tint.
    thumb = _read("components/tailored-resume-thumb.tsx")
    assert '<div aria-hidden="true" className="h-1.5 shrink-0 bg-resume" />' in thumb
    assert "<ResumeTag hue={hue}" in thumb and "bg-resume-container" in thumb and "style={resumeColorStyle(hue)}" in thumb
    assert "<TailoredResumeThumb app={app} hue={resume.hue} name={resume.name} tailored={resume.tailored} />" in src
    # The application's details: the page's Details and history fold, mounting the fields only while open (each
    # open reseeds them from the server), and a blur saves only a field that changed.
    assert "const [historyOpen, setHistoryOpen] = useState(false);" in page
    assert "{historyOpen && application ? ( <ApplicationDetails" in squash(page)
    panel = " ".join(_read("components/application-panel.tsx").split())
    assert "if (appliedAt !== formatDateInput(app.applied_at)) onPatch({ applied_at: toIsoDate(appliedAt) });" in panel
    assert 'if (notes !== (app.notes ?? "")) onPatch({ notes });' in panel
    assert "each open reseeds the fields from the server, so a stale local note can never overwrite" in panel
    # No PDF line and no preview: step 3 holds the PDF and its download (owner, 2026-10-16).
    assert "PdfFileLine" not in src and "PdfPagesPreview" not in src
    # QASections keeps the state, and `arrange` is required.
    assert "arrange={({ questions, coverLetter, history, facts }) => (" in src
    assert "arrange: (parts: QAParts) => ReactNode;" in qa and "arrange = " not in qa
    assert "questions: questionsPart," in qa and "coverLetter: coverLetterPart," in qa
    # The receipt's "Cover letter attached" jumps to the letter's History entry, not the card that writes one.
    assert "jumpId={isLetterTarget ? COVER_LETTER_ID : undefined}" in qa and "id={jumpId}" in qa
    assert "Edit it or create its PDF in History." in qa
    # Edit resume lives on step 3; the Companion button waits for a way to tell it is paired.
    assert "Edit resume" not in src and "Let the Companion fill it" not in src


def test_step_three_change_rows_read_and_revert_one_by_one():
    src = _read(_STEP_THREE)
    rows = _slice(src, "function ChangesList(", "function PdfCard(")
    # Five changes, then the rest behind one toggle; once a PDF exists only the rows fold.
    assert "const SHOWN_CHANGES = 5;" in src and "`Show ${hunks.length - SHOWN_CHANGES} more changes`" in rows
    assert "const listOpen = listShown ?? !hasPdf;" in rows and "aria-expanded={listOpen}" in rows
    fold = _slice(rows, "<div id={listId} hidden={!listOpen}", "</section>")
    assert "No changes yet." not in fold and "Try again" not in fold
    # Check wording is the studio's (Edit resume); step 3 has no copy of it (owner, 2026-10-16).
    assert "Check wording" not in src and "runCoherenceCheck" not in src
    # Each row: where it sits (first, with an id the Revert button points at), the chip, what it was and is now.
    assert fold.index("{hunkPlace(hunk, draft)}") < fold.index("<ProvenanceChip value={hunk.provenance} tinted />")
    assert '<span className="sr-only">Before: </span>' in fold and "<del>" in fold
    assert '<span className="sr-only">Now: </span>' in fold and "<ins" in fold
    revert = open_tag(fold, "IconButton")
    assert 'label="Revert this change"' in revert and "aria-describedby={placeId}" in revert
    assert 'data-revert=""' in revert and "focusableWhenDisabled" in revert
    # Keys ignore position (lib/resume-diff `hunkIds`), so the neighbour that takes focus keeps its node.
    assert "<li key={id}" in fold and "const id = ids[position];" in fold and "hunkIds(hunks)" in src
    assert '<p className="sr-only" aria-live="polite">' in rows
    # A revert edits the draft the list describes, and never creates the PDF again behind your back.
    step = _slice(src, "export function TailoredResumeStep(", "function ChangesList(")
    # The diff names the draft it was computed from; a revert goes only against that one, and says so to the
    # server, which refuses it (409) if the row has moved since.
    assert "if (diff.data?.updated_at !== app.updated_at) {" in step
    assert 'toast.error("The changes were out of date and have been refreshed. Try again.");' in step
    assert "expected_updated_at: write.expectedUpdatedAt" in src
    # A new draft's list loads behind the previous one, and nothing in that stand-in can be reverted.
    assert "placeholderData: keepPreviousData" in step
    assert "const diffSettled = !diff.isPlaceholderData && !diff.isFetching;" in step
    assert "disabled={busy || readOnly || !diffSettled}" in step
    assert "diffData: diff.isPlaceholderData ? undefined : diff.data" in step
    assert "draftLoaded" not in _read(_JOB_PAGE) + src
    writes = _slice(src, "function useDraftWrites(", "export function TailoredResumeStep(")
    assert "renderOnce" not in writes and "render" not in writes.replace("re-render", "")
    assert "Create the PDF again when you are done." in writes
    assert "mutationKey: tailoredRescoreKey(app.id)," in writes
    # The diff is keyed on the draft it describes.
    api = _read("lib/api.ts")
    assert 'queryKey: ["resume-diff", application.id, application.updated_at],' in api


def test_step_three_says_provenance_in_the_studios_words():
    src = _read(_STEP_THREE)
    # One chip, the studio's: step 3 asks for it tinted.
    assert "ProvenanceTag" not in src and "PROVENANCE_TONE" not in src and "const PROVENANCE:" not in src
    assert "<ProvenanceChip value={value} tinted />" in src
    assert '"Yours"' not in src and '"From career history"' not in src
    review = _read("components/resume-editor/diff-review.tsx")
    assert "const PROVENANCE_CHIPS:" in review and "export function ProvenanceChip(" in review
    assert "className={tinted ? PROVENANCE_TONE[value] : undefined}" in review
    assert 'name: "From your career history"' in review and 'user: { kind: "you",' in review
    # The header's count is its own badge, read as a number of changes.
    assert '{count === 1 ? "1 change" : `${count} changes`}' in src
