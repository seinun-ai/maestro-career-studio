# Design refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development in this session) to implement this plan task-by-task.

**Goal:** Make Maestro calmer, clearer and livelier for any job seeker, rebuild analytics on data the app really has, show pay in the user's home currency, let the profile cover several countries, and give new users a clean first run, without losing any existing question or setting.

**Architecture:** Three layers, shipped in phases that each leave the app working. (1) Shared UI primitives and tokens (Fold, NextStep, LeadCard, NumberRoll, WorkingDots, DayStrip, OKLCH chart palette). (2) Backend data work: analytics correctness fixes, an application status-event log, countries and money (ISO country codes on jobs, `home` + `apply_in` markets, work-permit answers per country, ECB rates). (3) Page rebuilds that consume both: Jobs, Agent inbox, Job page, Automations, Today (new home), Analytics, Setup (new), Profile, Settings.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic on SQLite (backend), Next.js 16.3.8 App Router + React 19.3 + Tailwind v4 + Base UI/shadcn (frontend), pytest with xdist, backend source-pin tests for the frontend (`backend/tests/test_frontend_*.py`, `tests/_jsx_pins.py`), Node tests for `frontend/lib/*.test.ts` run through `tests/node_ts.py`.

**Visual spec:** the Design canvas https://claude.ai/artifact/C3WyCrgSJ4fwyqQp6RX28D. Each UI task names its board. Boards use sample data; build against real data.

---

## Goal Card

Goal: Maestro feels complex ("a lot going on") and flat ("not fun"). Make it calm, clear and alive for any job seeker in any field and any country. Each page has one thing that matters most, a few secondary things, and the advanced rest folded away. Words become numbers, meters and short tags. Motion and the base-resume colour appear only where something happens. Analytics show only what the data supports. Pay reads in the user's home currency. The profile covers every country the user applies in. A new user gets a short, engaging setup. Every one of today's 156 Profile and Settings items keeps a home.

Principles:
- Honest data first: never show a number, status or schedule the backend does not have. If the canvas shows something the data cannot back, change the UI, not the truth.
- For everyone: no owner-specific defaults (no US-only tiles, no data-role assumptions). Countries, currencies and work-permit wording come from data files.
- Keep the design system's rules: round means status, square means a base resume, one filled button per view, the motion budget (≤ 400 ms; frequent and keyboard actions do not animate), colour roles from tokens only.
- Agents own automations: Maestro never schedules or starts a run. It shows what runs reported.

Non-goals:
- No third-party AI logos (Anthropic needs written permission; OpenAI needs permission or must stay within its terms). Use app names as text.
- No phone layouts (desktop 1024 px and wider only), no hosted mode, no new scheduler.

Autonomy: **peer, adapt-and-advise.** Opus 5.5 implements and reviews each task (memory: subagent-model-routing). You may change *how* when the repo disagrees with this plan, and you must log each change in the task's commit body as `Deviation: <planned> → <done>, because <Goal Card line>`. Changes to scope, to an interface another task depends on, or to the Goal Card come back to the planner as a deviation note. Never widen scope.

## Owner decisions already made (2026-10-20, do not reopen)

- D1 Every page uses the Lead / Also / Folded tiers. Page subtitles go.
- D2 No Resume column in the Jobs list: a resume is picked after a job is saved. The square stays on Agent inbox rows (the agent picked that resume), on the tailored-resume card on the job page, on Today cards and in charts split by resume.
- D3 Every row's Next step uses one style: a blue text link with a chevron for your move, grey text for waiting. The tonal fill shows on row hover only.
- D4 The Jobs list borrows the Agent inbox's Select mode and its ownership popover (main `d1cd976a`). The Where column goes. The ownership icon shows only when a job is not on your laptop.
- D5 Automations: agents own the schedule and every run. Each card has one app-neutral Copy prompt. Status comes only from `agent_runs`. There are no per-app buttons and no logos.
- D6 Autofill coverage leaves Analytics for Settings › Advanced › Diagnostics.
- D7 Analytics: a rate shows only from 20 in its denominator, with a Wilson 95% range. Below that, show counts ("5 of 12").
- D8 Money: one home currency (from where you live). Converted figures carry "≈" and the posted amount underneath. Rates are ECB daily reference rates. Missing pay is never estimated.
- D9 Countries: "You live in" (one: home currency and date format) plus "You apply in" (several). Work-permit answers are stored per country. A form gets the answer for the country its question names, else the job's country, else the Companion asks once on that job.
- D10 Diversity consent stays in Profile, next to the answers it covers. Agreements and signatures, the screening-answer setting, the Companion's apply toggles and the form-filling engine move to Settings › Companion.
- D11 First run: a four-step Setup (AI model, resume, where and what, form answers). Profile holds facts about you, Settings holds how the app behaves (tabs: Basics, Companion, Agent apps, Advanced).

## Ground rules for every task

- Work in this worktree. Commit locally after every task, one commit per task, and never push (memory: design-system-local-batching). Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Backend from `backend/` with the worktree venv: `.venv/bin/python -m pytest <target> -q` for one file, and `.venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` at each phase gate. If `.venv` is missing: `python -m venv .venv && .venv/bin/python -m pip install -e ".[dev,mcp]"`.
- Frontend gates from `frontend/`: `npx tsc --noEmit`, `npm run lint`, `npm run build`.
- Alembic ids: `python -c "import uuid; print(uuid.uuid4().hex[:12])"`. Find the head with `.venv/bin/alembic heads` and use it as `down_revision`.
- Copy follows `docs/design-system/README.md` (plain words, sentence case, no em dash as a joiner, no placeholders except the search prompt, "you", one word per thing).
- Update `SYSTEM.md` in the same commit when you change an entity, endpoint, invariant or convention it describes (header contract). Run `python3 scripts/check_system_md.py` before committing a SYSTEM.md change.
- Add a line under `CHANGELOG.md` `[Unreleased]` per user-visible change. Tasks note when.
- Existing source-pin tests will fail when a page is rebuilt on purpose. Update the pin to the new rule in the same commit and say so in the body. Never delete a pin without replacing what it protected.
- Never verify against the live app (ports 8001/3000). Use the fresh stack in `.claude/launch.json` (see memory: worktree-verification-recipe).

## Phase map

| Phase | What | Depends on | Can run alongside |
|---|---|---|---|
| 0 | Shared primitives, tokens, copy rules | none | 1 |
| 1 | Analytics correctness fixes, value normalising, extraction fixes | none | 0 |
| 2 | Status-event log | none | 0, 1 |
| 3 | Countries and money backend | 1 (Task 1.8 normalising) | 0 |
| 4 | Lists (Jobs, Agent inbox, Job page, Automations), motion in use, fewer words on the remaining pages | 0 | 2, 3 |
| 5 | Analytics rebuild | 1, 2, 3 | 4 |
| 6 | Today page as home | 0, 2, 4 | 5 |
| 7 | First run: Setup, Profile, Settings | 0, 3 | 5, 6 |
| 8 | Docs, design system, full verification | all | none |

Phase gate (end of each phase): full backend suite with xdist, the three frontend gates, the slop ratchet for every surface touched, named in the commit (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend|frontend|extension`), SYSTEM.md gate.

---

## Phase 0: Shared primitives and tokens

### Task 0.1: Chart palette in OKLCH

**Board:** Colour roles (Chart series row).

**Files:**
- Modify: `frontend/app/globals.css` (light `--chart-1..6` near `:230-235`, dark near `:324-329`)
- Modify: `frontend/components/explore/charts/chart-kit.tsx` (hex fallbacks `:25-32`)
- Modify: `docs/design-system/tokens.json` (`:399-441`)
- Test: `backend/tests/test_frontend_color_roles.py`

**Step 1: Write the failing test**

```python
def test_chart_series_are_oklch_with_no_red_or_green_series():
    css = (_FRONTEND / "app/globals.css").read_text(encoding="utf-8")
    for n in range(1, 7):
        values = re.findall(rf"--chart-{n}:\s*([^;]+);", css)
        assert len(values) == 2, n  # light and dark
        assert all(v.strip().startswith("oklch(") for v in values), values
    hues = [float(m) for m in re.findall(r"--chart-\d:\s*oklch\([\d.]+ [\d.]+ ([\d.]+)\)", css)]
    assert not any(15 <= h <= 35 or 135 <= h <= 150 for h in hues)  # no traffic-light red or green
```

**Step 2:** Run `.venv/bin/python -m pytest tests/test_frontend_color_roles.py -q`. Expected: FAIL (hex values).

**Step 3: Implement.** Light: `--chart-1: oklch(0.55 0.14 259)`, `--chart-2: oklch(0.62 0.13 50)`, `--chart-3: oklch(0.55 0.1 175)`, `--chart-4: oklch(0.55 0.14 310)`, `--chart-5: oklch(0.6 0.11 95)`, `--chart-6: oklch(0.5 0.03 259)`. Dark: same hues and chroma at lightness 0.72 (chart-6 at 0.68). Mirror them in `tokens.json`, and replace the hex fallbacks in `chart-kit.tsx` with `oklch(...)` strings. Check 3:1 against `card` in both themes with the repo's contrast helper in `test_frontend_color_roles.py` (graphical objects need 3:1).

**Step 4:** Run the test. Expected: PASS. Run `npx tsc --noEmit`.

**Step 5:** Commit `feat(tokens): chart series in OKLCH at even lightness`.

### Task 0.2: Neutral monograms

**Board:** Colour roles (Ground: monogram), Jobs.

**Files:** Modify the monogram component (find it with `rg -n "monogram" frontend/components -i`; the design system README lists "monograms = 4 non-status tones"), its README card under `docs/design-system/components/`. Test: the existing monogram pin (`rg -n "monogram" backend/tests -il`).

**Steps:** Write a pin asserting the monogram fill is `bg-surface-container-highest` and takes no hue from the company name. Watch it fail, implement, watch it pass. Commit `feat(visual): monograms go neutral so the resume square is the row's only hue`.

### Task 0.3: Fold (the Folded tier)

**Board:** every page (rows with a chevron, a title and a quiet summary on the right).

**Files:**
- Create: `frontend/components/ui/fold.tsx`
- Test: `backend/tests/test_frontend_tiers.py` (new)

**Step 1: Write the failing test**

```python
"""The Lead / Also / Folded tiers (design refresh, Phase 0)."""

from pathlib import Path

from tests._jsx_pins import squash

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _src(path: str) -> str:
    return (_FRONTEND / path).read_text(encoding="utf-8")


def test_fold_is_a_real_disclosure_with_a_summary():
    src = squash(_src("components/ui/fold.tsx"))
    assert "aria-expanded={open}" in src and "aria-controls={panelId}" in src
    assert "summary" in src and "ChevronRight" in src
    assert "transition-[rotate]" in src  # names the property, never `transform`
```

**Step 2:** Run it. Expected: FAIL (file missing).

**Step 3: Implement**

```tsx
"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The Folded tier: a row that keeps advanced or rare things one click away.
 * Title on the left, a short summary of what is inside on the right. */
export function Fold({ title, summary, children, defaultOpen = false, className }: {
  title: string; summary?: ReactNode; children: ReactNode; defaultOpen?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  return (
    <div className={cn("rounded-corner-md bg-card", className)}>
      <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((o) => !o)}
        className="flex h-13 w-full items-center gap-3 px-5 text-left">
        <ChevronRight aria-hidden="true"
          className={cn("size-4 text-muted-foreground transition-[rotate] duration-short3 ease-standard", open && "rotate-90")} />
        <span className="text-title-small flex-1">{title}</span>
        {summary ? <span className="text-body-small text-muted-foreground">{summary}</span> : null}
      </button>
      <div id={panelId} hidden={!open} className="px-5 pb-5">{children}</div>
    </div>
  );
}
```

**Step 4:** Run the test and `npx tsc --noEmit`. Expected: PASS.

**Step 5:** Commit `feat(ui): Fold, the folded tier`.

### Task 0.4: NextStep (one style for a row's next move)

**Board:** Jobs (Next step column), Agent inbox.

**Files:**
- Create: `frontend/components/visual/next-step.tsx`, and export it from `frontend/components/visual/index.ts`
- Test: `backend/tests/test_frontend_tiers.py`

**Step 1: Failing test**

```python
def test_next_step_has_one_look_for_a_move_and_one_for_waiting():
    src = squash(_src("components/visual/next-step.tsx"))
    assert "text-primary" in src and "ChevronRight" in src        # your move
    assert "text-muted-foreground" in src                          # their move
    assert "bg-secondary-container" not in src.split("group-hover")[0]  # no fill at rest
    assert "group-hover/row:bg-secondary-container" in src
```

**Step 3: Implement**

```tsx
import { ChevronRight } from "lucide-react";
import Link from "next/link";

/** A row's next step (owner rule D3): your move is a blue text link with a chevron, their move is grey
 * text. One look for every row. The tonal fill shows only while the row is hovered. */
export function NextStep(props: { label: string; href: string } | { waiting: string }) {
  if ("waiting" in props) {
    return <span className="text-body-medium text-muted-foreground tabular-nums">{props.waiting}</span>;
  }
  return (
    <Link href={props.href}
      className="-ml-2 inline-flex h-7 items-center gap-0.5 rounded-corner-sm px-2 text-label-large text-primary group-hover/row:bg-secondary-container group-hover/row:text-on-secondary-container">
      {props.label}<ChevronRight aria-hidden="true" className="size-3.5" />
    </Link>
  );
}
```

Rows that use it carry `group/row` on the row element.

**Step 4:** Run the test and `tsc`. **Step 5:** Commit `feat(visual): NextStep, one style for a row's next move`.

### Task 0.5: LeadCard (the Lead tier)

**Board:** Today (Next up), Job page (Ready to apply), Analytics (funnel), Profile (Next up).

**Files:** Create `frontend/components/ui/lead-card.tsx`. Test in `test_frontend_tiers.py`.

**Test:** the component renders an eyebrow (`text-label-medium text-primary`), a `children` slot, and accepts at most one `action` prop that renders a filled `Button` (variant `default`). Pin that `shadow-level1` is the only shadow, because the lead card floats a little.

**Implementation:** `LeadCard({ eyebrow, aside, action, children })` is a `rounded-corner-lg bg-card p-7 shadow-level1` section with `aria-labelledby` on the eyebrow and a flex-wrap row (content `flex: 1 1 420px`, aside `flex: 0 1 300px` on `surface-container-low`).

**Commit:** `feat(ui): LeadCard, the lead tier`.

### Task 0.6: NumberRoll, WorkingDots, CheckDraw

**Board:** Motion specimens (Number rolls, AI is working, Saved then settles).

**Files:**
- Create: `frontend/components/visual/number-roll.tsx`, `working-dots.tsx`
- Modify: `frontend/app/globals.css` (`@layer utilities`: `.working-dot` keyframes; `@utility animate-check-draw`; reduced-motion rules in the existing block at `:519`)
- Modify: `frontend/lib/motion.ts` (add `ROLL_MS = 400`)
- Test: `backend/tests/test_frontend_motion.py`

**Step 1: Failing tests**

```python
def test_number_roll_and_working_dots_stay_in_budget_and_respect_reduced_motion():
    roll = (_FRONTEND / "components/visual/number-roll.tsx").read_text()
    assert "ROLL_MS" in roll and "translate" in roll and "aria-live" not in roll  # the parent announces
    assert "useReducedMotion" in roll or "prefers-reduced-motion" in roll
    dots = (_FRONTEND / "components/visual/working-dots.tsx").read_text()
    assert 'role="status"' in dots and "working-dot" in dots
    reduced = _CSS.split("@media (prefers-reduced-motion", 1)[1]
    assert ".working-dot" in reduced and "animate-check-draw" in reduced
```

**Step 3: Implement.** NumberRoll renders each digit as a 0–9 column in a `h-[1lh] overflow-hidden` box and moves it with `translate: 0 -${d}lh` and `transition-[translate] duration-[400ms] ease-out-strong`. It renders the plain number when reduced motion is on. The surrounding element keeps `aria-label={String(value)}` and the digit columns are `aria-hidden`. WorkingDots is three 7 px dots with staggered `animation-delay` (0, 120, 240 ms) on a 900 ms ease-in-out loop, `role="status"` and the label as visible text. CheckDraw is a `stroke-dasharray: 24` path with `animate-check-draw` (300 ms ease-out-strong). Task 4.5 puts all three to use.

**Step 4:** Run `test_frontend_motion.py`. The existing budget test must still pass (every ms ≤ 400, shimmer 1400). **Step 5:** Commit `feat(motion): number roll, working dots and check draw`.

### Task 0.7: DayStrip (a 14-day row of round status dots)

**Board:** Automations.

**Files:** Create `frontend/components/visual/day-strip.tsx` and `frontend/lib/day-strip.ts` (pure), with test `frontend/lib/day-strip.test.ts` run from `backend/tests/test_frontend_automations.py` via `run_node_test`.

**Node test (`lib/day-strip.test.ts`):**

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { dayStrip } from "./day-strip.ts";

test("one cell per local day, the worst outcome wins a day, empty days stay empty", () => {
  const today = new Date("2026-10-20T12:00:00");
  const runs = [
    { finished_at: "2026-10-20T08:00:00", outcome: "ok" },
    { finished_at: "2026-10-20T09:00:00", outcome: "partial" },
    { finished_at: "2026-10-18T09:00:00", outcome: "failed" },
  ];
  const cells = dayStrip(runs, today, 14);
  assert.equal(cells.length, 14);
  assert.equal(cells[13].outcome, "partial");
  assert.equal(cells[11].outcome, "failed");
  assert.equal(cells[12].outcome, null);
});
```

**Implementation:** `dayStrip(runs, today, days)` buckets by the local calendar day (not UTC, unlike `explore_activity.py:36`). Severity is failed > partial > ok. The component draws 14 round dots (round means status): `success`, `warning`, `destructive`, or `surface-container-high` for no report. It has `role="img"` with a sentence label and a legend under it.

**Commit:** `feat(visual): DayStrip for automation reports`.

### Phase 0 gate

Run the gate. Then update `docs/design-system/README.md` (Motion: NumberRoll, WorkingDots, CheckDraw. Components: Fold, NextStep, LeadCard, DayStrip. Shape: Lead / Also / Folded. Colour: charts and neutral monograms) and its component cards under `docs/design-system/components/`. Commit `docs(design-system): tiers and new primitives`.

---

## Phase 1: Analytics correctness and clean values

Every task here fixes a defect found in the 2026-10-20 audit. Each one starts with a test that reproduces it.

### Task 1.1: Best-paying role never compares across currencies

**Files:** Modify `backend/app/services/explore_overview.py:91-96`. Test `backend/tests/test_explore_router.py`.

**Step 1: Failing test.** Seed two roles: role A with three jobs in INR (`salary_max` 2,400,000) and role B with three jobs in USD (`salary_max` 170,000). Call `/api/explore/overview` with no currency filter. Assert the best-paying signal names role B, or names none, and never role A.

**Step 3: Implement.** Compute the signal only among rows sharing the single most common currency (until Phase 3 adds conversion), and add `currency` to the signal payload so the text names it. In Task 3.9 this switches to converted pay.

**Commit:** `fix(analytics): best-paying role compares one currency`.

### Task 1.2: Skills by role numerator honours every filter

**Files:** `backend/app/routers/explore.py:186-207`. Test `tests/test_explore_router.py`.

**Failing test:** with a Level filter set, every `pct_jobs` stays ≤ 100. Seed one role, two levels and skills on both.

**Fix:** apply the same `JobFilters` to the numerator query as to the denominator.

**Commit:** `fix(analytics): skills-by-role percentages stay within 100`.

### Task 1.3: Roles over time honours filters and zero-fills weeks

**Files:** `backend/app/routers/explore.py:269-287`, `frontend/components/explore/charts/role-mix-chart.tsx`. Test `tests/test_explore_router.py`.

**Failing test:** a Country filter changes the series, and the weeks run continuously, with zero for empty weeks.

**Fix:** pass the filters through, and build the week list from min to max with zeros. On the frontend, show `dot` when a series has one point.

**Commit:** `fix(analytics): roles over time follows the filters`.

### Task 1.4: Base line reads one base per job

**Files:** `backend/app/services/explore_gaps.py:233-265`. Test `tests/test_explore_gaps.py`.

**Failing test:** a job scored against three bases contributes one base point, its best, to the Base line. Today it contributes all three.

**Fix:** reuse `_best_base_gap_rows` (`explore_gaps.py:46-98`) to pick the base per job. This follows the "one base per job" rule in `docs/frontend-conventions.md`.

**Commit:** `fix(analytics): match score over time reads one base per job`.

### Task 1.5: Rates on tiny counts become counts

**Files:** `backend/app/services/explore_activity.py:129`, `frontend/components/analytics/analytics-overview.tsx`. Test `tests/test_explore_activity.py`.

**Failing test:** with 3 applications, the payload carries `interview_rate: null` with `interviewing: 1, applied: 3`. With 20 or more it carries a rate.

**Fix:** add `MIN_RATE_N = 20` in a new `backend/app/services/rates.py` (Task 5.1 adds the Wilson range there). The tile shows "1 of 3" below the minimum.

**Commit:** `fix(analytics): no percentage on fewer than 20`.

### Task 1.6: Score gain follows the All / Yours / Agents toggle

**Files:** the tailoring-lift query (`rg -n "def .*tailoring_lift" backend/app`). Test `tests/test_explore_router.py`.

**Failing test:** with `source=agent`, user-made tailoring is excluded.

**Commit:** `fix(analytics): score gain follows the source toggle`.

### Task 1.7: A failed chart says it failed

**Files:** `ats-over-time-chart.tsx:38`, `fit-distribution-chart.tsx:31`, `role-mix-chart.tsx:26`, `tailoring-lift-chart.tsx:24`, `heatmap-chart.tsx:29` (all under `frontend/components/explore/charts/`). Test `backend/tests/test_frontend_analytics.py`.

**Failing test:** each chart file reads `isError` and renders the shared load-error state (`components/load-error-state.tsx`), as `top-skills-chart.tsx:125` already does.

**Commit:** `fix(analytics): charts show a load error instead of "No data yet"`.

### Task 1.8: One spelling per work mode, level and country

**Files:**
- Modify: `backend/app/schemas/job_extraction.py` (validators for `work_mode`, `level`)
- Create: `backend/app/services/data/countries.yaml` (ISO 3166 alpha-2 code, English name, aliases such as `USA`, `U.S.`, `United States of America`, `UK`, `Great Britain`, and the currency) and `backend/app/services/countries.py` (`normalize(text) -> str | None`, `label(code)`, `currency(code)`)
- Modify: `backend/app/models/job.py` (add `country_code: Mapped[str | None]` beside `country`, line 48)
- Create: migration `backend/migrations/versions/<id>_jobs_country_code.py` (add the column and backfill from `country`, falling back to `location`)
- Modify: `backend/app/services/explore_overview.py` (group work mode, level and countries by normalised key)
- Test: `backend/tests/test_countries.py` (new), `tests/test_explore_router.py`

**Step 1: Failing tests**

```python
from app.services import countries


def test_country_spellings_collapse_to_one_code():
    for text in ["United States", "USA", "U.S.", "united states ", "United States of America"]:
        assert countries.normalize(text) == "US"
    assert countries.normalize("Canada / United States") is None  # more than one: no guess
    assert countries.normalize("unknown") is None
    assert countries.label("GB") == "United Kingdom"


def test_overview_groups_one_spelling_per_value(db_session):
    # Seed jobs with work_mode "Hybrid", "hybrid ", "On-site", "Onsite" and country "USA", "United States".
    # Assert the overview lists Hybrid once, On-site once and United States once, with summed counts,
    # and that unknown countries show as "Not stated".
    ...
```

**Step 3: Implement.** Work-mode validator: lower-case and strip, map `onsite|on site|on-site|in office` to `on_site`, then `hybrid`, then `remote`. Store the key and let the UI word it. Level: map to the existing level vocabulary (find it with `rg -n "level" backend/app/services/data`) and add `entry_to_mid` only if the vocabulary has it. Countries: `countries.yaml` is data, like `markets.yaml`. Keep it to countries with real usage plus every market. Write `country_code` on capture (find the capture write with `rg -n "country=" backend/app/routers/jobs.py`). The migration backfills with `countries.normalize`. It reads YAML through the service module, with no ORM import (alembic env convention).

**Step 4:** Run both tests. Run `.venv/bin/alembic upgrade head` on a scratch DB (`DATABASE_URL=sqlite:////tmp/<scratch>/m.sqlite3`).

**Step 5:** Commit `feat(jobs): one country code and one spelling per work mode and level`. Update SYSTEM.md §4 Job.

### Task 1.9: "40 hours per week" is not pay

**Files:** `backend/app/services/jd_extraction.py:9-16, 65-80`. Test: `rg -n "hourly" backend/tests -l` and add to the extraction test file.

**Failing test:** a description with "40 hours per week" and no pay extracts no salary. "$45 per hour" still extracts 45/hour.

**Fix:** the hourly hint needs a currency mark or a pay word ("pay", "rate", "salary", "compensation") next to the number. It never takes a bare `<n> hours`.

**Commit:** `fix(extraction): working hours are not an hourly rate`.

### Task 1.10: A bare "$" is not US dollars

**Files:** `backend/app/schemas/job_extraction.py:177` (symbol table), `backend/app/routers/jobs.py:148-167` (`_salary_currency_for`). Tests: the extraction schema tests.

**Failing test:** `"$"` alone normalises to `None`. `"US$"` and `"USD"` still give `USD`. A job in Toronto with a bare "$" gets `CAD` from its country at capture (`countries.currency("CA")`) and is flagged `salary_currency_assumed = True` (new boolean column in the Task 1.8 migration, or a second migration).

**Fix:** remove `"$": "USD"` and the `$` prefix branch. In `_salary_currency_for`, fall back first to the job's country currency (marked assumed), then to the home currency (Task 3.4), also marked assumed. The Currency board's "Unclear $" warning reads this flag.

**Commit:** `fix(extraction): an unmarked dollar sign takes the job's country`.

### Phase 1 gate

Run it, then add `CHANGELOG.md` lines: analytics fixes (best-paying role, percentages, filters, base line, small counts, chart errors) and extraction fixes (hours, "$").

---

## Phase 2: Status-event log

Applications store only their current `status` and `applied_at` (`backend/app/models/application.py:28-29`). "Ever interviewed", "time to hear back" and "quiet for 14 days" need dated status changes.

### Task 2.1: application_status_events table

**Files:**
- Create: `backend/app/models/application_status_event.py`
- Create: migration `<id>_application_status_events.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_status_events.py` (new)

**Model**

```python
class ApplicationStatusEvent(Base):
    """One status change on an application: what it became, when, and who said so. Read by Analytics
    (funnel, time to hear back) and Today (quiet for 14 days). `backfilled` rows were made by the
    migration from the status an application already had: their `at` is its last update, not when the
    status changed, so timing metrics skip them."""

    __tablename__ = "application_status_events"
    __table_args__ = (Index("ix_status_events_app_at", "application_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)  # "you" | an MCP client name | "mail"
    backfilled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

**Migration:** create the table, then insert one `backfilled=1` row per application that has a status, with `at = updated_at`. Check that sync does not need the table (`rg -n "SYNCED_TABLES|synced" backend/app/services/sync*`). If applications sync between copies, add the table to the same sync set, because synced pairs must both update (memory: resume-colour-jobs-row).

**Tests:** creating the table on a fresh DB, and the backfill count equalling applications with a status.

**Commit:** `feat(applications): a dated log of status changes`. Update SYSTEM.md §4.

### Task 2.2: Record every status change in one place

**Files:** find every writer with `rg -n "\.status = |status=" backend/app/routers/applications.py backend/app/services backend/mcp_server | grep -i applic`. Create `backend/app/services/application_status.py` with `set_status(session, application, to_status, source)`, which writes the column and the event when the value changes. Route every writer through it: the REST update, MCP `update_application` and `mark_submitted`, mail-status updates, and Companion submit. Test `tests/test_status_events.py`.

**Failing tests:** a status change through the REST endpoint writes one event with `source="you"`. Through the MCP tool it writes `source=<clientInfo name>` (see `server.py` `_client_label`). Setting the same status again writes nothing.

**Add a guard test:** a source scan of `backend/app` fails if `application.status =` is assigned outside `application_status.py`, so a new writer can't skip the log.

**Commit:** `feat(applications): every status change goes through set_status`.

---

## Phase 3: Countries and money

### Task 3.1: More markets as data

**Files:** `backend/app/services/data/markets.yaml`. Test `tests/test_markets.py` (find the existing one with `rg -n "markets" backend/tests -l`).

**Failing test:** `markets.is_supported("DE")` and `("NL")` are true, `currency_for("DE") == "EUR"`, `offers_eeo("DE") is False`, and the work-permit vocabulary is `generic`.

**Implement:** add DE (Germany) and NL (Netherlands) with `eeo_module: null` and `work_auth_vocab: generic`, following the file's comment that a null module is an honest limit. Keep the label and date format right (DMY).

**Commit:** `feat(markets): Germany and the Netherlands`.

### Task 3.2: home + apply_in replace the single market

**Files:**
- Modify: `backend/app/schemas/market_settings.py` (`MarketSetting`)
- Modify: `backend/app/services/market_settings.py` (`default_currency_for_capture`, `offers_eeo`)
- Modify: `backend/app/routers/settings.py:353-370` (`GET/PUT /api/settings/market`)
- Test: `backend/tests/test_market_settings.py` (find the existing one or create it)

**Step 1: Failing tests**

```python
from app.schemas.market_settings import MarketSetting


def test_a_legacy_single_market_reads_as_home_and_apply_in():
    setting = MarketSetting.model_validate({"market": "UK"})
    assert setting.home == "UK" and setting.apply_in == ["UK"]


def test_apply_in_always_holds_known_markets_once():
    setting = MarketSetting.model_validate({"home": "DE", "apply_in": ["de", "UK", "UK", "US"]})
    assert setting.apply_in == ["DE", "UK", "US"]


def test_an_unknown_market_is_refused_not_coerced():
    with pytest.raises(ValidationError):
        MarketSetting.model_validate({"home": "XX", "apply_in": ["XX"]})
```

**Step 3: Implement**

```python
class MarketSetting(BaseModel):
    """Where the user lives (`home`: currency, date format) and every market they apply in (`apply_in`).
    A stored `{"market": X}` from before this change reads as home = X, apply_in = [X]: the setting is
    a JSON text setting with a file mirror and may come from a peer that has not updated, so it is
    mapped when read, never migrated (the autofill veteran precedent)."""

    home: str = markets.DEFAULT_MARKET
    apply_in: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value):
        if isinstance(value, dict) and "market" in value and "home" not in value:
            return {"home": value["market"], "apply_in": [value["market"]]}
        return value

    @field_validator("home", mode="before")
    @classmethod
    def _known_home(cls, value):
        return _known(value)

    @field_validator("apply_in", mode="before")
    @classmethod
    def _known_list(cls, value):
        seen: list[str] = []
        for item in value or []:
            key = _known(item)
            if key not in seen:
                seen.append(key)
        return seen

    @model_validator(mode="after")
    def _home_counts(self):
        if not self.apply_in:
            self.apply_in = [self.home]
        return self
```

`_known` is the old `_known_market` body. Keep a read-only `market` property that returns `home` for callers that are not migrated yet, and list each one in SYSTEM.md §13 as an active migration row. The router returns `{home, apply_in, markets: [...vocabulary]}`, and PUT accepts both shapes.

**Step 4:** Run the tests and the full `tests/test_*market*` set.

**Step 5:** Commit `feat(markets): where you live plus where you apply`. Add a SYSTEM.md §13 migration row `market-home-apply-in`.

### Task 3.3: A job's default currency comes from its own country

**Files:** `market_settings.default_currency_for_capture` takes `job_country_code: str | None`. Callers are `routers/jobs.py:148-167`. Test `tests/test_market_settings.py`.

**Failing test:** a German job saved by a user who lives in the UK defaults to EUR. A job with no country defaults to the home currency. Both are marked assumed (Task 1.10).

**Commit:** `feat(money): a job's default currency is its country's`.

### Task 3.4: Money settings and ECB rates

**Board:** Pay in your currency, Settings (Money card).

**Files:**
- Create: `backend/app/services/fx_rates.py`, `backend/app/schemas/money.py`, `backend/app/services/money.py`
- Modify: `backend/app/routers/settings.py` (`GET/PUT /api/settings/money`, `GET /api/fx/rates`, `POST /api/fx/rates/refresh`)
- Test: `backend/tests/test_money.py` (new), `backend/tests/test_fx_rates.py` (new, with a recorded ECB XML fixture in `backend/tests/fixtures/ecb_eurofxref_daily.xml`)

**Rates source.** The ECB's daily reference rates at `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` are official and free. They cover about 29 currencies and are published around 16:00 CET on working days. The ECB asks to be cited as the source and says the rates are for information only. Do not use Frankfurter's default endpoint: it blends 104 providers. Its `/v2/providers/ecb/rates` endpoint is an acceptable mirror, but fetching from the ECB itself needs no third party. Fetch at most once a day, when a page asks and the cache is older than a day. Cache in a JSON text setting `fx_rates` (`{"date": "2026-10-19", "base": "EUR", "rates": {...}, "fetched_at": ...}`). When offline, keep the last cache. With no cache at all, conversions return `None`: the UI shows the posted amount and leaves the job out of comparisons. Never invent a rate.

**Step 1: Failing tests (money)**

```python
from decimal import Decimal

from app.services import money

RATES = {"base": "EUR", "date": "2026-10-19", "rates": {"USD": Decimal("1.0870"), "GBP": Decimal("0.8770")}}


def test_convert_goes_through_euro_and_never_guesses():
    assert money.convert(Decimal("100"), "EUR", "EUR", RATES) == Decimal("100")
    assert money.convert(Decimal("108.70"), "USD", "EUR", RATES).quantize(Decimal("1")) == Decimal("100")
    assert money.convert(Decimal("1"), "ARS", "EUR", RATES) is None  # no ECB rate
    assert money.convert(Decimal("1"), "USD", "EUR", None) is None  # no cache yet


def test_yearly_uses_2080_hours_and_twelve_months():
    assert money.to_yearly(Decimal("50"), "hour") == Decimal("104000")
    assert money.to_yearly(Decimal("5000"), "month") == Decimal("60000")
    assert money.to_yearly(Decimal("1000"), "week") == Decimal("52000")
    assert money.to_yearly(Decimal("400"), "day") == Decimal("104000")  # 260 working days
    assert money.to_yearly(Decimal("1"), None) is None


def test_midpoint_of_a_range_or_the_one_end_given():
    assert money.midpoint(Decimal("70"), Decimal("90")) == Decimal("80")
    assert money.midpoint(None, Decimal("90")) == Decimal("90")
    assert money.midpoint(None, None) is None
```

**Step 3: Implement** `money.py` (pure, `Decimal` only): `convert`, `to_yearly` (hour × 2080, day × 260, week × 52, month × 12, year × 1), `midpoint`. `HOURS_PER_YEAR = 2080` is the US full-time figure the BLS uses. Make it a setting under Advanced (`Hours per year`, default 2080) and pass it in. `fx_rates.py` holds `parse_ecb_xml(text) -> dict`, `current(session) -> dict | None` (read-only, the peek pattern) and `refresh(session, fetch=httpx.get)`. Keep the fetch injectable for tests, with a timeout of 5 s. Money settings schema: `{home_currency: str (ISO 4217, default currency_for(home)), period: "year"|"month"|"hour", show_posted: bool = True, hours_per_year: int = 2080}`.

**Step 4:** Run `test_money.py` and `test_fx_rates.py`. The parser test reads the fixture. The refresh test stubs `fetch` and asserts there is one fetch per day.

**Step 5:** Commit `feat(money): home currency, pay period and ECB reference rates`. SYSTEM.md: a new §4 entry "Money and rates" and the network call in the outbound-calls list (find it with `rg -n "outbound|network call" SYSTEM.md`).

### Task 3.5: The frontend money formatter

**Files:** Create `frontend/lib/money.ts` and `frontend/lib/money.test.ts`. Pin from `backend/tests/test_frontend_money.py` (new) with `run_node_test`.

**Node tests**

```ts
test("same currency reads plain, converted reads with ≈ and keeps the posted amount", () => {
  const rates = { base: "EUR", date: "2026-10-19", rates: { GBP: 0.877 } };
  const same = formatPay({ min: 75000, max: 90000, currency: "EUR", period: "year" }, { home: "EUR", rates, locale: "en-GB" });
  assert.equal(same.primary, "€75K–€90K");
  assert.equal(same.posted, null);
  const conv = formatPay({ min: 70000, max: 85000, currency: "GBP", period: "year" }, { home: "EUR", rates, locale: "en-GB" });
  assert.match(conv.primary, /^≈ €80K–€97K$/);
  assert.equal(conv.posted, "£70K–£85K");
});

test("no rate shows the posted amount and says so; no pay stays empty", () => {
  const out = formatPay({ min: 2400000, max: null, currency: "ARS", period: "month" }, { home: "EUR", rates: null, locale: "en-GB" });
  assert.equal(out.converted, false);
  assert.equal(formatPay({ min: null, max: null, currency: null, period: null }, { home: "EUR", rates: null, locale: "en-GB" }), null);
});
```

**Implement:** `Intl.NumberFormat(locale, { style: "currency", currency, notation: "compact", maximumFractionDigits: 0 })` with `formatRange`. It is Baseline since 2023, but guard `typeof fmt.formatRange === "function"` and fall back to joining both ends with "–". Use `currencyDisplay: "narrowSymbol"` for the home currency and `"symbol"` for others, so an unclear "$" reads as "US$" or "CA$". Conversion mirrors `money.py` and reads rates from `GET /api/fx/rates`. Replace `formatMoney` / `formatSalary` in `components/job-extracted-fields.tsx:51-85` with this module, and drop their USD default.

**Commit:** `feat(money): one formatter for pay, with ≈ for converted figures`.

### Task 3.6: Work-permit answers per country

**Files:**
- Modify: `backend/app/schemas/autofill_profile.py` (add `WorkAuthByCountry = dict[str, WorkAuth]`)
- Modify: `backend/app/services/autofill_profile.py` (`get_work_auth(session, country: str | None)`, read-time mapping)
- Modify: `backend/app/services/autofill_job.py:24-31` (`profile_for_job` resolves `work_auth` for the job's `country_code`)
- Create: `backend/app/services/autofill_country.py` (`country_in_question(question, apply_in) -> str | None`)
- Modify: the slot value lookup for `work_auth.*` keys (find it with `rg -n "work_auth\." backend/app/services/autofill_map.py backend/app/services/autofill_slots.py backend/app/services/autofill_pick.py`)
- Modify: `backend/app/services/setup_status.py:70-98` (work-permit completeness per apply_in country)
- Test: `backend/tests/test_autofill_country.py` (new)

**Rule (D9):** the answer comes from the country the question names. If the question names none, it comes from the job's country. If the job has none, the answer is unknown: the Companion reports `missing_source` and asks once on that job, as for any unknown knockout answer. Remote multi-country jobs rarely ask.

**Step 1: Failing tests**

```python
def test_the_country_the_question_names_wins():
    profile = {"work_auth_by_country": {
        "DE": {"authorized_now": True, "sponsorship_now": False},
        "UK": {"authorized_now": False, "sponsorship_now": True},
    }, "home": "DE"}
    q = "Are you legally authorised to work in the United Kingdom?"
    assert autofill_country.country_in_question(q, ["DE", "UK", "US"]) == "UK"
    assert work_auth_for(profile, question=q, job_country="DE").authorized_now is False


def test_no_country_in_the_question_uses_the_job_country_then_asks():
    profile = {"work_auth_by_country": {"DE": {"authorized_now": True}}, "home": "DE"}
    assert work_auth_for(profile, question="Authorized to work here?", job_country="DE").authorized_now is True
    assert work_auth_for(profile, question="Authorized to work here?", job_country=None).authorized_now is None


def test_a_legacy_single_work_auth_belongs_to_the_home_market():
    legacy = {"work_auth": {"authorized_now": True}}
    assert work_auth_for(legacy, question="", job_country="US", home="US").authorized_now is True
    assert work_auth_for(legacy, question="", job_country="UK", home="US").authorized_now is None
```

**Implement.** `country_in_question` matches the label and the aliases from `countries.yaml` for each country in `apply_in`, case-insensitively and on word boundaries. It returns the country only if exactly one matches. Store per-country answers under `work_auth_by_country` in the autofill JSON. The legacy top-level `work_auth` reads as the home market's entry, mapped when read and kept as written until the user saves (the veteran precedent in `autofill_profile.py`). `profile_for_job` sets `profile["work_auth"]` to the job country's set, so existing slot code keeps working. The question-country override happens at slot lookup, where the question text is known. `WorkAuth.countries_authorized` stays readable and is derived from the keys whose `authorized_now` is True. The extension reads the resolved `work_auth`, so no extension change is needed. Confirm with `rg -n "work_auth" extension/` and pin it in the test.

**Step 4:** Run the new tests and the autofill suites (`.venv/bin/python -m pytest tests/ -q -k autofill -n auto --dist loadfile`).

**Step 5:** Commit `feat(autofill): work-permit answers per country`. Update SYSTEM.md (§6 invariant: a knockout answer is never guessed, now per country) and add a §13 row `autofill-work-auth-by-country`.

### Task 3.7: Diversity sets per country, consent stays in Profile

**Files:** `market_settings.offers_eeo(session, country)`. `setup_status._autofill_step` counts EEO answers only for apply_in countries with a module (US, UK today). Keep `eeo_consent` as it is (D10). Test `tests/test_setup_status.py`.

**Failing test:** a user who applies in DE only gets no EEO group. DE + US gets the US set.

**Commit:** `feat(autofill): a diversity set only for countries with a checked one`.

### Task 3.8: Salary checks compare one currency

**Files:** `backend/app/services/knockout.py:144-191`, `frontend/components/knockout/job-knockout-card.tsx:77` (find it with `rg -n "desired_salary" frontend/components`). Job preferences "Minimum salary" (`schemas/job_preferences.py:81`) becomes `{amount, currency}`, with the currency defaulting to home and a read-time map from the old free text when it parses as a number. Test `tests/test_knockout.py`.

**Failing test:** a desired salary of €70,000 against a ceiling of £60,000 converts (≈ €68,400) before comparing. With no rate it returns "can't compare", never a pass or a fail.

**Commit:** `fix(knockout): salary checks convert to one currency`.

### Task 3.9: Market analytics in the home currency

**Files:** `backend/app/services/explore_overview.py:49-58, 91-96, 127-155`. Test `tests/test_explore_router.py`.

**Failing test:** "Yearly pay by role" returns ranges in the home currency, with `converted_count`, `posted_currencies` and `rate_date`. A role with fewer than 5 jobs that list pay is listed under `hidden_roles`. Jobs whose currency has no rate are counted in `unconverted`. The server-side `_SYMBOLS` / `_thousands` text goes: the payload carries numbers and the browser words them with `lib/money.ts`.

**Commit:** `feat(analytics): pay by role in your currency`.

### Phase 3 gate

Run it, plus the alembic round trip on a scratch copy of real data: `backend/scripts` has the snapshot tools, and a backup in `~/Library/Application Support/Maestro Career Studio/backups/` restored to `/tmp` works. Do not open the live file. CHANGELOG: several countries, home currency, ECB rates, the "$" and hours fixes.

---

## Phase 4: Lists (Jobs, Agent inbox, Job page, Automations)

### Task 4.1: Jobs list

**Board:** Jobs, fewer words.

**Files:** `frontend/app/applications/page.tsx` (table at `<TableHeader>`). Pins: `backend/tests/test_frontend_jobs_where.py`, `test_frontend_jobs_page_words.py`, `test_frontend_jobs_honest_words.py`. Read them first and change each pin to the new rule.

**Target:**
- Columns are Role (monogram, title, "Company · Place"), Match (ScoreBar and number), Status (StatusChip and date), Next step (`NextStep`) and a 32 px trailing slot. The trailing slot holds `JobOwnershipPopover` (from main `components/job-ownership.tsx`) only when the job is not on your laptop.
- No Where column, no Resume column, no Added column (sorting by added stays in the sort menu).
- Filter chips are All active, Ready to apply, Waiting to hear, Interviews and Closed, with counts. Status, level, country and resume filters sit behind "Filters".
- A quiet Select button turns on the Agent inbox's Select mode: a checkbox on each row and a bottom bar. Bulk actions are only those the existing bulk endpoints allow (Archive, Move to closed). If none exist, the bar offers Archive only. Add no new bulk semantics in this task.
- No page subtitle. The header shows the title, a count and the search box.
- Rows carry `group/row` for NextStep's hover fill.

**Tests to write first** (new `test_frontend_jobs_refresh.py`):

```python
def test_jobs_table_has_no_resume_where_or_added_column():
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    for gone in (">Resume<", ">Where</TableHead>", 'header("created_at"'):
        assert gone not in head


def test_every_next_step_uses_next_step_and_rows_are_hover_groups():
    assert "<NextStep " in _PAGE and "group/row" in _PAGE
    assert 'variant="secondary"' not in _TABLE  # no tonal buttons at rest in rows


def test_select_mode_and_ownership_popover_come_from_the_inbox():
    assert "JobOwnershipPopover" in _PAGE and "selectMode" in _PAGE
```

**Commit:** `feat(jobs): five columns, one next-step style, Select mode`. CHANGELOG.

### Task 4.2: Agent inbox lanes as one list card

**Board:** Agent inbox, same rows.

**Files:** `frontend/components/proposals/proposals-section.tsx`, `triage-actions.tsx`, `app/proposals/page.tsx`. Pin: `backend/tests/test_frontend_agent_inbox.py`.

**Target:** each lane is one `bg-card` card holding 60 px rows, not a tall card per job.
- **Header:** three counts (to approve, queued, sent this week) replace the subtitle, and the lock line "Nothing is sent without your yes" stays.
- **Controls:** one sort select, with the other filters under "Filters".
- **Kept as they are:** Select mode and its bottom bar from `d1cd976a` (Queue is the one filled button in the bar), and the resume square on rows (D2).
- **Row content:** a question from the agent is a single truncated line. History is a Fold.

**Commit:** `feat(inbox): lanes as one list, header counts`.

### Task 4.3: Job page lead card and folds

**Board:** Job page.

**Files:** `frontend/app/jobs/[id]/page.tsx` and the step components (`rg -n "JobSteps|job-steps" frontend/components -l`). Pins: `rg -n "jobs/\[id\]" backend/tests -l`.

**Target:**
- **Stepper:** four steps with a 4 px progress bar each, a check icon and one number ("18 skills", "6 of 6 closed", "58 → 81"). No sentences.
- **Current step:** a `LeadCard`. For Apply, it shows the tailored resume thumbnail with the 6 px resume band and a `ResumeTag` footer, the score, a gain `DeltaChip`, the filled "Open the job post" button, "Mark as applied" as an outline button, and two tonal rows, Cover letter and Form questions.
- **Folds:** Job description, Autofill answers ("34 from your profile") and Details and history.
- **Header:** title, "Company · Place · Mode · pay" (pay from `lib/money.ts`), StatusChip and the menu.

**Commit:** `feat(job-page): one lead card per step, the rest folded`.

### Task 4.4: Automations from real reports only

**Board:** Automations, agents in control.

**Files:** `frontend/app/automations/page.tsx`, `frontend/components/automations/automation-card.tsx`, `recent-runs.tsx`. Data: `GET /api/agent-runs?limit=200` (`backend/app/routers/agent_runs.py:32`), which gives the runs for the 14-day strip, and `/latest`. Pin: `backend/tests/test_frontend_automations.py`.

**Target:**
- **How-it-works strip:** Copy a prompt → Your agent schedules it → Each run reports here.
- **Reporting:** cards for automations with a run in the last 14 days. Each has a `DayStrip`, a status line ("2 hours ago · 3 updated · by Claude", built from `counts`, `agentDisplayName` and `on_bot`), Copy prompt, and one link to the result ("Last report" for the digest, "4 in Agent inbox" when `proposed > 0`).
- **No reports yet:** compact rows with Copy prompt.
- **Folded:** Recent runs and "What each one never does".
- **Never shown:** connection dots, schedules, app names on buttons, logos (D5).

**Tests first:**

```python
def test_automations_show_no_schedule_or_connection_state_they_cannot_know():
    page = _src("app/automations/page.tsx") + _src("components/automations/automation-card.tsx")
    for invented in ("connected", "Runs weekdays", "Open in Claude", "logo"):
        assert invented not in page
    assert "<DayStrip" in page and "Copy prompt" in page
```

Keep `test_wrappers_name_no_agent_app_or_scheduler` green.

**Commit:** `feat(automations): status from reports, one Copy prompt per card`.

### Task 4.5: Motion where something happens

**Board:** Motion specimens.

**Files:**
- `frontend/components/status-chip.tsx`: a cross-fade with 2 px blur between old and new, then the existing `animate-confirm` pulse.
- The AI wait sites: replace spinners with `WorkingDots` (find them with `rg -n "Writing…|Answering…|Adapting…|Applying…" frontend/components frontend/app`). The Button `pending` spinner stays on buttons; WorkingDots is for a region that waits on AI.
- Save confirmations: `CheckDraw` where "Saved" already holds (`hooks/use-saved-hold.ts`).
- Stat tiles: `NumberRoll` in place of `useCountUp` for whole numbers. Keep `useCountUp` for decimals.
- Jobs row → job page: a View Transition naming the monogram and the title (`view-transition-name` from the job id).
  - Next 16.3.8 and React 19.3 need no flag (`node_modules/next/dist/docs/01-app/02-guides/view-transitions.md`; read it first, per `frontend/AGENTS.md`).
  - Set `default="none"`, so only the named pair morphs.
  - The morph takes 250 ms, with fades only under reduced motion.
  - Back navigation still morphs by name, with no slide.

**Tests:** extend `test_frontend_motion.py`.
- Every new duration is ≤ 400 ms.
- No animation on keyboard-initiated actions: grep the new code for `onKeyDown` handlers that start an animation, and assert there are none.
- The reduced-motion block covers `.working-dot`, `animate-check-draw` and `::view-transition-group(*)`.
- The view transition names only the monogram and the title.

**Commit:** `feat(motion): status cross-fade, working dots, check draw, row-to-page morph`. CHANGELOG.

### Task 4.6: Fewer words on the pages without a board

**Pages:** Career history (the wordiest: 59 sentence-length strings, 54 muted paragraphs), Base resumes, Templates, Referrals, Assistant.

**Rule:** a copy pass, not a redesign.
- Remove page subtitles (D1).
- Delete hints that restate their label.
- Move the rest of a section's explanatory paragraphs into a `Fold` or a tooltip, keeping one line where a consequence must be seen before acting.
- Turn sentence summaries into numbers or chips.
- No layout changes. Career history gets its own board and design pass later (ask the owner).

**Tests:** a pin that these pages' `PageHeader` has no `description` prop, and a ratchet asserting the count of muted `<p>` elements per page folder (counted like the 2026-10-20 audit) falls by at least half. Record the before and after counts in the commit body.

**Commit:** `refactor(copy): fewer words on Career history, Base resumes, Templates, Referrals, Assistant`.

### Phase 4 gate

Run it, plus a browser pass at 1280 and 1024, light and dark, on the fresh stack with seeded sample data.

---

## Phase 5: Analytics rebuild

### Task 5.1: Wilson range and the search summary

**Files:** `backend/app/services/rates.py` (from Task 1.5), create `backend/app/services/search_summary.py`, add the route `GET /api/explore/search-summary?weeks=12&source=all` in `backend/app/routers/explore.py`. Test `backend/tests/test_search_summary.py`.

**Step 1: Failing tests**

```python
from app.services import rates


def test_wilson_range_matches_the_textbook_and_hides_below_twenty():
    low, high = rates.wilson(12, 64)
    assert round(low, 3) == 0.111 and round(high, 3) == 0.300
    assert rates.rate(12, 64) == {"count": 12, "of": 64, "rate": 0.1875, "low": low, "high": high}
    assert rates.rate(5, 12) == {"count": 5, "of": 12, "rate": None, "low": None, "high": None}


def test_summary_counts_from_events(db_session):
    # Seed 25 applications applied over 8 weeks; events: 6 replies (rejected or interviewing) with
    # real timestamps, 2 interviews, 1 offer, plus 3 backfilled events.
    # Assert: applied 25; heard_back 6 (backfilled counted for status, not timing);
    # median_days_to_reply uses only non-backfilled events; quiet_30 counts applied ≥ 30 days ago
    # with no event after applying; weekly series zero-filled; by_resume groups by application.base_resume.
    ...
```

**Implement `rates.py`**

```python
from math import sqrt

MIN_RATE_N = 20
Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval: safe at small n and near 0 or 1 (Brown, Cai and DasGupta, 2001)."""
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(successes: int, n: int) -> dict:
    """A rate only from MIN_RATE_N in the denominator (owner D7); below it, counts alone."""
    if n < MIN_RATE_N:
        return {"count": successes, "of": n, "rate": None, "low": None, "high": None}
    low, high = wilson(successes, n)
    return {"count": successes, "of": n, "rate": successes / n, "low": low, "high": high}
```

**Summary definitions:**
- **Applied:** `applied_at` in the window.
- **Heard back:** any event to rejected, interviewing, offer or accepted after `applied_at`, or a current status in that set.
- **Interview:** ever had an interviewing event, or a current status of interviewing or later.
- **Offer:** the same rule for offer.
- **Median days to hear back:** non-backfilled events only. Show the median and the 25th–75th percentile when there are at least 5 replies, otherwise `null` with the count so far.
- **Quiet after 30 days:** count only applications whose `applied_at` is 30 or more days ago.
- **Applied per week:** the mean over the window.
- **Score gain:** the existing tailoring-lift median.
- **By resume:** applied, heard back and interview per `base_resume`, each through `rate()`.

The 30-day window and the at-least-5 rule are named constants with a comment saying why. Sources disagree on a "no reply" window (14 to 45 days), so 30 sits between them.

**Commit:** `feat(analytics): search summary from dated events`. SYSTEM.md §7 endpoint list.

### Task 5.2: Analytics page

**Board:** Analytics.

**Files:** `frontend/app/analytics/page.tsx`, `frontend/components/analytics/*`, `frontend/components/explore/*`. Pins: `test_frontend_analytics.py`, `test_frontend_jobs_honest_analytics.py`. Update the pinned captions to the new words.

**Target:**
- **No tabs:** one page with a period control (4 weeks, 12 weeks, All) and the source toggle.
- **Lead:** "Where your applications went", a funnel `LeadCard` with counts, rates with Wilson ranges from 20 and "5 of 12" below, plus the two rule chips.
- **Also:**
  - four tiles: applied per week with a sparkline, time to hear back with its range, quiet after 30 days, and score gain;
  - an "Each week" bar chart of applied and replies;
  - "By resume", coloured by resume (`ResumeSwatch`).
- **Jobs you saved:**
  - yearly pay by role in the home currency, with the conversion chip and a "hidden: under 5" chip;
  - work mode as a segmented bar;
  - skills jobs ask for (top 5, plus a count of the rest);
  - most common gaps (one card, Quick wins removed).
- **Folded:** "Match scores in detail" (the current fit charts), "Market in detail" (level, places, the work-permit breakdown per apply_in country), and "How these are counted".
- **Removed:** the OPT tile and Autofill coverage (D6 moves it, Task 7.6).

**Tests first:** a pin that `autofill-coverage-card` is not imported by `app/analytics/page.tsx`, that "OPT" appears nowhere on the page, and that rates render through a `RateLabel` component which shows "x of n" when `rate` is null.

**Commit:** `feat(analytics): one page, honest rates, pay in your currency`. CHANGELOG.

---

## Phase 6: Today page as home

### Task 6.1: Today summary endpoint

**Files:** create `backend/app/services/today.py` and `GET /api/today` (new router `backend/app/routers/today.py`, registered in `app/main.py`). Test `backend/tests/test_today.py`.

**Payload:**
- `next_up`: the single most important item, chosen in order: an application with an offer awaiting a response, then a draft with a PDF ready and the best match, then a proposal needing your answer.
- `also`: up to three counts with links: agent jobs to approve, tailored resumes to check, quiet 14 days.
- `more`: counts behind "N more": gaps to close, resumes to health check.
- `week`: applied per day for 7 local days, replies and interviews this week.

Every count comes from existing queries (setup status, proposals funnel, the needs-you count hook's source, the status events). The order rule and the 14-day window are named constants.

**Failing tests:** for each priority, seed data where the higher item exists, and assert it wins. With nothing to do, `next_up` is null.

**Commit:** `feat(today): one next-up and three counts`.

### Task 6.2: Today page and the new home route

**Board:** Today page.

**Files:** create `frontend/app/today/page.tsx`. Modify `frontend/app/page.tsx` (redirect to `/today` instead of `/applications`) and `frontend/components/app-sidebar.tsx:34-63`.

**Target:**
- **Sidebar order:** Today (with the needs-you badge), Jobs, Agent inbox, Resumes, Career history, Analytics. Then "More tools" (Automations, Referrals, Templates, Assistant). Profile and Settings sit at the bottom.
- **Next up:** a LeadCard with the one filled button and "Where this job is" step dates.
- **Also today:** three cards with NumberRoll counts.
- **Below:** a "N more" Fold, then This week (bars).
- **Empty state:** a new user without a key or a resume sees Setup's entry card instead (Task 7.1).

**Test (pin):** `app/page.tsx` redirects to `/today`, the sidebar lists Today first, and More tools is a disclosure with `aria-expanded`.

**Commit:** `feat(today): Today is the home page`. CHANGELOG.

---

## Phase 7: First run, Profile and Settings

### Task 7.1: Setup flow

**Board:** Setup in four steps (clickable).

**Files:** create `frontend/app/setup/page.tsx` and `frontend/components/setup/setup-flow.tsx`, reusing `components/setup/setup-steps.ts`. Data: `GET /api/setup/status` (`backend/app/routers/setup.py:18`) plus the existing write endpoints: keys and model test (Settings › AI), resume import (the upload dialog), market (Task 3.2), autofill (`PUT` the profile), job preferences. Test `backend/tests/test_frontend_setup_flow.py` (new) and `test_setup_status.py`.

**Target:**
- **Rail:** four steps, each with a time estimate, and a progress bar.
- **Step 1, AI model:** five provider cards (Claude, OpenAI, Gemini, OpenRouter, your own server) named in text, with no logos. Key and Test go through the existing test endpoint, with WorkingDots while checking and capability chips after.
- **Step 2, resume:** one drop zone. The found counts (roles, bullets as drafts, skills, degrees) come from the import response.
- **Step 3, where and what:** "You live in" (one), "You apply in" (chips), roles suggested from the resume, and work mode.
- **Step 4, form answers:** one question at a time. Work-permit questions come first, one per apply_in country (Task 3.6). Then notice period, relocation, and diversity (answer or decline, only for countries with a set). Contact fields come from the resume.
- **Done screen:** Add your first job (filled), Connect an agent app, Add the Companion.
- **Navigation:** Skip for now on every step. Back is free.
- **When it shows:** on first launch (no key and no resume), and from Today's setup card until every required step is done. "Run setup again" sits in Settings › Basics.

**Tests:** pins that each step writes through an existing endpoint (no new write route), that each work-permit question carries its country, and that the provider cards hold no `<img`.

**Commit:** `feat(setup): a four-step first run`. CHANGELOG.

### Task 7.2: Profile as tiles

**Board:** Profile, facts about you; Where everything lives (the Profile group).

**Files:** `frontend/app/profile/page.tsx`, `frontend/components/settings/autofill-section.tsx` (1448 lines: split it by tile into `frontend/components/profile/*`), `persona-section.tsx`, `job-preferences-section.tsx`, `market-section.tsx`. Pins: `test_frontend_settings_autosave.py`, `test_frontend_settings_pages.py`, `test_frontend_autofill_gaps.py`.

**Target:**
- **Header:** name, a one-line summary ("lives in … · applies in …") and a completion ring from `SetupStatus`.
- **Next up:** the first unanswered required item, answered in place, with the Profile board's line beside it ("Never guessed for you").
- **Tiles:** Contact, Where you apply (country chips; the chip shows a base resume's square when that resume stores the country), Work permits (one line per apply_in country), Jobs you want, How you come across, Start and pay, Education, Languages, Your own questions.
- **Folds:** Diversity (per country with a set, with the consent toggle and consent date beside the answers, D10) and Eligibility.
- **Saving:** every field saves as you go. Remove the Autofill tab's Save button and reuse the `AutosaveStatus` pattern.
- **Moves out:** agreements and signatures and the screening-answer setting go to Settings › Companion (Task 7.3).

**Coverage test (write first): every Profile item from the map has a home.**

```python
PROFILE_ITEMS = [
    "First name", "Last name", "Email", "Phone", "Street address", "Address line 2", "City", "State",
    "Postal code", "Country", "LinkedIn profile link", "GitHub link", "Website", "Fill from career history",
    "You live in", "You apply in", "Work authorization status", "Authorization expires on",
    "Roles you want", "Years of experience", "Work location", "Locations", "Minimum salary", "Job types",
    "Persona", "Draft from my career history", "Desired salary", "Notice period", "Earliest start date",
    "Willing to relocate?", "How did you hear about the job?", "School", "Degree", "Major", "GPA",
    "Start year", "Graduation year", "Add education", "Language", "Add language", "Add question",
    "Let the Companion fill these answers", "Are you a veteran?", "Disability status", "Gender",
    "How you describe your gender", "Hispanic or Latino?", "Race or ethnicity", "Decline the rest",
    "Are you 18 or older?", "Have you worked for the company you're applying to?",
    "Subject to a restrictive covenant?",
]


def test_every_profile_item_still_has_a_home():
    src = "".join(p.read_text() for p in (_FRONTEND / "components/profile").glob("*.tsx"))
    src += _src("app/profile/page.tsx")
    missing = [label for label in PROFILE_ITEMS if label not in src]
    assert not missing, missing
```

Work-permit questions are worded per country from the market's `work_auth_vocab`, so pin their keys (`authorized_now`, `sponsorship_now`, `sponsorship_future`) per country instead of US wording.

**Commit:** `feat(profile): facts about you as tiles, saves as you go`. CHANGELOG.

### Task 7.3: Settings tabs: Basics, Companion, Agent apps, Advanced

**Board:** Settings, how the app behaves; Where everything lives (the Settings groups).

**Files:** `frontend/app/settings/page.tsx`, `frontend/components/settings/settings-tabs.tsx`, `lib/settings-tabs.ts` (anchors), and every section file listed in the map. Pins: `test_frontend_settings_cards.py`, `test_frontend_settings_pages.py`, `test_frontend_settings_assistant_words.py`.

**Target:**
- **Basics:**
  - **AI model card:** provider, status and capabilities, Test again, Change provider; three plain-word model rows; "Use recommended models" (Task 7.4); other provider keys in a Fold.
  - **Also:** Money (Task 3.4), Resume PDFs, and Appearance (Light, Dark, Like my computer).
  - **Footer:** About and "Run setup again".
- **Companion:** what it may fill (agreements and signatures with their date, the screening-answer setting), how it applies (choose the base resume for me, stop after each step, think when stuck, fields it couldn't operate), and the form-filling engine (Jev key, provider, decisions model, Test).
- **Agent apps:**
  - connect an app (tool set and every app command);
  - what agents can and can't do (a Fold);
  - limits: full automation, per-day, per-search, move after days, lowest score, lead needed, companies to skip;
  - accounts and copies: job-site login, next-step hints, second copy.
- **Advanced:**
  - model per job (Fast, Smart, Assistant, Reasoning, with Test and badges, "Which model should I pick?");
  - more models (find per provider, the list, your own AI server);
  - AI instructions (all 22);
  - Quick tailor (4 toggles and the extra instruction);
  - Hours per year (Task 3.4);
  - Diagnostics (Autofill coverage and Clear data, D6).
- **Old URLs keep working:** `?tab=ai`, `?tab=tailoring`, `?tab=agents`, `?tab=appearance` and `?tab=about` redirect to the new tab and anchor.

**Coverage test (write first):** the Settings item list from the map (Basics 23, Companion 11, Agent apps 26, Advanced 22 labels, as on the board), asserted present across `components/settings/*.tsx`, the same way as Task 7.2. A second test asserts each old `?tab=` value maps to a new tab.

**Commit:** `feat(settings): four tabs by purpose, nothing removed`. CHANGELOG.

### Task 7.4: Use recommended models

**Files:** `backend/app/services/model_settings.py`, create `backend/app/services/data/recommended_models.yaml` (per provider: fast, smart, assistant, reasoning model ids from the existing built-in catalog), add `GET/PUT /api/settings/models/recommended` in `routers/settings.py`. Test `backend/tests/test_model_settings.py`.

**Failing test:** with only a Claude key saved and recommended on, the four roles resolve to the catalog's Claude ids. Turning it off keeps the user's picks. A recommended id missing from the catalog fails a data test, so the YAML can't name a model the app can't call.

**Commit:** `feat(models): a recommended set per provider`.

### Task 7.5 (optional, owner to confirm): Remember the last model test

**Files:** a JSON text setting `model_tests` (`{model_id: {ok, capabilities, at}}`) written by the existing test endpoint. The AI model card shows "tested 3 days ago" only from this. Until it lands, the card shows capabilities from the catalog. Ask the owner before building.

### Task 7.6: Autofill coverage moves to Diagnostics

**Files:** move `frontend/components/analytics/autofill-coverage-card.tsx` under Settings › Advanced › Diagnostics, unchanged apart from its heading. Pin: Analytics no longer imports it, and the Settings Advanced tab does.

**Commit:** `refactor(settings): autofill coverage lives under Diagnostics`.

---

## Phase 8: Docs, design system, full verification

### Task 8.1: Design system docs and artifact

Update `docs/design-system/README.md` and the component cards:
- the tiers;
- NextStep, Fold, LeadCard, DayStrip, NumberRoll and WorkingDots;
- the resume-square rule (D2: inbox rows, the tailored-resume card on the job page, Today and charts; never the Jobs list);
- neutral monograms;
- the chart palette;
- money display rules (≈, the posted amount, one rate date per page);
- the country rules for forms.

Then sync the claude.ai Design System artifact (https://claude.ai/artifact/VxnjspbkP71d8Z183QqrB7, memory: design-system-rollout) with the README and `tokens.json`. Commit `docs(design-system): refresh rules and primitives`.

### Task 8.2: SYSTEM.md and the ledgers

Sweep SYSTEM.md for every section whose subject changed:
- §4: Job.country_code, status events, money and rates, markets;
- §6: per-country knockout answers, status writes through `set_status`;
- §7: new endpoints;
- §8: the frontend tiers;
- §13: migration rows for the market split and work_auth_by_country.

Run `python3 scripts/check_system_md.py`. Add gotchas this work paid for (symptom → cause → rule, ≤ 3 lines each). Commit `docs: SYSTEM.md for the design refresh`.

### Task 8.3: Full verification

1. Full backend suite with xdist; the frontend `tsc`, lint and build; the slop ratchet for backend, frontend and extension, each named.
2. Fresh stack seeded with the sample persona: a product designer in Berlin who applies in DE, UK and US, has 4 base resumes, 86 jobs in EUR, GBP and USD, and status events. Walk the first run on an empty data dir first, then every board's page at 1280 and 1024, light and dark.
3. Compare each page with its canvas board. Log any intentional difference in the final summary.
4. A real-data check on a restored backup in `/tmp` (never the live file): the migrations run, legacy `market` and `work_auth` read correctly, and every old Settings URL lands on the right tab.
5. Goal-critique (goal-anchored-delegation): review the result against the Goal Card, not this plan. Default to approve. Name a Goal Card line for each finding.

Commit `chore: verification notes for the design refresh` with the summary in the body. Do not push. The owner pushes on their say-so.

---

## Done means

- Every board on the canvas has its page, built on real data.
- Every one of the 156 Profile and Settings items has a home, pinned by the coverage tests in Tasks 7.2 and 7.3.
- No rate shows below 20. No pay is invented. No status or schedule is shown that the backend does not have.
- The suites and gates are green, the ratchets are named, SYSTEM.md and the design system docs and artifact are updated, and the CHANGELOG `[Unreleased]` lists the user-visible changes.
