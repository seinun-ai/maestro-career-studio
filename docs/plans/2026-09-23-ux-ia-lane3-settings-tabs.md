# UX IA and copy, wave 1 lane 3: settings-tabs — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 6, 7, 8, 9 of `docs/plans/2026-09-23-ux-ia-copy.md`, in that order.
**Branch:** `claude/ux-ia-lane3-settings-tabs` (from `claude/ux-ia-copy-plan` at the commit that added this doc).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane3-settings-tabs`. Work only there.
**Planner/reviewer:** Claude (Opus 5.5). It reviews and merges this branch; you never merge.

## Goal Card

**Goal.** A new user understands every screen on first read. The app says one plain word for each thing
on every surface (web app, Companion panel, and the server messages it shows). The Agent inbox is plainly
separate from the app's own features and names who proposed each job. Long lists keep their headers in
view and say when they are cut off. Settings and Profile are organised into tabs with one spacing rhythm.

**Principles**
- **Plain words over precise jargon.** No abbreviations (JD, KB), no internals (render, slug, endpoint,
  schema paths), no example text in blank fields, no "/" meaning "or". A term that must stay (ATS, MCP)
  is explained once, where it first appears.
- **One word per thing, everywhere.** The glossary (Appendix D0) is binding and pinned by a ratchet.
- **Honesty and safety nuance survive every cut.** Consent, "nothing is submitted without your yes",
  honesty warnings and "can't undo" are shortened, never dropped.
- **Everything from the last plan still holds.** Never lose typed text, never say "saved" while pending,
  focus never to `<body>`, WCAG 2.2 AA, one request per click.
- **No new dependencies. MCP and chat contracts are additive only** (docstrings ≤ ~2,000 chars).
- **Conventions change deliberately**, in the same commit as the code.

**Non-goals**
- Referrals / Contacts work (deferred by the owner), grouping or paginating the tracker, search and sort
  in the URL, an `X-Total-Count` header (Appendix B O3).
- Gender options and "restrictive covenant" wording (legal nuance; owner's call later).
- `keepMounted` on the job workspace tabs, a dot on a tab holding unsaved work.

**Autonomy: peer (adapt-and-advise).** Adapt *how* when a step conflicts with repo reality and log every
deviation with one line of reason. Scope, another task's interface or the Goal Card go back to the
planner. Never expand scope.

## Ground truth (read in this order before writing code)

1. `SYSTEM.md` at the repo root.
2. `docs/frontend-conventions.md` and `frontend/AGENTS.md` (read `frontend/node_modules/next/dist/docs/` before relying on any Next API).
3. The main plan `docs/plans/2026-09-23-ux-ia-copy.md`: Goal Card, *Owner decisions* and *Planner decisions* (binding — especially 15–20), *Before you start*, *Waves and lanes*, and your tasks' sections.
4. The appendix sections your tasks cite: C §1–§5. They hold the exact code; line numbers are at `8cac7cf9`, so re-locate by the quoted code.
5. **Words:** where your appendix proposes UI copy, use the D §0 glossary word instead if they differ (planner decision 19; `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md` §0).

## Scope

**Files this lane owns:** C's lane A ownership (Appendix C, *File ownership*): new `lib/settings-tabs.ts` (+ test), new `components/settings/settings-tabs.tsx`, `app/settings/page.tsx`, `app/profile/page.tsx`, `lib/use-focus-section.ts`, the `anchorHref()` helper and every link in C §3's inventory, `lib/leave-guard.ts`, `components/guarded-link.tsx`, `lib/focus.ts` (`focusIfStranded`), `components/ui/tabs.tsx`, pins in `test_frontend_settings_pages.py` (new), `test_frontend_leave_guard.py`, node tests, conventions bullets C names for these sections. Leave a mount point in `app/settings/page.tsx` for wave 2's Connected agents card.

**Other wave-1 lanes run at the same time** (lane 1 proposed-by: backend/MCP; lane 2 lists: tables, toolbars, Applications, cap notice; lane 3 settings-tabs: the two pages, tabs, deep links, leave guard; lane 4 settings-cards: the cards). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane3`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8813` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane3/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3213,http://localhost:3213`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8813 npx next dev -p 3213` (open `http://localhost:3213`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

## Gates (per task, and all of them before you report done)

- The task's pins (seen FAILING first), plus every `backend/tests/test_frontend_*.py`. Mutation-check every pin you add: break the guarded code, see exactly that pin fail, restore from a backup copy (never `git stash`).
- tsc clean; lint 0 errors; node tests pass; `npm run build` (run last).
- Full backend suite `pytest tests/ mcp_server/tests/ -q` at least once before reporting (baseline at `61a4a15f`: see the plan's *Gate results*); `ruff check .`.
- Slop ratchet: frontend duplication measured on a CLEAN `git archive HEAD` export (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py scan <export>/frontend --json` → `duplication`) must stay ≤ **437 lines / 36 clones**; `slop_scan.py check frontend` and `check backend` OK from the export root; backend `complexity_hotspots` ≤ **424** (423 at the branch point; split a test that reaches cc 10).
- Logic added in two places goes through a shared helper.

## Commits

One per task with the plan's commit message, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't amend or squash earlier commits. Commit this doc's filled-in logs at the end.

## Escalation (autonomy: peer)

Adapt *how* when the plan conflicts with the code and log it below. If a change needs another lane's file, scope, or a Goal Card trade-off: log a deviation note (planned / found / proposed / Goal Card line) and carry on with the rest. Never expand scope.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 6 | C1 reserves anchor `"mcp"` for the Connected agents explainer | Reserved `"connected-agents"` | A8 names the card `id="connected-agents"`; with `"mcp"` the wave-2 card's id fails the card-id pin ("Every old link still lands on its card") |
| 6 | C2 renders `ModelCatalogSection` and `CustomEndpointSection` in the AI & models panel | Renders `ApiKeysSection`, `ModelsSection`, `PromptsSection` only | Those exports are lane 4's (C7) and do not exist on this branch; their ids are already in the tab table. Deferred to merge (below) |
| 6 | C2 pin `"router." not in src` | Pin: no `useRouter`, no `router.replace(`/`router.push(` call | The literal matched C's own comment (`app-router.js`, "`router.replace` would fetch") |
| 6 | (not in C) | Added `test_connected_agents_keeps_its_order_and_a_place_for_the_explainer` and `test_profile_lands_a_hash_once` | Planner decision 18 Q2 (explainer, hints, Auto-apply) and Q9 (one `useFocusSection()` on /profile: the strip takes `focus` as a prop) needed pins |
| 7 | C3 pin greps every source for a hash-only `/settings#`/`/profile#` string | The pin strips comments first | Comments quote hash-only examples (`setting-card.tsx:70`, lane 4's file; the tab hook's docstring) |
| 8 | C2: the tab hook parses the page's `searchParams` prop (`param`) | The hook reads `useSearchParams().getAll("tab")`; `SettingsTabs` takes no `param`; the pages keep `use(searchParams)` (a comment says why) | Found in the Task 8 browser check: the prop keeps its ARRIVAL value after a native `replaceState` (C2's own risk note), so a link to another tab of the same page (sidebar Profile from `/profile?tab=autofill`) opened nothing. `use(searchParams)` is load-bearing: without it `next build` fails ("useSearchParams() should be wrapped in a suspense boundary", tried and restored). The pin was renamed to match |
| 8 | C4: four one-token edits in `leave-guard.ts` | Exactly those four; `answered()`'s two `h.url === t.page` stay URL compares | They decide whether the URL must be put back (Stay) or which render to run, not whether the page changed; outside the verified 43/43 set |
| 9 | C5: the `TabsList` base string only | Also `relative` and `scroll-px-[3px]` on the row, `min-w-0` on the `Tabs` root | Browser check 2 failed with C5 alone: the dialog body is a grid, so the `Tabs` item took the row's full label width as its minimum and the whole dialog overflowed. Then Home left the first tab 16px under the edge: Base UI's scroll-into-view walks `offsetParent`s and the unpositioned row was not on that chain (the dialog's padding was counted). `scroll-px-[3px]` keeps an end tab's 3px focus ring inside. `min-w-0` measured: no size change on 7 other tabbed pages at 375 and 1280 |
| 9 | C5 pin slices the variants block | The pin reads only the class string | The comment beside it names the classes (and "justify-center") |
| all | One commit per task | Plus `4c9dbacb` splitting two pins | Two new pins reached cc 10, and backend `complexity_hotspots` went 423 → 425 (limit 424); split, now 423 |
| review | Appendix C §4: `samePage` (pathname) in `arrive`/`judge` with the old unconditional `out.push(STOP)`; C §4's optional step: a same-page `GuardedLink` passes straight through | `showSamePage` in `leave-guard.ts`: same page decides only what ASKS, the URL decides what RENDERS (stop for the same URL, or while a question or a step over the duplicate settles; otherwise `t.page = e.url` and Next renders). A dirty same-page `GuardedLink` `preventDefault`s and `router.replace`s. The listeners' snapshot compares the exact URL again | **Plan defect** (review C1, I1): with the pathname compare every Back/Forward between two queries of one page (Analytics `?tab=`, Settings/Profile `?tab=`, `/chat?session=`) changed the address bar and not the screen, even with nothing unsaved; and a dirty same-page link pushed a normal entry above the duplicate, so Back #1 was a dead press. Adopted the reviewer's prototype re-derived, with two changes: a Back that steps over a leftover duplicate holds the page too (the prototype rendered the older tab for a frame before leaving), and `home` moves only to an entry whose URL is the page on screen ("Every Back shows the entry's page"; "never lose typed text") |
| review | C5: wrapping rows "never overflow sideways, so none of this engages there" | `overflow-x-auto` scoped to `not-[.flex-wrap]`; triggers `group-[.flex-wrap]/tabs-list:h-auto`; comment rewritten; `scroll-px-1` (was `[3px]`) | Review I2: `overflow-x: auto` computes `overflow-y: auto`, so a wrapped row clipped its second line (Analytics "Gaps & growth" at 375, Career history at 375/768); the triggers' `h-[calc(100%-1px)]` had already spilled over the next card before this lane. At 3px the scroll-into-view stopped 1px short of the end (the verifier's clipped ring) |
| review | (not in C) | `settingsPageAt()` in `lib/settings-tabs.ts`, shared by `anchorHref` and `use-focus-section.ts`'s `announce()`, which now writes `tabHref(page, tab, anchor)`; the in-page jump's poll is cancelled on unmount and by the next jump | Review minors M1/M2: the in-page jump left `?tab=` naming the old tab (a reload opened the wrong one); logic in two places goes through one helper |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 6 `dd14e643` | pins (seen failing: collection error, then 2 of 7) | `test_frontend_settings_pages.py` 7 passed; all `test_frontend_*.py` 654 passed |
| 6 | node `settings-tabs.test.ts` (seen failing: module missing) | 4/4; all node 170/170 |
| 6 | tsc / lint / build | clean / 0 errors, 5 baseline warnings / OK (`/settings`, `/profile` are ƒ) |
| 6 | mutations | 10/10 caught by exactly the named pin (prefix rule ×2 incl. node, label, card id in the wrong tab, card moved to another panel, keepMounted, router write, page ignores `?tab=` (superseded by the Task 8 pin), Auto-apply before hints, strip keeps its own hook); re-run after the split: all still caught |
| 6 | browser (`t6_browser.py`) | 26/26 |
| 7 `4843cd25` | pins (seen failing 2/2) | 9 passed; all frontend pins 656 |
| 7 | tsc / lint / node / build | clean / 0 errors / 170/170 / OK |
| 7 | mutations | 6/6 (setup step, knock-out, `/new` hash-only; mounted counts as shown; no hashchange; landing never cancels) |
| 7 | browser (`t7_browser.py`) | 24/24 |
| 8 `71128818` | node history tests (seen failing 2/5 new, as C4 says) | 43/43; `focus.test.ts` (seen failing: no export) 20/20; all node 176/176 |
| 8 | pins (seen failing 3) | `test_frontend_leave_guard.py` 22 passed; all frontend pins 658 |
| 8 | tsc / lint / build | clean / 0 errors / OK |
| 8 | mutations | 11/11 (stamp by URL ×2 incl. node, judge, forward skip, snapshot, same-page link asks, inert focus kept ×2 incl. node, tab switch strands focus, tab read from the arrival prop, page stops reading `searchParams`) |
| 8 | browser (`t8_browser.py`) | 23/23 |
| 9 `7a19e105` | pin (seen failing) | passed; all frontend pins 659 |
| 9 | tsc / lint / node / build | clean / 0 errors / 176/176 / OK |
| 9 | mutations | 7/7 (no `max-w-full`, plain centring, no overflow, row not `relative`, no scroll padding, root not `min-w-0`, visible scrollbar) |
| 9 | browser (`t9_browser.py`) | 69/69 (light and dark × 375/768/1280) |
| end `4c9dbacb` | full backend `pytest tests/ mcp_server/tests/ -q` | 4982 passed, 2 skipped (baseline at `6366ec27`: 4969 passed, 2 skipped; +13 pins) |
| end | `ruff check .` | All checks passed |
| end | frontend duplication, clean `git archive HEAD` | 437 lines / 36 clones (ceiling 437/36) |
| end | `slop_scan.py check frontend`, `check backend` (export root) | both "slop ratchet OK" |
| end | backend `complexity_hotspots` | 423 (≤ 424) |
| end | `check_system_md.py` | OK, 1000/1000, 0 warnings (SYSTEM.md untouched) |
| review fix `041a35cb` | node history tests (seen failing 6 of 10 new on `eb3774e7`'s machine) | 53/53 (43 + 10: review A–G re-derived, a same-page push while dirty, `samePage` with a hash); all node 187/187 |
| review fix | pins (seen failing on `eb3774e7`: 3 leave-guard, 2 tab-row; the rest are pins for surviving mutants, each seen failing under its mutant) | `test_frontend_leave_guard.py` 24, `test_frontend_settings_pages.py` 19; all `test_frontend_*.py` 670 passed |
| review fix | mutations (`/tmp/maestro-ia-lane3/scripts/mutate_fix.py`, backup copies) | 25/25 caught: C1 ×6 (stop always; judge or arrive unconditional stop; no hold, which is the prototype's flash; always hold; snapshot by pathname), I1 ×2 (pass-through push; `router.push`), I2 ×3 (unscoped overflow; trigger height; 3px scroll padding), the named survivors M1 M4 M8 M9 M10 M11 M13 M16 M17 M21 M22 (each by a pytest pin now, 4 also by node), minors ×3 (no unmount cancel; no replace-cancel; announce keeps the old `?tab=`). The reviewer's own list (`mutate_review.py`, M1–M23): 22/22 caught (M5 M6 M7 M12 M14 M15 M19 M23 also survived at `eb3774e7`; pinned too); M24's target line no longer exists (I1 replaced it) |
| review fix | browser, real Back/Forward (`fix_browser.py`: `chrome.tabs.goBack/goForward` from an extension in headed Chrome for Testing) | 40/40; the same script on `eb3774e7`'s leave guard: 31/40 (C1 ×7, I1 ×2). Profile, Settings, Analytics `?tab=gaps`, `/chat?session=` Back/Forward cycles: URL and shown tab agree; dirty asks, Stay, Leave, one press after Save, Forward after Save; I1: no entry added, Back #1 asks |
| review fix | browser, wrapped rows (`fix_wrap.py`, light 375/768/1280 + dark 375) | 110/110 (on `eb3774e7`'s `tabs.tsx`: 78/110). Analytics (both tabs, filter bar below), Career, both studios, KB import drawer: every tab hittable and inside its row, the row visible/visible, nothing below overlaps, a click selects each tab; job page, Settings, Profile still one 32px scrolling row; end tabs' ring: Settings 0px lost (was 0.7), job page 0.34px (sub-pixel: `scrollWidth` is an integer) |
| review fix | browser, regressions and M2 (`t6`–`t9_browser.py`, `fix_announce.py`) | 26/26, 24/24, 23/23, 69/69; 4/4 (the strip's jump writes `?tab=autofill#autofill-…`, a reload opens it) |
| review fix | full backend `pytest tests/ mcp_server/tests/ -q` | 4992 passed, 2 skipped (+10 pins over `4c9dbacb`'s 4982) |
| review fix | tsc / lint / `ruff check .` / `npm run build` (last) | clean / 0 errors, 5 baseline warnings / All checks passed / OK (`/settings`, `/profile` ƒ) |
| review fix | slop, clean `git archive HEAD` of `041a35cb` | frontend duplication 437 lines / 36 clones (≤ 437/36); `check frontend`, `check backend` OK; backend `complexity_hotspots` 423 (≤ 424; the tab-row pin that reached cc 10 was split) |
| review fix | `check_system_md.py` | OK, 1000/1000, 0 warnings (SYSTEM.md untouched) |

**Not verified:** Chromium only (no WebKit); Tasks 6–9's Back and Forward were driven by `history.back()`/`forward()`
(the review fix re-ran them with the browser's own Back via `chrome.tabs.goBack`); a touch swipe on the tab row
(a horizontal wheel scrolled it); `/settings#model-catalog` and `#custom-endpoint` (lane 4's cards are not
on this branch); C4's "cross-tab jump from inside a panel" (no such link until wave 2; a hash change
that hides the focused panel was checked instead); the template editor's tab row (`/templates/[id]`).
Browser scripts and screenshots: `/tmp/maestro-ia-lane3/scripts/t{6,7,8,9}_browser.py`, `fix_{browser,wrap,announce}.py`,
`/tmp/maestro-ia-lane3/shots/`.

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §11 item 31: delete "the New base résumé dialog's tab row does not shrink;" and "the job page's tab row
  pushes Q&A off-screen;" (Task 9 browser checks 1 and 2 pass at 375, light and dark).
- §12 candidate (2026-09-23): **A page's `searchParams` prop keeps its arrival value after a native
  `replaceState`**: the settings tab hook parsed it, so a link to another tab of the same page opened
  nothing → read `?tab=` with `useSearchParams`, and keep `use(searchParams)` in the page (it makes the route
  dynamic; without it `next build` fails on `useSearchParams` outside Suspense).
- §12 candidate (2026-09-23): **Base UI's arrow-key scroll-into-view walks `offsetParent`s up to the
  scroller**: an unpositioned tab row is not on that chain, so a dialog's padding was counted and Home left
  the first tab 16px cut off → the row is `relative` (`components/ui/tabs.tsx`).
- §12 candidate (2026-09-23): **Same page is not same URL**: the leave guard stopped every popstate to the
  same pathname, so Back between `?tab=` or `?session=` entries changed the URL and not the screen, on every
  page → `samePage` decides what asks, the URL decides what renders (`showSamePage`).
- §5 step 3 and §7 need nothing; §8 is an index (the conventions carry the rules).

## Deferred to merge (edits left for Claude, with file:line)

- `frontend/app/settings/page.tsx:67-68`: after `<ModelsSection />` add `<ModelCatalogSection />` and
  `<CustomEndpointSection />` (imports from `@/components/settings/model-catalog-panel` and
  `@/components/settings/llm-endpoint`, lane 4's exports), per C2. Their ids `model-catalog` and
  `custom-endpoint` are already in `lib/settings-tabs.ts`, so the card-id pin passes once they render. Then
  re-run the legacy-link browser check for `/settings#model-catalog` (not checkable here).
- `frontend/app/settings/page.tsx:74` (wave 2, Task 15): replace the comment with `<ConnectedAgentsCard />`
  (id `connected-agents`, already reserved), and extend
  `test_connected_agents_keeps_its_order_and_a_place_for_the_explainer` to assert the card before
  `<McpWorkflowSection />` (drop the comment check). Then run C4's "a cross-tab jump from inside a panel"
  check if the card links in-page.
- `backend/tests/test_frontend_settings_pages.py`: lane 4 appends "Models" and "Rhythm" sections at the
  end of the same new file; keep both sides.
- `docs/frontend-conventions.md`: this lane edited the leave-guard bullet (~:298), the `TabsContent` bullet
  (~:621), "Settings vs Profile" (~:887) and "Derived setup guidance" (~:955); lane 4 edits the neighbouring
  `SettingCard`, "Two save models" and legend bullets, so hunks may touch.
- `frontend/components/settings/setting-card.tsx:70` (lane 4's file) still quotes `/profile#autofill` in a
  comment; harmless (the deep-link pin strips comments), but C9's copy lane may want `anchorHref` there.
- Wave 3 (copy), from review M3: server messages still point Profile fields at Settings, and name
  "Settings → Models" (now the "AI & models" tab). Not this lane's files; listed for the copy lane.
