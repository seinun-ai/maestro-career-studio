"""Small motion that confirms (visual-language plan, Task 15; owner's motion budget D9)."""

import re
from pathlib import Path

from tests.node_ts import run_node_test

_CSS = (Path(__file__).resolve().parents[2] / "frontend/app/globals.css").read_text()
_UTILITIES = _CSS.split("@layer utilities", 1)[1].split("@media (prefers-reduced-motion", 1)[0]


def test_count_up_node_suite():
    result = run_node_test("lib/count-up.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_motion_utilities_exist_and_stay_within_budget():
    assert "@utility animate-confirm" in _CSS and ".collapse-exit" in _CSS
    assert "confirm-ring var(--duration-medium4)" in _CSS
    assert ".animate-row-exit" not in _CSS
    assert "[data-leaving]" in _UTILITIES
    for decl in re.findall(r"[^;{}]*\b\d+ms\b[^;{}]*", _UTILITIES):
        for ms in map(int, re.findall(r"(\d+)ms", decl)):
            # Over 400 only as a loop that says "still going", not a change: the skeleton shimmer
            # (1400) and the working dots (900).
            assert ms <= 400 or (ms in (900, 1400) and "infinite" in decl), decl


def test_no_bounce_curve_is_introduced():
    assert "cubic-bezier(0.34, 1.56" not in _CSS and "bounce" not in _CSS.lower()


def test_collapse_exit_clips_only_while_leaving():
    # At rest the child must not clip focus rings, shadows or popovers.
    rest = re.search(r"\.collapse-exit > \*\s*\{([^}]*)\}", _UTILITIES).group(1)
    assert "overflow" not in rest and "min-height: 0" in rest
    leaving = re.search(r"\.collapse-exit\[data-leaving\] > \*\s*\{([^}]*)\}", _UTILITIES)
    assert leaving and "overflow: hidden" in leaving.group(1)


_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _ms(var: str) -> int:
    return int(re.search(rf"--{var}:\s*(\d+)ms", _CSS).group(1))


def _motion() -> str:
    return (_FRONTEND / "lib/motion.ts").read_text()


def _const(name: str) -> int:
    return int(re.search(rf"export const {name} = (\d+);", _motion()).group(1))


def test_motion_module_holds_the_budget_and_matches_the_tokens():
    assert _const("CONFIRM_HOLD_MS") == 1200
    assert _const("CONFIRM_MS") == _ms("duration-medium4")
    assert _const("ROW_EXIT_MS") == _ms("duration-short4")


def test_motion_constants_are_imported_not_redeclared():
    for rel, name in {
        "hooks/use-copy.ts": "CONFIRM_HOLD_MS",
        "hooks/use-saved-hold.ts": "CONFIRM_HOLD_MS",
        "components/status-chip.tsx": "CONFIRM_MS",
        "components/proposals/proposals-section.tsx": "ROW_EXIT_MS",
    }.items():
        src = (_FRONTEND / rel).read_text()
        assert re.search(rf'import \{{[^}}]*\b{name}\b[^}}]*\}} from "@/lib/motion"', src), rel
        assert not re.search(r"\b(1200|400|200)\b", re.sub(r"//.*|/\*.*?\*/", "", src)), rel
    assert "SAVED_HOLD_MS" not in (_FRONTEND / "components/settings/autosave-status.tsx").read_text()
    page = (_FRONTEND / "app/jobs/[id]/tailor/[sessionId]/page.tsx").read_text()
    assert "useSavedHold(" in page and "SAVED_HOLD_MS" not in page
    assert "export const ROW_EXIT_MS" not in (_FRONTEND / "components/proposals/triage-actions.tsx").read_text()


def test_every_motion_token_is_within_budget():
    root = _CSS.split(":root", 1)[1]
    used = set(re.findall(r"var\(--(duration-[\w-]+)\)", _UTILITIES))
    for block in re.findall(r"@utility animate-[\w-]+\s*\{[^}]*\}", _CSS):  # animate-confirm, animate-check-draw
        used |= set(re.findall(r"var\(--(duration-[\w-]+)\)", block))
    assert "duration-medium4" in used and "duration-short4" in used
    for token in used:
        assert re.search(rf"--{token}:\s*(\d+)ms", _CSS), token
        assert _ms(token) <= 400, token
    assert root


def test_count_up_default_is_within_budget_and_continues_from_the_screen():
    hook = (_FRONTEND / "hooks/use-count-up.ts").read_text()
    assert int(re.search(r"ms = (\d+)", hook).group(1)) <= 400
    step = hook[hook.index("const step"): hook.index("frame = requestAnimationFrame(step);\n    return")]
    assert "from.current = v" in step  # the value on screen, written inside the frame callback
    effect = hook[hook.index("useEffect("): hook.index("const reduce")]
    assert "setShown" not in effect and "from.current = target" not in hook


def test_number_roll_and_working_dots_stay_in_budget_and_respect_reduced_motion():
    """Design refresh Task 0.6: a number rolls, the AI says it is working, a save draws its check."""
    roll = (_FRONTEND / "components/visual/number-roll.tsx").read_text()
    assert "ROLL_MS" in roll and "translate" in roll and "aria-live" not in roll  # the parent announces
    assert "useReducedMotion" in roll or "prefers-reduced-motion" in roll
    assert 'import { ROLL_MS } from "@/lib/motion"' in roll and "400" not in roll
    assert "transition-[translate]" in roll and "transform" not in roll
    dots = (_FRONTEND / "components/visual/working-dots.tsx").read_text()
    assert 'role="status"' in dots and "working-dot" in dots
    # Spoken however it is mounted: the region is in the page, empty, before its words are written.
    assert '<span ref={region} role="status" className="sr-only" />' in dots
    assert "node.textContent = label;" in dots and "SPEAK_AFTER_MS" in dots
    assert '<span aria-hidden="true">{label}</span>' in dots
    reduced = _CSS.split("@media (prefers-reduced-motion", 1)[1]
    assert ".working-dot" in reduced and "animate-check-draw" in reduced


def test_visual_primitives_node_suite():
    """The day strip's ends name its oldest dot's day, and the working dots' region mounts empty
    (components/visual/visual.test.mjs)."""
    result = run_node_test("components/visual/visual.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_roll_ms_is_the_number_token_and_the_check_draws_in_budget():
    assert _const("ROLL_MS") == _ms("duration-medium4")
    draw = re.search(r"@utility animate-check-draw\s*\{([^}]*)\}", _CSS)
    assert draw, "animate-check-draw is a registered utility, so variants apply"
    assert "stroke-dasharray: 24" in draw.group(1)
    assert "var(--duration-medium2)" in draw.group(1) and "var(--ease-out-strong)" in draw.group(1)
    assert "@keyframes check-draw" in _UTILITIES and "@keyframes working-dot" in _UTILITIES
    check = (_FRONTEND / "components/visual/check-draw.tsx").read_text()
    assert "animate-check-draw" in check and 'pathLength="24"' in check


# --- Design refresh Task 4.5: motion where something happens ---------------------------------------------------------

_REDUCED = _CSS.split("@media (prefers-reduced-motion", 1)[1]


def _src(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def test_a_status_cross_fades_with_a_2px_blur_then_pulses_once():
    chip = _src("components/status-chip.tsx")
    assert 'import { CONFIRM_MS, FADE_MS } from "@/lib/motion";' in chip
    assert 'className="animate-status-out col-start-1 row-start-1"' in chip
    assert 'className="animate-status-in col-start-1 row-start-1"' in chip
    # The old label leaves after the fade; the pulse waits for the fade's end, then runs once.
    assert "window.setTimeout(() => setLeaving(null), FADE_MS);" in chip
    assert "Math.max(0, fadeEnds.current - performance.now())" in chip
    assert '"data-confirm:animate-confirm"' in chip
    for name, frames in (("status-in", "from"), ("status-out", "to")):
        utility = re.search(rf"@utility animate-{name}\s*\{{([^}}]*)\}}", _CSS)
        assert utility and f"animation: {name} var(--duration-short4) var(--ease-out-strong) both;" in utility.group(1)
        keyframes = re.search(rf"@keyframes {name}\s*\{{\s*{frames}\s*\{{([^}}]*)\}}", _UTILITIES)
        assert keyframes and "opacity: 0;" in keyframes.group(1) and "filter: blur(2px);" in keyframes.group(1)
    assert _const("FADE_MS") == _ms("duration-short4")


def test_a_region_that_waits_on_ai_shows_the_working_dots_not_a_spinner():
    """A button keeps its `pending` spinner; a region that waits on the AI says so with WorkingDots."""
    passes = _src("components/resume-health/question-pass.tsx")
    assert '<WorkingDots label="Writing new wording"' in passes and "Loader2" not in passes
    qa = _src("components/qa-tab.tsx")
    history = qa[qa.index("const history = (") : qa.index("return arrange({")]
    assert '{askQuestions.isPending ? <WorkingDots label="Answering your questions" className="flex" /> : null}' in history
    assert '{coverLetter.isPending ? <WorkingDots label="Writing your cover letter" className="flex" /> : null}' in history
    # The buttons that started them keep their own spinner and words.
    assert 'pending={askQuestions.isPending}' in qa and '{askQuestions.isPending ? "Answering…" : "Answer questions"}' in qa
    assert 'pending={coverLetter.isPending}' in qa and '{coverLetter.isPending ? "Writing…" : "Write cover letter"}' in qa


def test_saved_draws_its_check_where_saved_holds():
    for rel in ("components/settings/autosave-status.tsx", "app/jobs/[id]/tailor/[sessionId]/page.tsx"):
        src = _src(rel)
        assert "useSavedHold(" in src and '<CheckDraw className="size-3" />' in src, rel


def test_whole_numbers_roll_and_a_decimal_score_counts():
    """NumberRoll for a whole number that changes in place; useCountUp keeps the one decimal it runs (the Match
    score, and Analytics' decimal tiles: applied per week and the score gain, design refresh Task 5.2). Analytics'
    whole numbers (the funnel's counts, the tiles' days and counts) roll."""
    users = sorted(
        str(path.relative_to(_FRONTEND)) for path in _FRONTEND.glob("**/*.tsx")
        if "node_modules" not in path.parts and "useCountUp(" in path.read_text(encoding="utf-8")
    )
    assert users == ["components/analytics/search-tiles.tsx", "components/score-summary.tsx"], users
    assert "const shownScore = useCountUp(score.composite);" in _src("components/score-summary.tsx")
    tiles = _src("components/analytics/search-tiles.tsx")
    assert "const shown = useCountUp(value);" in tiles
    assert "<CountedDecimal value={summary.applied_per_week} />" in tiles and "<NumberRoll value={quiet.count} />" in tiles
    assert "<NumberRoll value={row.count}" in _src("components/analytics/applications-funnel.tsx")
    assert "<NumberRoll value={count.value}" in _src("components/proposals/inbox-counts.tsx")


_MORPH_SITES = ("app/applications/page.tsx", "app/jobs/[id]/page.tsx")


def test_the_row_to_page_morph_names_only_the_monogram_and_the_title():
    morph = _src("components/job-morph.tsx")
    assert 'import { ViewTransition, type ReactElement } from "react";' in morph
    # Only the named pair morphs: no transition of its own otherwise, and `share` is what pairs them.
    assert '<ViewTransition name={morphName(jobId, part)} share="job-morph" default="none">' in morph
    assert 'part: "monogram" | "title";' in morph
    names = _src("lib/view-transition.ts")
    assert 'export function morphName(jobId: string, part: "monogram" | "title"): string' in names
    # The pair lives in one place: no other ViewTransition, and no hand-set view-transition-name.
    for path in _FRONTEND.glob("**/*.tsx"):
        if "node_modules" in path.parts or path.name == "job-morph.tsx":
            continue
        text = path.read_text(encoding="utf-8")
        assert "<ViewTransition" not in text and "viewTransitionName" not in text, path
    for rel in _MORPH_SITES:
        parts = re.findall(r'<JobMorph jobId=\{[^}]+\} part="(\w+)"', _src(rel))
        assert parts and set(parts) == {"monogram", "title"}, (rel, parts)
    row = _src("app/applications/page.tsx")
    assert row.count("<JobMorph") == 2
    # 250ms, a strong ease-out; only the pair moves (the page itself swaps), and no slide anywhere.
    group = re.search(r"::view-transition-group\(\.job-morph\)\s*\{([^}]*)\}", _CSS)
    assert group and "animation-duration: 250ms;" in group.group(1)
    assert re.search(r"::view-transition-old\(root\),\s*::view-transition-new\(root\)\s*\{\s*animation: none;", _CSS)
    assert "transitionTypes" not in row and "nav-forward" not in _CSS and "nav-back" not in _CSS


def test_reduced_motion_covers_the_dots_the_check_and_the_morph():
    assert ".working-dot" in _REDUCED and "animate-check-draw" in _REDUCED
    # The morph does not move under reduced motion: the pair fades in place (the group's own animation is off).
    group = re.search(r"::view-transition-group\(\*\)\s*\{([^}]*)\}", _REDUCED)
    assert group and "animation-name: none !important;" in group.group(1)


def test_every_new_duration_stays_within_the_budget():
    # The view transition rules sit outside the utilities layer: each of their durations is in budget too.
    for decl in re.findall(r"::view-transition[^{]*\{[^}]*\}", _CSS):
        for ms in map(int, re.findall(r"(\d+)ms", decl)):
            assert ms <= 400, decl
    for name in ("CONFIRM_MS", "ROW_EXIT_MS", "ROLL_MS", "FADE_MS"):
        assert _const(name) <= 400, name


def test_no_animation_starts_from_a_key_handler():
    """Keyboard actions never animate (the motion budget). The new code adds no key handler that starts motion, and
    the Jobs row's Enter, the one key that opens a job, opens it without the morph."""
    starts = ("setConfirm", "setLeaving", "animate-", "startViewTransition", "data-confirm", ".animate(")
    for rel in (*_MORPH_SITES, "components/status-chip.tsx", "components/job-morph.tsx", "components/apply-step.tsx",
                "components/job-steps.tsx", "components/ui/lead-card.tsx", "components/tailored-resume-thumb.tsx"):
        src = _src(rel)
        for at in [m.start() for m in re.finditer(r"onKeyDown=\{", src)]:
            handler = src[at : src.index("}}", at)]
            assert not any(word in handler for word in starts), (rel, handler)
    row = _src("app/applications/page.tsx")
    key = row[row.index("onKeyDown={(e) => {") :]
    key = key[: key.index("}}")]
    assert "flushSync(() => setUnmorphed(jobId));" in key
    assert key.index("flushSync(() => setUnmorphed(jobId));") < key.index("router.push(href);")
    assert "off={unmorphed === jobId}" in row
    # A link pressed from the keyboard is a click with no pointer (`detail === 0`): the row's Next step and the job
    # page's Back drop the names first too.
    assert "if (e.detail === 0) flushSync(() => setUnmorphed(jobId));" in row
    page = _src("app/jobs/[id]/page.tsx")
    assert "if (event.detail === 0) flushSync(() => setUnmorphed(true));" in page
    # Both headers (loading and loaded) are one JobHeadingLead: its Back takes the handler, both morphs the flag.
    lead = page[page.index("function JobHeadingLead(") : page.index("\n}\n", page.index("function JobHeadingLead("))]
    assert lead.count("onClick={onBack}") == 1 and lead.count("off={unmorphed}") == 2
    assert page.count("onBack={backClick}") == 2 and page.count("unmorphed={unmorphed}") == 2


# --- a :root token is not a utility (docs/frontend-conventions.md, "Motion budget") ----------------------------

def _motion_tokens() -> tuple[set[str], set[str]]:
    """The motion tokens (`--duration-*`, `--ease-*`) declared in `@theme` and those declared only in `:root`.
    Tailwind makes a utility from a theme token (`ease-standard`), never from a `:root` one."""
    theme = _CSS.split("@theme inline {", 1)[1].split("\n}", 1)[0]
    declared = set(re.findall(r"--((?:duration|ease)-[\w-]+):", _CSS))
    in_theme = set(re.findall(r"--((?:duration|ease)-[\w-]+):", theme))
    return in_theme, declared - in_theme


def _bare_root_tokens(text: str, root_only: set[str]) -> list[str]:
    """Each `:root` motion token used as a bare utility: `duration-short3` or `delay-short3` for
    `--duration-short3`, `ease-out-strong` for `--ease-out-strong`. The arbitrary-value spelling
    (`duration-(--duration-short3)`) and `var(--…)` are not bare: a `-` or `(` sits before them."""
    found = []
    for token in sorted(root_only):
        kind, name = token.split("-", 1)
        utilities = ("duration", "delay") if kind == "duration" else ("ease",)
        for utility in utilities:
            found += re.findall(rf"(?<![\w(-])(?:[\w-]+:)*{utility}-{re.escape(name)}(?![\w-])", text)
    return found


def test_the_motion_token_scan_reads_both_tiers():
    in_theme, root_only = _motion_tokens()
    assert "ease-standard" in in_theme and "ease-out-strong" in root_only and "duration-short3" in root_only
    # Not vacuous: a bare use is found, with a variant prefix too; the arbitrary-value spelling and var() are not.
    assert _bare_root_tokens('className="transition duration-short3 hover:ease-out-strong"', root_only) == [
        "duration-short3", "hover:ease-out-strong"]
    assert _bare_root_tokens('className="delay-short3"', root_only) == ["delay-short3"]
    assert _bare_root_tokens(
        'className="duration-(--duration-short3) ease-(--ease-out-strong)" style={{ x: "var(--ease-spring)" }}',
        root_only) == []
    assert _bare_root_tokens('className="ease-standard duration-200"', root_only) == []


def test_no_root_motion_token_is_used_as_a_bare_utility():
    """A `:root` token as a bare utility compiles to no CSS, so the motion it names never runs (the Score
    breakdown's chevron turned with no transition). Write `duration-(--duration-short3)`, `ease-(--ease-out-strong)`."""
    _, root_only = _motion_tokens()
    wrong = []
    for tree in ("app", "components", "lib", "hooks"):
        for path in sorted((_FRONTEND / tree).rglob("*")):
            if path.suffix not in (".ts", ".tsx", ".css", ".mjs") or path.name == "globals.css":
                continue
            for use in _bare_root_tokens(path.read_text(encoding="utf-8"), root_only):
                wrong.append(f"{path.relative_to(_FRONTEND)}: {use}")
    assert not wrong, "\n".join(wrong)
