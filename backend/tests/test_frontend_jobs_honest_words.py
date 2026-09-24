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
    assert 'label: "Nothing rules you out",' in card
    assert 'detail: "Nothing the job lists conflicts with your profile.",' in card
    assert "meet the listed" not in card and "match what the job lists" not in card


def test_an_unstated_knockout_says_what_it_could_not_check():
    # The salary and experience checks are omitted, not failed, when the profile lacks the answer.
    src = Path(knockout.__file__).read_text(encoding="utf-8")
    assert "if desired is None:\n        return None" in src
    assert "if job.years_experience_min is None or years_experience is None:\n        return None" in src
    card = _read("components/job-knockout-card.tsx")
    assert "\"Nothing here to check. That doesn't mean you qualify.\"" in card
    assert '`Can\'t check ${what} yet: add your ${fields}.`' in card
    assert 'job.salary_period === "year" || (job.salary_period == null && ceiling >= 10000)' in card
    assert 'anchorHref("/profile", "autofill-preferences")' in card
    assert 'anchorHref("/profile", "job-preferences-years")' in card
    assert "<JobKnockoutCard scan={data?.knockout} job={job} />" in _read(_JOB_PAGE)


def test_an_unrun_knockout_names_the_check_and_its_salary_field():
    """Which check, and which of the two salary fields it reads: knockout reads
    preferences.desired_salary (the Autofill tab's), not Job preferences' Minimum salary."""
    src = Path(knockout.__file__).read_text(encoding="utf-8")
    card = _read("components/job-knockout-card.tsx")
    assert "return `${what.charAt(0).toUpperCase()}${what.slice(1)} check: not run yet`;" in card
    assert 'label: "Not checked yet"' not in card
    assert '(preferences or {}).get("desired_salary")' in src
    assert 'field: "desired salary (Profile › Autofill)",' in card
    assert 'field: "years of experience (Profile › About you)",' in card


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
    assert "</span> answered\n" in page and "{done} of" not in page
    assert "{counts.open > 0 ? `${counts.open} open` : \"Nothing open\"}" in page
    panel = _read("components/ats-score-panel.tsx")
    assert "gapCounts(" in panel and "resolutions_json.length" not in panel
    assert "` (${answered} answered)`" in panel


def test_auto_filled_banner_names_the_job_s_own_words():
    page = _read(_GAP_PAGE)
    assert 'resolutionProvenance(r)?.source === "wording_auto"' in page
    assert "filled in with the job's own words" in page
    assert "filled in from your resumes and career history" in page


def test_the_gap_page_names_the_ats_score_and_every_action():
    page = _read(_GAP_PAGE)
    assert "· ATS score before tailoring:" in page
    intro = page[page.index("These gaps need your input.") :]
    intro = intro[: intro.index("</p>")]
    for action in ("Add keyword", "Answer", "Attach project", "Skip", "I can&apos;t confirm this"):
        assert f'<span className="font-medium">{action}</span>' in intro, action
    assert "→" not in page  # the score toast says "to"
    assert "`ATS score: ${base.composite.toFixed(1)} to ${tailored.composite.toFixed(1)}" in page


def test_gap_rows_read_whole_at_375():
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


# --- ATS score, spelled out as our estimate ---------------------------------------


def test_the_ats_score_is_our_estimate_everywhere_it_is_explained():
    words = _read("lib/ats-words.ts")
    assert (
        '"An ATS score (0 to 100) is our estimate of how an applicant tracking system would rate each resume for this job."'
        in words
    )
    assert "{ATS_SCORE_LEAD}" in _read("components/ats-score-panel.tsx")
    fit = _read("app/analytics/page.tsx")
    assert "{ATS_SCORE_LEAD_ALL_JOBS}" in fit
    assert fit.index("{ATS_SCORE_LEAD_ALL_JOBS}") < fit.index("<BaseSummaryCards />")
    conventions = " ".join((_FRONTEND.parent / "docs/frontend-conventions.md").read_text(encoding="utf-8").split())
    assert "our estimate of how an applicant tracking system would rate each resume for this job" in conventions


# --- One request per click, focus never on <body> ---------------------------------


@pytest.mark.parametrize(
    ("rel", "marker"),
    [
        ("components/ats-score-panel.tsx", "onClick={() => runOnce()}"),
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
    panel = _read("components/ats-score-panel.tsx")
    card = panel[panel.index("function AtsScoreCard(") : panel.index("export function AtsScorePanel(")]
    assert card.count("focusableWhenDisabled") >= 3  # Find gaps (or Start over), Mark applied
    assert "onAnalyze={() => createOnce(score.target_id)}" in panel


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


def test_locked_tabs_say_why_and_show_a_panel():
    page = _read(_JOB_PAGE)
    assert '"Your resume and answers appear here once you start a draft."' in page
    reason = "Resume and Q&A open once this job has its own resume: tailor one, use yours as is, or mark the job applied."
    assert f'const LOCKED_REASON =\n  "{reason}";' in page
    assert "{LOCKED_REASON}" in page and '"aria-describedby": reasonId,' in page
    assert "Unlocks after you tailor" not in page
    # With no application, both tabs still render a panel that says so.
    no_app = page[page.index("          ) : (\n            // A link to ?tab=output") :]
    no_app = no_app[: no_app.index("          )}")]
    assert no_app.count("<NoDraftYet onOpenFit={() => setTab(\"fit\")} />") == 2
    assert '<TabsContent value="output"' in no_app and '<TabsContent value="qa"' in no_app


def test_the_job_header_keeps_its_title_and_drops_empty_facts():
    page = _read(_JOB_PAGE)
    assert '<h1 className="text-[22px] font-medium tracking-tight break-words">' in page
    assert "jobMetaLine([" in page
    meta = _read("lib/job-meta.ts")
    assert 'if (!part || part === "Not stated") continue;' in meta and "if (seen.has(key)) continue;" in meta
    assert "jobMetaLine([" in _read("components/proposals/proposals-section.tsx")


def test_delete_job_names_the_proposals_it_deletes():
    # application_proposals.job_id is ON DELETE CASCADE.
    model = (Path(knockout.__file__).parents[1] / "models/application_proposal.py").read_text(encoding="utf-8")
    assert 'ForeignKey("jobs.id", ondelete="CASCADE")' in model
    assert '"This also deletes its application, ATS scores, gap analyses, answers and any Agent inbox proposals for it.",' in _read(_JOB_PAGE)


def test_mark_applied_hides_once_the_job_is_applied():
    panel = _read("components/ats-score-panel.tsx")
    assert "const applied = applicationStatus != null && applicationStatus !== \"draft\";" in panel
    assert "{applied ? null : (" in panel
    assert "<AtsScorePanel jobId={id} applicationStatus={application?.status ?? null} />" in _read(_JOB_PAGE)


def test_the_resume_tab_names_what_it_holds():
    panel = _read("components/application-panel.tsx")
    assert "<CardTitle>Resume for this job</CardTitle>" in panel
    assert "<CardTitle>Tailored resume</CardTitle>" not in panel
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
    assert ("such as Claude, Codex or the ChatGPT desktop app, using MCP "
            "(the standard way AI apps connect to tools).") in inbox
    assert "ready-made instructions for your agent" in inbox
    assert "May not accept OPT" in inbox


# --- Safety and consent sentences that a shortening must keep (review I9) ---------


@pytest.mark.parametrize(
    ("rel", "sentence"),
    [
        ("components/job-knockout-card.tsx", "That doesn't mean you qualify."),
        (_GAP_PAGE, "Version history keeps the old one."),
        ("components/ats-score-panel.tsx", '"It replaces any tailored draft (Version history keeps it) " +'),
        (_GAP_PAGE, "Your changes here won&apos;t be saved."),
        (_GAP_PAGE, "You can review and undo each change afterward."),
        ("components/analytics/autofill-coverage-card.tsx", ", including which sites they were on and when.`"),
        ("components/analytics/autofill-coverage-card.tsx", '" You can\'t undo this." +'),
        ("components/application-panel.tsx", "This deletes its tailored resume, answers and PDF. The job stays saved."),
        ("components/qa-tab.tsx", "A new letter replaces the saved one, including any edits you made to it."),
        ("components/ats-score-panel.tsx", "and closes any open proposal in your Agent inbox for this job."),
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
        "components/ats-score-panel.tsx",
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


def test_the_score_tab_name_is_sentence_case():
    assert '<TabsTrigger value="fit">Score and tailor</TabsTrigger>' in _read(_JOB_PAGE)


# ── Unreadable job dates (Task 25): said plainly, with a format that works ──────


def test_the_score_tab_says_why_undated_jobs_score_low():
    """First-read pass: "Recent experience 11" with dates like 2021-03 and no word of why.
    The engine reads "Mon YYYY" only (accepting more is §11: it moves ATS scores)."""
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
    panel = _read("components/ats-score-panel.tsx")
    assert "{datesUnreadable(score.subscores_json.format_flags) && (" in panel
    assert "<p className=\"text-muted-foreground text-xs\">{UNREADABLE_DATES_NOTE}</p>" in panel
    # "11 of 100", not a bare 11.
    assert '<span className="text-muted-foreground font-normal"> of 100</span>' in panel


def test_a_skill_with_no_example_never_contradicts_mentioned_in():
    """"Skills with no example" beside "Mentioned in: Northwind" read as a contradiction:
    the entries were found, but their dates can't be read, so only the skills list counts."""
    words = _read("lib/ats-words.ts")
    assert 'return placement === "skills_list_only" && entries.length > 0;' in words
    assert "These don't count as examples yet because we can't read a date on them." in words
    card = _read("components/gap-analysis/gap-card.tsx")
    assert "const undated = undatedEvidence(diagnostic.placement, entries);" in card
    assert "{undated ? <p className=\"text-muted-foreground basis-full text-xs\">{UNDATED_EVIDENCE_NOTE}</p> : null}" in card
