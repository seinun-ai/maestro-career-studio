# UX follow-ups, lane 3: Analytics and plain-words copy — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 11, 12, 13 of `docs/plans/2026-09-22-ux-followups.md`, in that order.
**Branch:** `grok/ux-lane3-analytics` (from `claude/ux-followups` at the commit that added this doc, right after `2916d83f`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/lane3-analytics` (dependencies are installed). Work only there.
**Planner/reviewer:** Claude (Opus 5.5). It reviews and merges this branch; you never merge.

## Goal Card

**Goal.** Close every gap that the honest-studio reviews and browser pass found,
plus the leftovers from the first UX review. The app must never mislead the user
about unsaved work. It must be keyboard- and contrast-accessible wherever the
reviews measured a gap, mark selection and "current" the same way everywhere, and
speak the user's language (no engine ids, no slugs) in the web app, in chat and in
MCP.

**Principles**
- **Honesty about unsaved work outranks convenience.** If a gesture could lose
  typed text, it asks or keeps the text; the status line never says "saved" while
  something is pending.
- **Accessibility is not negotiable.** WCAG 2.2 AA: contrast pinned by computed
  tests, focus never dropped to `<body>`, programmatic state (`aria-current`,
  `aria-pressed`, `inert`).
- **No new dependencies.** Existing tokens, components and hooks, or a small
  shared helper.
- **MCP and chat contracts are additive only.** The docstring is the API (SYSTEM.md
  §7). Every docstring stays under the ~2,000-char truncation budget.
- **Conventions change deliberately.** Each task updates
  `docs/frontend-conventions.md` (and SYSTEM.md where it describes the behaviour)
  in the same commit.

**Non-goals**
- Phase 2 of the studio direction (draft preview, three zones, job-fit chip), Phase
  3 (undo), remembering the sidebar across reloads, and the extension side panel.
- The out-of-scope leaks the briefs name for §11 (raw work-mode/OPT keys on Job
  market; MCP `explore_*` tools returning role slugs). File them in §11; don't widen
  this plan.

**Autonomy: peer (adapt-and-advise).** Adapt *how* when a step conflicts with repo
reality, and log every deviation in this doc with one line of reason. Anything touching
scope, another task's interface or the Goal Card goes back to the planner. Never
expand scope.

## Ground truth (read in this order before writing code)

1. `SYSTEM.md` at the repo root: the authoritative project reference.
2. `docs/frontend-conventions.md` and `frontend/AGENTS.md`.
3. The main plan `docs/plans/2026-09-22-ux-followups.md`: *Goal Card*, *Owner decisions*
   (binding), *Before you start*, and your tasks' sections. Each task section is the spec:
   its Files, Steps, pins, browser check and commit message.
4. The appendix sections your tasks cite (A1 §n, A2 §n, B §n) in
   `docs/plans/2026-09-22-ux-followups-appendix-*.md`. They hold the exact code. Their line
   numbers are from `a3c800bb`; Tasks 1–3 moved code since, so re-locate by the quoted code.

## Your tasks

1. **Task 11** — the `### Task 11` section of the main plan.
2. **Task 12** — the `### Task 12` section of the main plan.
3. **Task 13** — the `### Task 13` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- `frontend/app/career/page.tsx` (Task 11's KB tab), `frontend/components/status-chip.tsx`
  (Task 11's `NEEDS_YOU`), `frontend/app/templates/page.tsx` (the subtitle)
- `frontend/components/explore/explore-overview.tsx`, `frontend/app/analytics/page.tsx`
- `frontend/lib/types.ts`, `frontend/components/analytics/gap-tiers-panel.tsx`
- `frontend/components/role-category-picker.tsx`; delete `frontend/lib/format.ts` (its only
  importer is `charts/role-mix-chart.tsx`); new `frontend/lib/analytics-series.ts` and test
- `frontend/components/charts/{ats-over-time,role-mix,tailoring-lift,heatmap}-chart.tsx`
- Backend: `app/services/explore_overview.py`, `explore_gaps.py`, `explore_build_areas.py`,
  `mcp_server/server.py` (two docstrings), `app/services/chat_tools.py`,
  `app/prompts/chat_system.txt`, and the tests `test_explore_router.py`,
  `test_explore_gaps.py`, `test_explore_build_areas.py`, `mcp_server/tests/test_server.py`,
  `test_chat_upgrades.py`
- `docs/agentic-job-search.md`
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 2 (Task 6)** may swap `red-*` classes for the destructive token in
  `app/career/page.tsx`, and touch `status-chip.tsx` / `role-category-picker.tsx`. Keep your
  edits to the lines your task needs; no reformatting.
- **Lane 2 (Task 10)** owns `charts/top-skills-chart.tsx`. Don't touch it.

**Never touch:**
- `SYSTEM.md`. It sits at its 1000-line cap and four lanes would collide there. Write any
  SYSTEM.md change your task calls for under *Queued for Task 18* below; Claude applies them.
- `.slop-baseline.json` files (don't re-baseline; see Gates).
- `docs/ux/` (private, untracked), other lanes' worktrees and branches.
- The main checkout `/Users/ajeyds/Projects/maestro-career-studio`: its `data/` is the
  owner's live database, and its Docker stack on ports 3000/8001 is live. Never `cd` there,
  never run `docker compose`.
- Never use bare `git stash` / `git stash pop` (the stash stack is shared with other
  sessions). Don't push, rebase or merge.

## Lane notes

- **MCP and chat contracts are additive only** (Goal Card). Every MCP docstring stays
  under the ~2,000-char truncation budget; a ratchet test enforces it.
- **Task 12:** run the FULL backend suite (`pytest tests/ mcp_server/tests/ -q`, ~4 min).
  Add the agent-facing text AFTER the tier content.
- **Task 13:** its "§11 entries for the out-of-scope leaks" are SYSTEM.md edits: write them
  under *Queued for Task 18* below instead.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/lane3-analytics/backend`
  (the cwd wins on `sys.path`, so tests import this worktree's code).
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/lane3-analytics/frontend`): `npx tsc --noEmit`, `npm run lint`,
  `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Lint has the React Compiler rules at error level** (`react-hooks/refs`,
  `set-state-in-effect`, `set-state-in-render`). Run lint after every step. Baseline:
  0 errors, 5 warnings.
- **Node tests aren't in CI.** Pair every `lib/*.ts` behaviour with a pytest source pin in
  `backend/tests/test_frontend_*.py`.
- **Browser checks** use a throwaway stack on this lane's ports (other lanes use others):
  - scratch dir `/tmp/maestro-lane3`; SQLite at `/tmp/maestro-lane3/app.sqlite3`;
  - backend: from `/Users/ajeyds/Projects/maestro-ux-lanes/lane3-analytics/backend`,
    `DATABASE_URL=sqlite:////tmp/maestro-lane3/app.sqlite3`, every `*_DIR` variable
    SYSTEM.md lists pointed under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3103,http://localhost:3103`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8773` (startup runs
    alembic);
  - frontend: `API_PROXY_BACKEND=http://127.0.0.1:8773 npx next dev -p 3103`;
  - seed MADE-UP data through the API; no LLM keys are needed;
  - use real key and pointer events (a Playwright/browser tool), not synthetic JS events;
  - tear the stack down afterwards.

  If you have no browser tool, write "not run" for that check in the gate table. Claude runs
  every browser check again at merge anyway.

## Gates (per task, and all of them before you report done)

- The task's pins, plus every `backend/tests/test_frontend_*.py`.
- tsc clean; lint 0 errors; node tests pass.
- Slop ratchet, from `/Users/ajeyds/Projects/maestro-ux-lanes/lane3-analytics`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`. Name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 517 duplicated lines, 43 clones** (the
    value at the branch point; the checked-in baseline says 518). Four lanes merge into one
    branch, so each must hold its own delta at zero or below. Get the numbers with
    `slop_scan.py scan frontend --json` → `duplication`.
  - Logic added in two places goes through a shared helper or hook. Never reorder code to
    dodge the detector.
  - If `complexity_hotspots` rises only because you added tests, don't re-baseline: note it
    in the gate table and Claude re-baselines at merge.
- Don't run the full backend suite unless your task says to (Task 12 does).

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 3 tasks committed on `grok/ux-lane3-analytics` (one commit each), the three logs below
filled in, and this doc committed with them. Then report to the owner: the commit SHAs, the
gate table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 11–13 | Main plan trailer `Co-Authored-By: Claude Opus 5` | Commit trailer is `Assisted-by: Grok 4.7 (Cursor CLI)` only | This handoff is the binding trailer for this executor. |
| 11 | Optional naming note in `docs/frontend-conventions.md` | No conventions edit | No existing bullet names the KB Profile tab, and the task marks the note optional. Other lanes edit other bullets of the same file. |
| 12 | Replace the last two sentences of the `analytics_gap_frequency` chat spec | Replaced the status and category sentences; kept `role_category filters by the job's slug` | That sentence now follows them. Dropping it would hide the closed slug vocabulary. Additive contracts only. |
| 12 | Append the prompt line | Also updated `migrations/prompt_defaults.lock.json`. No resync migration | The pin test fails without the hash. Appendix B says this line is reinforcement for new installs; the tool spec is what existing installs read. |
| 13 | Tests named in the task only | Also added `backend/tests/test_frontend_analytics.py` | Node tests are not in CI. The lane rule says every `lib/*.ts` behaviour needs a pytest source pin. |
| 13 | Stay inside the owned file list | Updated the module docstring in `backend/app/routers/role_categories.py` | It named the deleted `frontend/lib/format.ts`. The endpoint still exists so pickers can fetch labels. |
| Review | Merge as delivered | Review fixes (Claude, one commit): the label fallback is `lib/humanize-slug.ts` (acronyms cased as the catalog cases them; `baseResumeLabel` uses it too, so `SLUG_ACRONYMS` is gone); Needs you is `text-orange-800` with a computed pin; solid focus on the status chip and role picker; the lift figure uses `text-destructive` / `emerald-700`; the fit chart names resumes by `display_name` (additive field on `/api/explore/fit-distribution`, and its MCP docstring) and caps at six hues; the KB import drawer's tab is Basics; the skill insight reads "Top required skill: sql (32% of JDs)", because skill names are stored casefolded and have no display form; `splitTopRoles` became `splitTopSeries`; pins are one per case | Goal Card: no slugs in the web app or MCP; contrast pinned by computed tests. The fit chart and drawer items were deferred below and are done here. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 11 | `test_overview_signals` + `test_overview_signal_copy_has_no_em_dash` | pass (em-dash pin failed on the old skill detail, then passed) |
| 11 | `pytest tests/test_explore_router.py tests/test_frontend_*.py` | 173 passed |
| 11 | tsc / lint / `node --test lib/*.test.ts` | tsc clean; lint 0 errors, 5 warnings; 67 passed |
| 11 | slop `check frontend` and `check backend` | both OK; frontend duplication 517 lines, 43 clones |
| 11 | browser (scratch stack, 3103) | Basics tab selected on `/career`; Templates subtitle "The look of the PDF."; Job market tiles are sentence case and insight details have no em dash; Needs you chip on `/proposals` uses `bg-orange-500/10 text-orange-700` |
| 12 | five pins (label set, row label, wording `None`, both docstrings, chat spec) | failed first, then passed |
| 12 | `pytest tests/ mcp_server/tests/ -q` | 4448 passed, 2 skipped, after the prompt pin update (first run: 4447 passed, 1 failed on `test_prompt_file_matches_its_pin[chat_system]`) |
| 12 | docstring budget ratchet | passed (inside the full suite) |
| 12 | tsc / lint / node tests | tsc clean; lint 0 errors, 5 warnings; 67 passed |
| 12 | slop `check frontend` and `check backend` | frontend OK, duplication 517 lines, 43 clones. Backend `complexity_hotspots` 424 → 426 because two existing tests each gained one `assert` and crossed cc 10. Not re-baselined. |
| 12 | browser | not in the task steps. The panel's words are unchanged; they now come from `category_label`. No scored gap rows on the scratch stack, so the panel was not opened. |
| 13 | `analytics-series.test.ts` + `test_best_paying_signal_uses_role_label` | failed first (missing module; title was `Best-paying track: unknown`), then passed |
| 13 | `pytest` explore router, the new pin, and `tests/test_frontend_*.py` | 161 passed in that selection. Full backend suite was Task 12's gate, not this task's. |
| 13 | tsc / lint / `node --test lib/*.test.ts` | tsc clean; lint 0 errors, 5 warnings; 70 passed |
| 13 | slop `check frontend` and `check backend` | frontend OK. Duplication 517 lines / 43 clones → 507 / 42 (deleting `format.ts` and the panel map). Backend `complexity_hotspots` 424 → 428. The four new hotspots are tests (two asserts in Task 12, `test_best_paying_signal_uses_role_label`, and the source pin). Not re-baselined. |
| 13 | browser (scratch stack, 3103) | Job market role mix, heatmap, salary tile, and the role filter options are catalog labels (Data Scientist, Data Engineer, Product Manager, Software Engineer), and the closed filter says Any. Best-paying insight says "Data Scientist". Resume fit and Gaps show no role slugs (both empty of scores: "No data yet" / "No frequent gaps yet"). Role-mix legend is 4 lines, strokes `--chart-1` through `--chart-4`, no repeat. Work mode and OPT keys are still raw; queued below. |
| Review | full suite / tsc / lint / node / ruff | 4499 passed, 2 skipped; tsc clean; lint 0 errors, 5 warnings; node 74 passed; ruff clean |
| Review | slop `check frontend` and `check backend` | both OK, no re-baseline. Frontend duplication 507 lines / 42 clones; backend `complexity_hotspots` 428 → 424 |
| Review | mutation checks | 38 mutants, each fails the pin written for it (a revert that breaks a present and an absent pin on the same line fails both) |
| Review | browser (scratch stack, 3116) | Catalog request delayed then 500: labels read AI/ML Engineer, MLOps Engineer, BI Developer. Needs you chip 6.57:1 light / 6.68:1 dark on `/proposals`, 6.16 (5.86 row hover) light / 7.56 (6.60) dark on `/applications`. Fit legend shows six resume names, `--chart-1..6`; its caption read "1 more are not shown", so the count now picks is/are (pinned; not re-run in the browser). |

## Queued for Task 18 (SYSTEM.md changes Claude applies)

§11 entries from Task 13. File them; do not build them on this branch.

- Job market still prints raw keys for work mode, OPT, and sponsorship
  (`onsite`, `yes` / `no` / `stem_opt_ok` / `unstated`, `sponsorship_available`)
  through `toBars` in `frontend/components/explore/explore-overview.tsx`.
  Role slugs on that page are labels now. These other keys are the leak the
  brief named for §11.
- MCP `explore_*` tools still return role slugs and do not add a `role_label`.
  The web app labels roles. The agent tools do not.
- Analytics filters still print raw keys: Employment shows `full_time` /
  `part_time`, and Level shows lowercase keys (`mid`, `senior`)
  (`frontend/app/analytics/page.tsx:147-153`). The Job market Level bars do the
  same (`toBars(o.level_breakdown)`, `explore-overview.tsx:215`). Same class as
  the work-mode / OPT / sponsorship leak above.
- The Applications table's Base column shows the humanized slug ("Ds Base")
  through `baseResumeLabel(r.app.base_resume)` (`app/applications/page.tsx:604`)
  instead of the resume's `display_name`. Found during the review browser pass.
- **Owner flag:** orange is no longer unique to "Needs you". Owner decision 6
  makes Needs you "one orange object", but `submission_uncertain` ("Submission
  uncertain") is also orange, as its own object, still `text-orange-700`
  (3.98:1 over `--muted`, 4.40:1 over `--background`: under AA). Decide whether
  it gets its own hue or joins the orange-800 shade.

## Deferred to merge (edits left for Claude, with file:line)

- `backend/tests/test_frontend_color_roles.py` on `claude/ux-followups`:
  `_PENDING_TRANSLUCENT_FOCUS` lists `components/status-chip.tsx` and
  `components/role-category-picker.tsx`. Both rings are solid on this branch,
  so delete the set (and its stale check) at merge, or the stale check fails.
- The `analytics_gap_frequency` chat spec uses the appendix's status phrase
  ("not in your Career KB / in your Career KB / ported before"). The chips
  say "Not in your KB", "In your KB", and "Ported before".
