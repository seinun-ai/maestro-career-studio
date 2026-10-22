# Design refresh: handoff

For the owner's local pass. Plan: [`2026-10-20-design-refresh.md`](2026-10-20-design-refresh.md). Visual spec: the
Design canvas (claude.ai artifact `C3WyCrgSJ4fwyqQp6RX28D`), read as data for every board.

## Where things stand

- **Branch:** `claude/modest-ride-js0by8`, started from `a2ae0312` (the 51 local-only commits of
  `claude/maestro-design-system-refresh-d50b59`). Pushed at the end of every phase. Never pushed to main, no PR,
  no merge.
- **Plan tasks:** 46 of 47 done, one commit each. Task 7.5 is skipped (the owner has not confirmed it). Task 8.3's
  cloud half is done; its local half (browser, real data, slop ratchet, artifact sync) is listed under
  [Checks still to run](#checks-still-to-run).
- **Beyond the tasks:** two review rounds over the whole diff found 12 defects; each is fixed in its own commit
  (listed under [After review](#after-review)). Two more follow-ups: old Settings and Profile places in messages,
  and pins for all 156 board items.
- **Gates:** every phase gate passed with zero new backend failures against the container baseline, plus
  `tsc`, `lint`, `build` and the SYSTEM.md gate. Final numbers are under [Test record](#test-record).
- **History:** three local rewrites happened before any push (a split of one commit that swept another agent's
  staged files, one rebuilt commit, one amend). Pushed history was never rewritten.

## How it was built

Each task ran as a subagent with the plan's Goal Card, D1–D11 and ground rules as binding text, test first, one
commit per task, with `Deviation: <planned> → <done>, because <Goal Card line>` in the commit body. Backend and
frontend work ran side by side in this one checkout, so every gate ran on a clean snapshot worktree of the
commit under test and was compared, test id by test id, with a baseline taken at `a2ae0312`.

## What landed, by phase

### Phase 0: shared primitives and tokens

| Task | Commit | What |
|---|---|---|
| 0.1 | `fcacd08` | Chart series in OKLCH at even lightness, light and dark; 3:1 on `card` pinned (lowest: chart-2 light, 3.81) |
| 0.2 | `56fc15e` | Neutral monograms (`surface-container-highest`, no hash) |
| 0.3 | `dada5fc` | `Fold`, the folded tier |
| 0.4 | `db3bfe5` | `NextStep`, one style for a row's next move (D3) |
| 0.5 | `6294361` | `LeadCard`, the lead tier (one filled action) |
| 0.6 | `c9bd837` | `NumberRoll`, `WorkingDots`, `CheckDraw`, `ROLL_MS`, reduced-motion rules |
| 0.7 | `25b13f8` | `DayStrip` (local calendar days, worst outcome wins) |
| docs | `8ca122b` | Design-system README and seven component cards |

### Phase 1: analytics correctness and clean values

| Task | Commit | What |
|---|---|---|
| 1.1 | `743f8e9` | Best-paying role compares one currency (later converted pay, 3.9) |
| 1.2 | `a4c92b2` | Skills by role numerator honours every filter |
| 1.3 | `2d9e4f3` | Roles over time follows the filters and zero-fills weeks |
| 1.4 | `783e742` | Match score over time reads one base per job |
| 1.5 | `1d4c6c7` | `services/rates.py` `MIN_RATE_N = 20`; no percentage below 20 |
| 1.6 | `cf85f12` | Score gain follows the All / Yours / Agents toggle |
| 1.7 | `7f150a4` | A failed chart shows the load-error state |
| 1.8 | `5c9ef5a` | `jobs.country_code` (migration `2d3de2d60a4c`, backfilled), work mode and level stored as keys |
| 1.9 | `06c1ee7` | "40 hours per week" is not pay |
| 1.10 | `f1f8afc` | A bare "$" takes the job's country currency, flagged `salary_currency_assumed` (migration `ff9591f140f7`) |
| gate | `16d3c62` | CHANGELOG lines |

### Phase 2: status-event log

| Task | Commit | What |
|---|---|---|
| 2.1 | `43c0566` | `application_status_events` (migration `c5b4833bcc54`, one backfilled row per application with a status); a job-child table for sync |
| 2.2 | `32347c3` | `application_status.set_status` is the only writer; AST guard test; §6 `inv-status-through-set-status` |

### Phase 3: countries and money

| Task | Commit | What |
|---|---|---|
| 3.1 | `7d1fabc` | Germany and the Netherlands as market data |
| 3.2 | `adc111b` | `home` + `apply_in`; a stored `{"market": X}` reads as home X, apply in [X]; §13 row `market-home-apply-in` |
| 3.3 | `c6f0f32` | A job's default currency is its country's, else the home's, marked assumed |
| 3.4 | `119780b` | Money settings, ECB daily reference rates (`GET /api/fx/rates`, `POST /api/fx/rates/refresh`), pure-Decimal `money.py` |
| 3.5 | `a558145` | `lib/money.ts` `formatPay`: ≈ on converted figures, the posted amount kept, no rate → as posted |
| 3.6 | `6bf1e1a` | Work-permit answers per country (`work_auth_by_country`); §6 `inv-work-permit-per-country`; §13 row |
| 3.7 | `f0fc3d7` | A diversity set only for apply-in countries with a checked one |
| 3.8 | `7eaae64` | Salary checks convert to one currency; no rate → "Can't compare" |
| 3.9 | `ae70f58` | Pay by role in the home currency; roles under 5 paid jobs hidden and counted |
| gate | `9c09026` | CHANGELOG lines |

### Phase 4: lists, job page, automations, motion, fewer words

| Task | Commit | What |
|---|---|---|
| 4.1 | `b33a18b` | Jobs: five columns, NextStep, filter chips, Filters, Select mode from the Agent inbox, ownership slot |
| 4.2 | `81ad078` | Agent inbox: lanes as one list card, three header counts, History as a Fold |
| 4.3 | `5aea2a1` | Job page: stepper numbers, one LeadCard per step, three Folds, header pay; Jobs Status cell reads `status_since` |
| 4.4 | `5c18cf7` | Automations from reports only: DayStrip, report line, one Copy prompt, nothing it cannot know |
| 4.5 | `6bcab65` | Status cross-fade, WorkingDots, CheckDraw, Jobs row → job page morph (monogram and title only) |
| 4.6 | `8248fe2` | Fewer words on Career history, Base resumes, Templates, Referrals, Assistant |

### Phase 5: analytics rebuild

| Task | Commit | What |
|---|---|---|
| 5.1 | `3df0895` | `rates.wilson` / `rates.rate`; `GET /api/explore/search-summary` from dated events |
| 5.2 | `f5b1de7` | One Analytics page: funnel lead, `RateLabel`, four tiles, Each week, By resume, Jobs you saved, Folds |

### Phase 6: Today as home

| Task | Commit | What |
|---|---|---|
| 6.1 | `c3e1e8a` | `GET /api/today` (next up, also, more, week; local days from `tz` + `utc_offset_minutes`) |
| 6.2 | `8283338` | Today page, `/` redirects to `/today`, sidebar order and More tools |

### Phase 7: first run, Profile, Settings

| Task | Commit | What |
|---|---|---|
| 7.1 | `f553cd7` | `/setup`: four steps, each writes through an existing endpoint; first launch sends a new install there once |
| 7.2 | `9ff8f75` | Profile as tiles and folds, saves as you go, work permits per country |
| 7.3 | `d93c0e0` | Settings: Basics, Companion, Agent apps, Advanced; old `?tab=` values land on the new tab and card |
| 7.4 | `25591dd` | Recommended models per provider (`GET/PUT /api/settings/models/recommended`), one resolver |
| 7.5 | skipped | The owner has not confirmed it |
| 7.6 | `bd91ebf` | Autofill coverage under Settings › Advanced › Diagnostics |
| 7.1 follow-up | `3634574` | Setup step 4 takes diversity (after consent) and contact answers in place, permits per country |

### Phase 8: docs and verification

| Task | Commit | What |
|---|---|---|
| 8.1 | `86b8b52` | Design-system README (D1, D2 square rule, D7, D8, D9/D10 sections), six new cards, `tokens.json` animation and timing |
| 8.2 | `44cc382` | SYSTEM.md sweep (§1–§5, §7, §8, §10 D1–D11 lines, §11, §12, §13), deferred items 53–62 |
| CHANGELOG | `5b43830` | `[Unreleased]` audited against every commit, Breaking changes completed |
| 8.3 | this file | Cloud verification record; local checks below |

## After review

Two read-only reviews ran over the whole diff (`a2ae031..f553cd7`, then `f553cd7..f470ed2`). Every finding below
was reproduced with a failing test before its fix.

| Commit | Finding fixed |
|---|---|
| `3540ada` | Messages and guides still named Settings tabs that no longer exist (new pin over every "Settings ›" place) |
| `d3aa9f3` | An old single work-permit set moved to whatever country "You live in" became |
| `07f90c7` | A save from a page holding one set could overwrite another country's answers (`work_auth_market` marker) |
| `0352b29` | The Companion's pause row saved a work-permit answer into the home country for a job elsewhere |
| `88b2662` | Skills by role printed percentages on 3 jobs (D7) |
| `281e500` | Today's counts did not match where they lead (expired proposals, the quiet link) |
| `f470ed2` | DayStrip's "14 days ago" (it is 13); WorkingDots was not announced reliably |
| `16886ae` | An open Profile tab could revert answers the Companion had just learned |
| `99333d4` | Messages still sent people to "Profile › Autofill" (pin extended to "Profile ›" places) |
| `96df563` | "Saved" could show while another editor's write was still in flight |
| `4e74281` | Setup's "Decline them all" declined less than it said; diversity answers without consent read as done; the pause row's wrong reason for a country with no market |
| `2a601d5` | A bare `:root` motion token compiled to nothing (pin added) |
| `ab8eb9e` | Pins for all 156 board items: 12 Setup, 62 Profile, 82 Settings, each label tied to the words or keys on screen |
| `6cf07a9` | Several Settings tabs and two cards showed more than one filled button at once; every rebuilt view is now pinned at one |

## Deviations

Every task's deviations are in its commit body; all 100 lines are copied verbatim in
[Appendix A](#appendix-a-every-deviation-line). The ones that change what you will see or decide:

- **Countries:** `countries.yaml` and `countries.py` already existed, so they were extended (plus
  `country_currencies.yaml`); market keys stay `UK` while jobs carry ISO `GB` (`markets.country_code` /
  `for_country` bridge them). Work-permit answers are keyed by market. A question naming a country with no market,
  or two countries, gets no answer (never the job's country by default).
- **Work mode and level are stored as keys** (`on_site`, `senior`), and the 1.8 migration re-spells saved jobs;
  the original text stays in `extracted_json`. Unknown text is kept as its own key rather than guessed.
- **Jobs list:** no archive and no bulk endpoint exist, so Select mode's bar offers Change status, Queue in Agent
  inbox and Delete, each sending the row's own request; Filters holds only the filters that exist (no level or
  resume filter was added); next-step labels come from the server's stage, not the board's samples.
- **Agent inbox counts** read "to review, queued, applied this week" (from `/api/proposals/summary`).
- **Job page:** the "Autofill answers" fold is "What was submitted" and "Form questions" is "Application
  questions" (one word per thing); the board's "Change" beside an assumed currency is left out (no endpoint can
  change a job's currency); the header score pill stays (SYSTEM.md §5 lists it).
- **Automations:** "See in Agent inbox" instead of "4 in Agent inbox" (a run reports how many it proposed, not how
  many are still open).
- **Analytics:** a per-country work-permit breakdown is left out (no payload); "Market in detail" keeps the charts
  Phase 1 made honest; two extra folds (Skill gaps, Agent pipeline).
- **Money:** `Intl.formatRange` is not used (ICU collapses "€75K–€90K" to "€75–90K"); both ends are formatted and
  joined. The ECB cache is machine-local (not shipped as profile); after a failed fetch it retries after an hour,
  otherwise at most one fetch a day.
- **Settings:** while recommended models are on, the Advanced pickers show the set read-only; "13th month" (Money)
  is left out (no field); Hours per year has its own card.
- **Setup:** no stored progress (each step reads done from the data it wrote); first launch redirects once per
  browser, and never when storage is blocked.
- **Profile:** the persona keeps Save and Discard (a drafted persona must be read first); diversity shows one set
  of answers, because the profile stores one (see open questions).
- **Docs:** REST endpoints stay in the reference tier (§7 only indexes agent surfaces); fixes to features that
  never shipped are folded into their CHANGELOG feature lines.

## Skipped or blocked

| Item | Why |
|---|---|
| Task 7.5 (remember the last model test) | Optional and not confirmed by the owner; the AI model card shows status from saved capability tests only |
| Design System artifact sync (8.1) | Needs the owner's claude.ai session; the README's "Not synced" section says what is behind |
| Browser pass at 1280 / 1024, light and dark (Phase 4 and 8.3) | No browser pass was run in the cloud |
| Real-data migration check on a restored backup (Phase 3, 8.3) | Your backups live on your machine |
| Slop ratchet, every surface | The scanner lives in your home directory |
| A live ECB fetch | The container's proxy refused `www.ecb.europa.eu` (403); the parser fixture is hand-written in the ECB's published format and says so |
| `bundle.css` and component previews | Not regenerated (old chart hexes; JobsTable, Sidebar, PageHeader previews show old layouts) |
| `docs/assets/connected-agents.png` | Still shows the old Settings tab (alt text updated) |

## Open questions for the owner

Ordered by how much the answer changes. Items with a deferred-ledger number are tracked in `docs/deferred.md`.

**Countries and answers**
1. Diversity answers are one stored set for every country (item 53). A UK-only user sees the US-shaped fields
   while UK has its own checked module. Store one set per country, or count none for UK until a UK set exists?
2. The extension's rule-based fill sees only the job country's work-permit answers (item 52): on a German job, a
   question about the UK gets the German answer there. The server-side engines already answer per question.
3. A work-permit answer learned for a country you don't apply in (say a Canada job) is saved under Canada, but the
   Work permits tile shows only the countries you apply in.
4. The knock-out salary check compares the Autofill "Desired salary", not Job preferences' Minimum salary. Should it
   also use the minimum?
5. Mail-status events are dated when Maestro learned of the reply, not the email's date (item 56).
6. Four readers still use a job's country text instead of `country_code` (item 62).

**Pages**
7. Jobs opens on All active (closed jobs hidden; All is `?status=all`). Right?
8. ~~A `pdf_ready` job opens on step 3 (Tailored resume) with Continue to Apply; the board shows Apply current. Should
   `pdf_ready` open Apply?~~ Decided 2026-10-22: yes, a job with its PDF opens on Apply (`lib/job-steps.currentStep`).
9. Today's sidebar badge counts every Needs-you proposal while the page shows one as Next up. Keep?
10. The bulk Change status offers every status. Limit it to the closed ones?
11. Sort labels differ: "Best score first" (Agent inbox) and "Best match first" (Jobs). Unify?
12. The knock-out card's on-site link opens Start and pay even when the message is about the city (Contact); fixing
    it needs a field on `KnockoutCheck`.

**Settings and models**
13. Recommended models: Claude's Assistant is Haiku 5.5; Gemini uses 3.7 Flash for all four roles; OpenRouter has no
    set until the catalog lists OpenRouter models. All are data in `recommended_models.yaml`.
14. The ECB retry rule: one hour after a failure, or strictly once a day?
15. Should the persona autosave too?

**Analytics**
16. The chart palette fails the dataviz validator (chart-3 at its chroma floor; chart-2 and chart-3 close for
    protan viewers in light; dark steps outside the band) (item 58). Retune the tokens?
17. Market shares at 20 and over (skills, work mode, Skills by role cells) show plain percentages without a Wilson
    range. Does D7's range apply to shares of saved jobs, or only to the funnel's rates?

**Process**
**Other pages**
18. The gap-analysis page (`app/jobs/[id]/tailor/[sessionId]/page.tsx`, not one of the plan's boards) shows two
    filled buttons while its stale banner is up ("Start new gap analysis" and a disabled Tailor). Restyle it in the
    Career history / gap pass?
19. Career history's copy pass halved its muted paragraphs by the task's rule (paragraphs with words of their own,
    39 → 19), but a plain count of every muted paragraph went 54 → 33 (Templates 7 → 5). The plan defers Career
    history's real redesign to its own board.

**Process**
20. SYSTEM.md section baselines were re-recorded with reasons (the byte cap did not move). Acceptable?
21. `frontend/.slopconfig.json` and `.slop-baseline.json` still name the deleted `autofill-section.tsx` (item 60).

## Checks still to run

Run these on your machine, in this order. A step that fails is new: the cloud baseline failures below are all
caused by this container (no TeX or Typst, root user), not by the code.

1. **Backend suite** (from `backend/`):
   `.venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
2. **Frontend gates** (from `frontend/`): `npx tsc --noEmit`, `npm run lint`, `npm run build`.
3. **SYSTEM.md gate** (repo root): `python3 scripts/check_system_md.py`, then `--stamp` if you want the revision
   stamp current.
4. **Slop ratchet, each surface, named:**
   `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend`, then `frontend`, then
   `extension`; and `python3 ~/.claude/skills/ai-slop-detector/scripts/ledger_check.py . --strict`.
   Fix `frontend/.slopconfig.json`'s stale `autofill-section.tsx` entry first; expect `complexity_hotspots` to rise
   (re-baseline it, per SYSTEM.md §9).
5. **Real-data migration check** on a restored backup, never the live file: copy a backup from
   `~/Library/Application Support/Maestro Career Studio/backups/` to `/tmp/<copy>/`, rewrite absolute paths first
   (SYSTEM.md §12, "A copied stack rendered into its source"), then
   `DATABASE_URL=sqlite:////tmp/<copy>/maestro_cs.sqlite3 .venv/bin/alembic upgrade head` and check:
   - `select count(*), count(country_code) from jobs;` (coverage of the backfill),
   - `select work_mode, count(*) from jobs group by 1;` and the same for `level` (keys only),
   - `select count(*) from application_status_events where backfilled = 1;` equals applications with a status,
   - `select count(*) from jobs where salary_currency_assumed = 1;`,
   - start the backend on that copy and read `GET /api/settings/market` (legacy `market` reads as home + apply in),
     `GET /api/settings/autofill` (a legacy `work_auth` reads under the home market with `work_auth_market`), then
     change "You live in" once and confirm the old set stays with the old country.
6. **A live ECB fetch:** Settings › Basics › Money › Update; the rate date should be the last ECB working day.
   Compare `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` with
   `backend/tests/fixtures/ecb_eurofxref_daily.xml`'s shape.
7. **Browser pass at 1280 and 1024, light and dark, on a fresh stack** (never ports 8001/3000):
   - an empty data dir first: `/` → `/setup`, all four steps, Skip for now, Back, the done screen;
   - then with sample data: Today, Jobs (chips, Filters, Select mode, the ownership slot, hover NextStep), Agent
     inbox, a job page on each step, Automations, Analytics (period, source, folds, ≈ pay), Profile (every tile and
     fold, autosave, consent), Settings (four tabs, every old `?tab=` link), and the copy pass pages;
   - motion in Chromium 125+: the Jobs row → job page morph (first click, back, reduced motion), the status
     cross-fade, WorkingDots, CheckDraw; the job page PDF thumbnail
     (`/api/applications/{id}/preview/page/1`);
   - Companion: reload the extension; on a job in a country other than your home, answer a paused work-permit
     question and confirm it saves to that country.
8. **Design System artifact:** sync `docs/design-system/README.md`, `tokens.json` and the component cards to
   https://claude.ai/artifact/VxnjspbkP71d8Z183QqrB7; regenerate `bundle.css` and the JobsTable, Sidebar and
   PageHeader previews; retake `docs/assets/connected-agents.png`.

## Test record

- **Baseline in this container** (`a2ae0312`): 74 failed and 34 errors (108 test ids), every one bound to the
  container: no TeX or Typst (`test_user_templates`, `test_undated_render`, template parity, PDF rendering), the
  root user and the proxy (`sync/test_guard` sync-off cases 5 and 9, `sync/test_remote_route`, `sync/test_files`,
  `test_http_client`), and files that unisolated tests leave in `/app/settings` (`test_eeo_consent`,
  `test_setup_status::test_fresh_install_every_step_pending`, `test_auto_apply_settings`).
- **Every gate** compared failing ids with that list. New failures at every gate: none. One gate first showed 17
  new failures; all were caused by a `sync-key` an earlier draft of a new test had left in
  `/app/settings/secrets/`. The test is isolated now, the key was removed, and the re-run was clean.
- **Final gate** at `6cf07a9` (the last code commit; this file is docs only):
  - backend `tests/` + `mcp_server/tests/`: 17,018 passed (16,320 at the baseline), 2,352 skipped, and the same 108
    container-bound ids failing, none new;
  - frontend: `npx tsc --noEmit` clean, `npm run lint` 0 errors (the same 2 warnings as at the baseline, in
    `tailored-resume-studio.tsx` and `lib/types.ts`), `npm run build` passes, `node --test lib/*.test.ts` 616 passed;
  - `python3 scripts/check_system_md.py`: OK, 110,755 of 125,800 B, 0 warnings;
  - Alembic: one head (`c5b4833bcc54`); upgrade from empty, downgrade to the baseline revision and upgrade again all
    run on a scratch file.
- **Not run here:** the slop ratchet, a browser, a real-data copy (see [Checks still to run](#checks-still-to-run)).

## Goal critique

Judged against the Goal Card, not the plan. **Verdict: approve.** No change violates a Goal Card line. Three
things fall short of a line without a change breaking it, and each is an open question above.

| Goal Card line | Result |
|---|---|
| Each page has one thing that matters most, a few secondary things, and the advanced rest folded away | Met on every rebuilt page: Today (Next up / Also / "N more"), the job page (one LeadCard per step, three Folds), Analytics (funnel lead, tiles, Folds), Profile (Next up, tiles, two Folds), Automations (Reporting / No reports / Folds), Jobs and the Agent inbox (the list leads, Filters folded), Settings (four tabs by purpose, folded keys and explainer). No page subtitles (D1, pinned). |
| Words become numbers, meters and short tags | Met: stepper numbers, inbox and Today counts with NumberRoll, DayStrip, report lines, chips for summaries, explanations moved into Folds and tooltips. Short of it: Career history still carries most of its words (question 19); the plan gives it its own board. |
| Motion and the base-resume colour appear only where something happens | Met: motion only on a status change, an AI wait, a save and the row-to-page morph, all within 400 ms, none on keyboard actions, all with reduced-motion rules (pinned). The square shows on Agent inbox rows, the tailored-resume card, Today cards, charts by resume and the gallery, never on the Jobs list (pinned). |
| Analytics show only what the data supports | Met: a rate only from 20 with a Wilson 95% range, counts below (funnel, by resume, quiet, Skills by role); the OPT tile and Autofill coverage are gone from Analytics; a per-country work-permit breakdown is left out rather than invented. |
| Pay reads in the user's home currency | Met in code: ECB daily reference rates, ≈ on every converted figure with the posted amount under it, no rate shown as posted and left out of comparisons, missing pay never estimated. A live ECB fetch still needs your check (the cloud proxy refused it). |
| The profile covers every country the user applies in | Met for where you live, where you apply, work permits per country (forms, the Companion's learning and knock-out checks read the country the question names, else the job's), and a diversity set only where a checked one exists. Short of it: diversity answers are one stored set for every country (question 1), a limit this change did not create; per-country storage is a scope decision. |
| A new user gets a short, engaging setup | Met: `/setup` in four steps with time estimates, Skip for now, free Back, WorkingDots while a key is tested, and a done screen; a brand-new install lands there once. Needs your browser pass. |
| Every one of today's 156 Profile and Settings items keeps a home | Met and pinned item by item (`ab8eb9e`: 12 Setup, 62 Profile, 82 Settings). |
| Honest data first | Met: where a board showed something the backend does not have (a status-change date before the log existed, "4 in Agent inbox", a currency Change action, a connection state, a schedule), the UI changed, not the truth. |
| For everyone: no owner-specific defaults | Met: countries, currencies, work-permit wording and recommended models come from data files; Germany and the Netherlands added as data. The diversity caveat above is the one US-shaped remnant. |
| Keep the design system's rules | Met on every rebuilt view: round means status, square means a base resume, one filled button per view (pinned by `6cf07a9`), colour roles from tokens only (bare-token pin). Short of it outside the plan's boards: the gap-analysis page (question 18). |
| Agents own automations | Met: Automations reads only `agent_runs`; no schedule, connection dot, per-app button or logo (pinned). |
| Non-goals | Kept: no third-party AI logos (Setup's provider cards are text, pinned), no phone layout, no hosted mode, no scheduler. |

## Appendix A: every deviation line

Copied verbatim from the commit bodies (100 lines, by commit, oldest first). Each names the plan's step, what was done instead and the Goal Card line it rests on.

- `fcacd08` feat(tokens): chart series in OKLCH at even lightness
  - Deviation: frontend/components/explore/charts/chart-kit.tsx → frontend/components/charts/chart-kit.tsx, because the file lives there now (Goal Card: colour roles from tokens only).
- `56fc15e` feat(visual): monograms go neutral so the resume square is the row's only hue
  - Deviation: plan's board shows the monogram at surface-container-high → kept surface-container-highest as the plan step says, because it stays visible on a hovered dark row (Goal Card: colour roles from tokens only).
- `dada5fc` feat(ui): Fold, the folded tier
  - Deviation: `duration-short3` → `duration-(--duration-short3)`, because the M3 durations live in :root, not @theme, so Tailwind v4 compiles `duration-short3` to nothing (SYSTEM.md §12; Goal Card: the motion budget). The pin asserts the working form.
- `db3bfe5` feat(visual): NextStep, one style for a row's next move
  - Deviation: `next/link` → `GuardedLink as Link`, because test_frontend_leave_guard.py keeps guarded-link.tsx the app's only next/link, so a row's next step asks before leaving unsaved work (Goal Card: keep the design system's rules).
  - Deviation: `duration-short3` → `duration-(--duration-short3)` for the hover fill, because Tailwind v4 compiles the bare name to nothing (SYSTEM.md §12).
- `783e742` fix(analytics): match score over time reads one base per job
  - Deviation: reuse `_best_base_gap_rows` as-is → its pick extracted into `_best_base_rows`, which `_best_base_gap_rows` now wraps, with `need_gaps` off for the Base line, because the Base line reads the composite only and a row scored before gap analysis is still a real score (honest data first).
- `6294361` feat(ui): LeadCard, the lead tier
  - Deviation: action shape unspecified → `LeadAction` = { label, icon? } and either { href } or { onClick, pending? }, because the Lead cards on the boards both link (Apply, Open the job post) and press, and a link goes through GuardedLink like every in-app link (Goal Card: one filled button per view).
- `1d4c6c7` fix(analytics): no percentage on fewer than 20
  - Deviation: payload counts `interviewing: 1, applied: 3` → new `interview_plus` plus the existing `submitted`, because one word per thing: `submitted` already is that denominator, and `interviewing` would read as the status alone when the count also holds offered and accepted.
- `cf85f12` fix(analytics): score gain follows the source toggle
  - Deviation: test in tests/test_explore_router.py → tests/test_explore_gaps.py, because the tailoring-lift tests and their base/tailored row helpers live there (reuse the existing seeding helpers).
- `c9bd837` feat(motion): number roll, working dots and check draw
  - Deviation: NumberRoll `duration-[400ms]` → inline transitionDuration from ROLL_MS, because the constant is then the one source for the timing (Goal Card: the motion budget lives in lib/motion.ts).
  - Deviation: `ease-out-strong` → `ease-(--ease-out-strong)`, because --ease-out-strong lives in :root, not @theme, and Tailwind v4 compiles the bare name to nothing (SYSTEM.md §12).
  - Deviation: NumberRoll's aria-label on the wrapper → the value as sr-only text with aria-hidden columns, because ARIA does not name a generic span, so a screen reader could skip the number (Goal Card: honest data first, the number must be read).
  - Deviation: CheckDraw as a bare check path (board) → a CheckDraw component drawing CircleCheck's tick (pathLength 24 keeps dasharray 24), because the icon register says done is CircleCheck in text-success and Check means selected only (Goal Card: keep the design system's rules).
- `25b13f8` feat(visual): DayStrip for automation reports
  - Deviation: legend unspecified → a legend of only the colours present plus "No report" when a day is empty, aria-hidden because the role="img" sentence already says it, because a legend of absent states is noise (Goal Card: calm, words become numbers).
  - Deviation: added dayStripLabel to lib/day-strip.ts, because the sentence label is logic worth a node test rather than inline JSX (Goal Card: honest data first).
- `5c9ef5a` feat(jobs): one country code and one spelling per work mode and level
  - Deviation: create countries.yaml with aliases and currency, and countries.py → extended the existing service and kept its `CODE: name` file and in-code alias table; the currency is a second data file, because /api/countries and five readers depend on that format (Goal Card: countries and currencies come from data files).
  - Deviation: work mode "on_site, then hybrid, then remote" → known spellings first, then hybrid wins, else the one mode named; a value naming no mode or both keeps its own words as one key, because honest data first (no guess).
  - Deviation: a level outside the vocabulary maps to it → keeps its own words as one key ("director"), because for everyone (fields outside tech have levels the vocabulary lacks).
  - Deviation: the migration reads YAML through services/countries as planned, but work_mode_key and level_key are frozen inline copies with a test keeping them equal, because a revision never imports app code (repo convention).
  - Deviation: the extraction prompt still says "onsite" and the validator maps it, because a prompt edit needs a resync migration (test_prompt_sync_guard) and the stored value is the key either way.
- `b33a18b` feat(jobs): five columns, one next-step style, Select mode
  - Deviation: bar offers Archive and Move to closed (else Archive only) → Change status, Queue in Agent inbox and Delete, each the row's own PATCH, Queue or DELETE sent one row at a time (Delete asks once), because there is no archive concept and no bulk endpoint for jobs or applications (Honest data first; add no new bulk semantics).
  - Deviation: status, level, country and resume filters behind Filters → the filters that exist (status, stage, source) behind Filters, none added, because Never widen scope (country codes are Task 1.8, level/resume filters do not exist today).
  - Deviation: slot holds JobOwnershipPopover only → the popover while the job is not here or a request waits, else the row's hover ⋯ (Queue in Agent inbox, Delete), because every row action keeps a home (a job on the other copy could not take those writes anyway).
  - Deviation: Status shows a status date → the applied date, labelled "Applied" for screen readers and on hover, because the backend has no status-change date yet (Honest data first; Phase 2's event log is not built).
  - Deviation: board's next steps (Respond, Log outcome, Follow up) → the server-stage labels of lib/next-step.ts, because Honest data first.
- `81ad078` feat(inbox): lanes as one list, header counts
  - Deviation: header counts "to approve, queued, sent this week" → "to review, queued, applied this week", because one word per thing (the lane is To review) and the summary's applied_this_week counts your own applies too, which "sent" would misname (Honest data first).
  - Deviation: the summary line ("N new · N need you · …", ArrivalsStrip) → gone, its new and needs-you counts said by each row's New dot, the Needs you lane and the sidebar badge, because the three header counts replace it.
  - Deviation: a row's Laptop / Bot word (ownershipWhere) → removed with the helper; the pop-up icon shows only when the job is not here or a request waits (ownershipSays), because the Jobs Where column it echoed went (D4) and the board shows only the icon.
  - Deviation: header in app/proposals/page.tsx → in InboxDashboard, because the counts need the visit time and the History state the dashboard holds.
  - Deviation: components/render-harness.mjs transpiles to tsconfig's ES2017, because ES5's downlevel spread broke NumberRoll's [..."123"] in the node render test (the app build was never affected).
- `43c0566` feat(applications): a dated log of status changes
  - Deviation: backfilled has server_default false() as well as default=False → raw inserts (tests, a future migration) get a real 0, because the salary_currency_assumed column set that precedent (inv-single-dialect).
  - Deviation: plan named no source for backfilled rows → "backfill", because honest data first (we do not know who set the old status).
- `adc111b` feat(markets): where you live plus where you apply
  - Deviation: `supported` → `markets` in the GET body (the plan's name), and `market` kept as a computed field rather than a plain property, because a peer that has not updated must read the same country (honest data first).
- `c6f0f32` feat(money): a job's default currency is its country's
  - Deviation: new failing test → the rule already lived in the router since Task 1.10, so the test pins the moved function (its new job_country_code argument, home market vs HOME_CURRENCY precedence) and the capture path end to end, because one rule in one place is what the extraction mapper's "one place" note asks.
- `32347c3` feat(applications): every status change goes through set_status
  - Deviation: "mail-status updates" through set_status → MCP update_application from_email (body status_source "mail") plus one line in the mail-status prompt, because there is no backend mail path: the automation calls update_application, and honest data first needs mail told apart from the agent's own word.
  - Deviation: draft creation records a pipeline word ("tailor", "from_base") instead of threading the caller through three more MCP tools, because honest data first: those words are true whoever started it, and nothing reads a draft's source.
  - Deviation: SYSTEM.md §6 sat 91 B under its section cap, so inv-autofill-telemetry-no-values was groomed (the blanking cases and the option-text rule already live in docs/entities/others.md, "Autofill telemetry details", and extension/INTERNALS.md, "Run trace") to fit the new invariant, per the header contract (cut prose the reference holds).
- `119780b` feat(money): home currency, pay period and ECB reference rates
  - Deviation: refresh(session, fetch=httpx.get) → fetch(url) -> text whose default builds its client with http_client.new_client (5 s timeout), because every client must survive a malformed NO_PROXY (the InvalidURL repair).
  - Deviation: "at most once a day" → at most one successful fetch a day, and a failed try waits an hour, because otherwise a first run offline shows no converted pay for a whole day (Pay reads in the user's home currency), and every offline page would wait out the timeout.
  - Deviation: fx endpoints in routers/settings.py → routers/fx.py (prefix /api/fx), and the money setting's storage in services/money_settings.py, because routers are one module per resource and money.py stays pure.
  - Deviation: a JSON text setting fx_rates → a Setting row with no file mirror, because it is a machine-local cache and every file-mirrored setting is profile (test_every_file_mirrored_setting_is_listed).
  - Deviation: SYSTEM.md "outbound-calls list" → PRIVACY.md "What leaves your machine" plus one sentence in SYSTEM.md §3, because SYSTEM.md has no such list; PRIVACY.md is where outbound calls are listed.
- `a558145` feat(money): one formatter for pay, with ≈ for converted figures
  - Deviation: Intl formatRange with a guard → each end formatted and joined with "–", because ICU's formatRange collapses the shared symbol and unit ("€75–90K", which reads as €75 to €90K) and writes equal ends "~€80K", which contradicts the plan's own test and the board (honest data first).
  - Deviation: maximumFractionDigits 0 alone → also maximumSignificantDigits 2 with roundingPriority morePrecision, because 0 fraction digits turn ARS 2.4M into "ARS 2M" (the board shows 2.4M).
  - Deviation: `converted: false` for no rate → also a `noRate` flag, because "says so" needs a field the UI can word, apart from "same currency".
- `5c18cf7` feat(automations): status from reports, one Copy prompt per card
  - Deviation: "4 in Agent inbox" → "See in Agent inbox" with the count in the report line ("4 proposed"), because Honest data first: a run reports how many it proposed, not how many are still open in the inbox.
  - Deviation: the board's per-card icons and short summaries → the catalog's own summary and its need badges, because the catalog (backend skill files) carries no icon or short summary and this task does not change the backend.
- `8248fe2` refactor(copy): fewer words on Career history, Base resumes, Templates, Referrals, Assistant
  - Deviation: ratchet on every muted <p> (the audit's count) → muted <p> with words of their own, because "Words become numbers, meters and short tags": 15 of Career history's 54 already print only a value (a date, a size, an error detail), and halving those would mean re-tagging data, not fewer words.
  - Deviation: a pin on PageHeader `description` → on `subtitle`, because the PageHeader prop is named subtitle.
  - Deviation: a new shared HintTip component, because "move into a tooltip" needs a keyboard-reachable trigger and the one existing pattern lived inline in the gap page.
- `3df0895` feat(analytics): search summary from dated events
  - Deviation: SYSTEM.md §7 endpoint list -> docs/frontend-conventions.md's Analytics endpoint list, because §7 indexes agent surfaces and holds no REST list; the /api/explore routes are listed there (Goal Card: honest data first, one place per fact).
  - Deviation: "the existing tailoring-lift median" -> a median computed over the existing lift query's rows, because tailoring_lift reports a mean only (Goal Card: analytics show only what the data supports).
  - Deviation: score gain counts tailoring inside the window (newest tailored score's date) -> it follows the period control like every other figure on the page, because the board shows it under that control (honest data first).
  - Deviation: interview = reached interviewing or later (event or current status) -> keeps the funnel nested so "N of M" never exceeds its denominator (honest data first).
  - Deviation: by resume "applied ... through rate()" -> applied stays a count (it is the denominator of the two shares), because a share of applied over applied says nothing (honest data first).
  - Deviation: time to hear back also skips a reply that did not move an Applied application on (a Draft-to-reply jump stamps applied_at at the reply), because that waiting time is not real (honest data first).
- `c3e1e8a` feat(today): one next-up and three counts
  - Deviation: next_up and counts "from existing queries" -> the pick of one offer and one ready PDF is a small query over existing readers (stage.for_applications, ats_score.tracker_scores), because no existing reader picks a single item (honest data first).
  - Deviation: links -> each count carries an href built on the Jobs list's URL contract (lib/tracker-filters.ts) and /proposals, /base-resumes, because the payload must say where a count leads without the page re-deriving it.
- `25591dd` feat(models): a recommended set per provider
  - Deviation: "per provider ... Claude, OpenAI, Gemini, OpenRouter" -> OpenRouter is null in the YAML, because the catalog holds no OpenRouter id and the data rule forbids naming one it lacks (honest data first).
  - Deviation: PUT also takes an optional provider -> needed to say whose set applies when several keys are saved; without it the first provider with a key answers (Settings' "AI model: <provider>" card).
- `6bf1e1a` feat(autofill): work-permit answers per country
  - Deviation: country_in_question matches apply_in countries only and the caller falls back to the job's country → every named country is read, and a question naming a country with no market or no answers, or two countries, is unknown instead of the job's set, because a work-permit answer is never guessed (Goal Card: honest data first).
  - Deviation: the question-country override in the slot lookup (autofill_map/slots/pick) → in the router, by grouping fields per question country before the engines run, because the engines read `facts` in many places and the plan's rg finds no `work_auth.` lookup there; one rule, one place (honest data first).
  - Deviation: work-permit completeness counts the visa status only where `work_auth_vocab` is `us_visa`, because the status list is the US visa taxonomy (Goal Card: for everyone, no US-only assumptions).
  - Deviation: the knock-out scan screens a job with no country with the home set (as before) and a country no market covers with none, because the scan is advisory, not an answer given (honest data first).
- `5aea2a1` feat(job-page): one lead card per step, the rest folded
  - Deviation: plan "Autofill answers" fold → "What was submitted", because one word per thing (the receipt's name in SYSTEM.md, docs/entities/filled-answers.md and the Companion).
  - Deviation: plan "Form questions" row and "Mark as applied" → "Application questions" and "Mark applied", because one word per thing (the Companion, Settings and step 2's menu use them).
  - Deviation: board "Change" beside the assumed currency → left out, because honest data first: no endpoint changes a job's salary currency (JobPatch takes source_url and apply_url only).
  - Deviation: the header meta drops the level (it stays in the Job description fold), because the plan's header is "Company · Place · Mode · pay".
- `7eaae64` fix(knockout): salary checks convert to one currency
  - Deviation: the card at frontend/components/knockout/job-knockout-card.tsx → frontend/components/job-knockout-card.tsx, because the file lives there (no scope change).
  - Deviation: the chip uses the not-run icon, not the unknown one, because the check could not run, and the unknown icon is the missing-answer chip's (Goal Card: honest data first).
- `8283338` feat(today): Today is the home page
  - Deviation: Setup's entry card links to /setup → its one button opens the first required step not done (Settings' API keys, the resume import dialog), because /setup does not exist until Task 7.1 and a link to it would be a dead end (honest data first).
  - Deviation: "Resumes" in the sidebar → "Base resumes", because the glossary has one word per thing and test_frontend_sidebar_nav.py pins the name.
  - Deviation: "Agent jobs to approve" → "Agent jobs to review", because the Agent inbox counts and names that lane "to review" (one word per thing).
- `6bcab65` feat(motion): status cross-fade, working dots, check draw, row-to-page morph
  - Deviation: plan "NumberRoll in place of useCountUp for whole-number stat tiles" → nothing to swap, because no whole-number tile counts up: useCountUp's one user is the Match score's decimal (kept), NumberRoll already rolls the inbox counts, and StatTile (components/analytics, Phase 5's rebuild and another agent's files) takes words. The new pin holds that split.
  - Deviation: Task 4.3's `status_since` frontend type lands here → frontend/lib/types.ts held another agent's uncommitted hunks when 4.3 was committed, so ApplicationSummary gains `status_since` now (the pin in test_frontend_jobs_refresh asserts it again).
- `d93c0e0` feat(settings): four tabs by purpose, nothing removed
  - Deviation: the blocklist refusal named "Settings › Connected agents" -> "Settings › Agent apps" in services/proposals.py and routers/proposals.py, because test_frontend_copy_merge ties the sentence to the tab's label (one word per thing).
  - Deviation: "Use recommended models ... role pickers show the set read-only or turning a pick turns recommended off" -> read-only, because a pick while on is stored as your own and the role still answers the set, so the picker would jump back (honest data first).
  - Deviation: "Hours per year" in money-section.tsx -> its own hours-per-year-section.tsx, because the card-id pin maps a file's ids to the one tab that renders it.
  - Deviation: the extension's Apply link (extension/panel/stages/job.js) moved from #form-filling to #companion-apply, because the switches left the form-filling card and the link said "Change in Settings" for them.
  - Deviation: four shared files (CHANGELOG.md, docs/frontend-conventions.md, test_frontend_first_read_words.py, test_frontend_query_error_states.py) also hold another agent's uncommitted hunks, and that agent was waiting for this commit: they were committed as HEAD plus this task's hunks only, and their hunks were put back in the working tree right after.
- `f5b1de7` feat(analytics): one page, honest rates, pay in your currency
  - Deviation: Market in detail holds level, places and the work-permit breakdown → it also keeps roles, every skill, Skills by role and Roles over time (the charts Phase 1 made honest), because "Analytics show only what the data supports" and these now do.
  - Deviation: the work-permit breakdown per apply_in country → no payload breaks work authorization down by country you apply in, so Market in detail shows the jobs' stated work authorization and the fold's Country filter narrows it to one country, because "Honest data first: never show a number the backend does not have".
  - Deviation: three folds on the board → five: Skill gaps (the old tab's panel, opened by the gaps card's See all skill gaps) and Agent pipeline (the old Overview card, shown only once an agent found a job), because "the advanced rest folded away".
  - Deviation: the job filters (role, level, employment type, country, currency) → kept, as one row inside each of the three detail folds (ids prefixed per fold), not above the page, because "Each page has one thing that matters most".
  - Deviation: the canvas's "Close gaps" link → "See all skill gaps", which opens the Skill gaps fold: there is no page that closes gaps across jobs, because "Honest data first".
- `bd91ebf` refactor(settings): autofill coverage lives under Diagnostics
  - Deviation: "unchanged apart from its heading" -> unchanged, with a Diagnostics group heading above it, because the card's own title (Autofill coverage) is the board's label and ChartCard is the Analytics agent's file.
- `f553cd7` feat(setup): a four-step first run
  - Deviation: diversity "answer or decline" through the consent flow -> Setup saves no diversity answer and grants no consent; "Answer them" points the done screen at Profile's diversity section, where the consent switch sits beside the answers, and "Decline to answer" leaves those questions to you on each form, because the consent confirm and the diversity option lists live unexported in a settings file (copy nothing) and D10 keeps consent beside the answers it covers.
  - Deviation: contact fields "come from the resume" -> a line linking to Profile's Fill from career history, because that action has no endpoint (its mapping is client code inside components/settings/autofill-section.tsx) and copying it would duplicate a settings piece.
  - Deviation: work-permit questions worded per work_auth_vocab -> the three knockout answers every market asks, worded once with the country as the heading; the US visa status (us_visa) stays in Profile and the card says how many answers are left there (from setup status' per-country counts), because the market response does not carry work_auth_vocab and the US status list is unexported in the Settings editor. The capability chips are Settings › Basics' three everyday jobs (lib/model-catalog.ts EVERYDAY_JOBS: Reads jobs, Writes, Runs the Assistant), each passed when every test result it needs passed.
- `3540ada` fix(copy): messages point to the new Settings tabs
  - Deviation: the named guides → also SECURITY, SETUP_REFERENCE and the other user guides that name a Settings tab, because Goal Card "clear for any job seeker" (a guide that sends you to a tab that is gone is the same message).
- `9ff8f75` feat(profile): facts about you as tiles, saves as you go
  - Deviation: every field saves as you go -> every Profile answer autosaves except the persona, which keeps Save and Discard, because a drafted persona must be read before it is saved (Goal Card: honest data first; inv-drafted-answers; the owner's two save models).
  - Deviation: Diversity per apply_in country with a checked set -> one stored set of answers, shown only when an apply-in country has a checked set and naming those countries, because the profile stores one diversity set and the backend has no per-country shape (honest data first; no backend scope added).
  - Deviation: coverage test across components/profile/*.tsx + app/profile/page.tsx -> plus lib/autofill-options.ts, because the field labels live in the importable module Setup shares (one source, no copy).
  - Deviation: SetupStatusStrip on Profile -> removed (its file with it), because the header ring and Next up say what Profile still needs and Setup and Today's setup card carry the steps (Goal Card: one thing that matters most per page).
  - Deviation: Decline the rest -> also declines the veteran question, because it matched the label "Decline to answer" and the veteran option reads "I don't wish to answer", so readiness stayed short after declining (honest data first).
- `3634574` feat(setup): diversity and contact answers in place
  - Deviation: setup-flow.ts helpers on lib/autofill-options.ts -> a separate lib/setup-answers.ts, because a value import between node-loaded lib modules needs a ".ts" specifier that tsc refuses (TS5097); one table, no copy (Goal Card: honest data first).
- `0352b29` fix(companion): a paused work-permit answer saves to the job's country
  - Deviation: the job's market from /context → the market /context names for the question, because a question that names another country gets that country's answers (inv-work-permit-per-country) and learning it into the job's entry would put one country's answer on another's (honest data first).
- `86b8b52` docs(design-system): refresh rules and primitives
  - Deviation: "sync the claude.ai Design System artifact" -> not synced and said so in Not synced, because the brief leaves artifact syncing to the owner (Goal Card: honest data first).
- `44cc382` docs: SYSTEM.md for the design refresh
  - Deviation: plan "§7: new endpoints" -> the REST endpoints stay in the reference tier where they already are (frontend-conventions' Analytics endpoints, entities/money.md, others.md Today), and §7 gains only the MCP surface's changes, because §7 indexes agent surfaces and holds no REST list (Goal Card: honest data first, one place per fact).
- `99333d4` fix(copy): messages point to Profile's tiles
  - Deviation: remove deferred item 59 → trimmed it to the one part not shipped (connected-agents.png still shows the old Settings tab; the previews were already listed under the design-system README's "Not synced"), because the ledger rule deletes an item only when it is shipped.

