# UX IA and copy, wave 1 lane 4: settings-cards — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 10, 11, 12 of `docs/plans/2026-09-23-ux-ia-copy.md`, in that order.
**Branch:** `claude/ux-ia-lane4-settings-cards` (from `claude/ux-ia-copy-plan` at the commit that added this doc).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane4-settings-cards`. Work only there.
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
4. The appendix sections your tasks cite: C §6–§8. They hold the exact code; line numbers are at `8cac7cf9`, so re-locate by the quoted code.
5. **Words:** where your appendix proposes UI copy, use the D §0 glossary word instead if they differ (planner decision 19; `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md` §0).

## Scope

**Files this lane owns:** C's lane B ownership (Appendix C, *File ownership*): `components/settings/setting-card.tsx`, `autosave-status.tsx`, `models-section.tsx`, `model-catalog-panel.tsx`, `llm-endpoint.tsx`, new `lib/model-catalog.ts` (+ test), every settings/profile card C §8 lists (spacing, labels, leave guards on Auto-apply and API keys, Advanced prompts toggle), their pins, conventions bullets C names for these sections. Do NOT edit `app/settings/page.tsx`, `app/profile/page.tsx` (lane 3).

**Other wave-1 lanes run at the same time** (lane 1 proposed-by: backend/MCP; lane 2 lists: tables, toolbars, Applications, cap notice; lane 3 settings-tabs: the two pages, tabs, deep links, leave guard; lane 4 settings-cards: the cards). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane4`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8814` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane4/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3214,http://localhost:3214`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8814 npx next dev -p 3214` (open `http://localhost:3214`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
| 10–12 | Pins in `test_frontend_settings_pages.py` sections "Models" and "Rhythm" | Own file `backend/tests/test_frontend_settings_cards.py` | Lane 3 writes `test_frontend_settings_pages.py` at the same time; two files never conflict (C, *File ownership*, allows it) |
| 10 | Status right of the title at 1280 and 768 | Right of the title at 1280; below the description at 768 and 375 | C's own `@max-md/card-header` threshold: the header measures 432px at 768 (< 28rem). Beside the title it would squeeze the description to ~284px |
| 10 | C6 header code as written | `CardTitle`/`CardDescription` carry `col-start-1`; stacked action children `justify-start` | Without it a narrow header auto-placed the description into the action column, and the width-reserving status sat indented |
| 10 | Focus pin marker "Draft from my career" | Marker `onClick={() => draft.mutate(editRevision.current)}` | The phrase first appears in a prop docstring, so `_button_with` found no button |
| 11 | C7 copy | D words where C proposed copy (planner decisions 19, 20): titles Available models and Custom AI server; D's role hints and "Assistant model"; D's footnote; "Find OpenAI/Gemini models"; D's discovery line; "Server settings saved"; D's chip labels (Writing, Structured answers, Assistant) and gates; the probe toasts that name the chips; D's model note (the old one said "JD" and used em dashes). Models description is "Which model does each job." | One word per thing; C's second description sentence repeated D's footnote |
| 11 | `RemoveButton` in Task 12 | Created in Task 11 (`setting-layout.tsx`), extended in Task 12 | The model list needs it first |
| 11 | `"<SettingCard" in source` pins | Regex `<SettingCard[\s>]` / `<SettingCard\s+id=…` | `<SettingCardAction>` also starts with "<SettingCard", so the substring pins passed with no shell |
| 12 | Education Remove named "Remove education entry N" | "Remove school N" | D's delta on C ("entry" is banned by the glossary) |
| 12 | A removed education row hands focus to Add education | Removing the last row hands focus to Add; removing another row leaves focus on the same-position Remove, now the next school's | Rows are keyed by index, so that button never unmounts and focus never drops |
| 12 | C8 table | Also: every explicit Save/Reset/Discard is `focusableWhenDisabled`; Persona's Save row and Auto-apply's Discard hand focus on (textarea, Save); a removed blocklist company hands focus to the add field; Autofill's field grid is `items-end`; `SwitchRow` labels are `leading-snug`; the label pin also bans a `text-sm` override | "Focus never to `<body>`" (C, Global constraints); 14px labels wrap in Autofill's three columns and at 375 |
| 12 | Placeholders untouched by C | Removed the unpinned `e.g.` placeholders in the cards rewritten here (Standing instruction, blocklist company, years, locations, salary, custom question). The pinned ones stay (Deferred) | Owner decision 13; the handoff's "no example text in the cards you rewrite" |
| 12 | One commit per task | Extra commit `87af0ee1` splitting four new pins | Each assert counts as a branch; the pins pushed backend hotspots to 427 (ceiling 424). Now 423 |
| 11–12 | Browser checks on the lane's own page | A temporary, uncommitted mount of `ModelCatalogSection` and `CustomEndpointSection` in `app/settings/page.tsx`, restored before every commit | That page is lane 3's; see Deferred |
| review | Pins for the review's surviving mutants in the autosave file (Task 10's) | Header pins (M01–M04) in `test_frontend_settings_cards.py`, section "The card header" | This lane's own file; the autosave file's Task 10 pins are untouched |
| review | Pin M08 where the remote check lived (`llm-endpoint.tsx`) | Moved `isRemoteEndpoint` into `lib/model-catalog.ts` (import-free, node-tested) with a `LOCAL_HOSTS` Set; pytest pins the Set | Node tests aren't in CI, so the pytest pin reads the Set. Also fixed a dead check: `URL` reports the IPv6 loopback as `[::1]`, so the old `host === "::1"` never matched |
| review | SwitchRow label `self-stretch items-center` | Row `flex min-h-11 items-center justify-between` (padding and gap moved off the row); label `flex-1 self-stretch py-1.5 pr-4 leading-snug` | The row's `py-1.5` and `gap-4` were dead strips; now the label covers height, width and the gap. `Label` is already `flex items-center` |
| review | Blocklist chip keeps the 44px target inside (e.g. `min-h-7`) | `h-7` → `min-h-7`: 28px on a fine pointer, 44px pill on a coarse one | The chip grows with the `pointer-coarse:min-h-11` ×, so wrapped rows sit 6px apart with no overlap |
| review | Capability reason reachable "if small" | sr-only reason text; icons and the visible chip label `aria-hidden`; `title` kept for the mouse | Screen readers read it; a sighted keyboard user still reaches it only by hover (the Test toast names failing chips). A focusable tooltip per chip was not small |
| review | Catalog focus race "fix if small" | Fixed: `leaving` holds `{ id, next }`; the effect waits while the removed id is still listed | Reproduced in the browser (Add held and released mid-Remove: focus to BODY before, the neighbour's Remove after) |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 10 | new pins seen failing | 8 failed before the change |
| 10 | mutation | 8/8 mutants killed (slot ref, effect-filled slot, heading role, status back in body ×2, no reserved width, Draft drops focus, reason back in `title`) |
| 10 | `test_frontend_*.py`, tsc, lint, node, build | 655 passed; clean; 0 errors / 5 warnings; 166/166; build OK |
| 11 | new pins seen failing | cards file missing (collection error); 4 focus/shell rows failed; node test failed (no module) |
| 11 | mutation | 15/15 pin mutants killed; node-test mutant (`trim()` dropped) killed |
| 11 | `test_frontend_*.py`, tsc, lint, node, build | 669 passed; clean; 0/5; 169/169; build OK |
| 12 | new pins seen failing | 11 failed before the change |
| 12 | mutation | 23/23 killed (after one pin was strengthened when the Persona Save mutant survived) |
| 12 | `test_frontend_*.py` + autofill parity, tsc, lint, node, build | 684 passed; clean; 0/5; 169/169; build OK |
| all | every mutant re-run on the final pins | 38/38 + Task 10's 8/8 killed (one pin re-scoped to `ModelCapability` after the re-run) |
| all | `pytest tests/ mcp_server/tests/ -q` | 5001 passed, 2 skipped (at `fa35b134`; `87af0ee1` changes only card pins: 683 frontend pins pass) |
| all | `ruff check .` | All checks passed |
| all | frontend duplication, clean `git archive HEAD` | 437 lines / 36 clones (ceiling 437 / 36) |
| all | `slop_scan.py check frontend`, `check backend` (export root) | both OK; backend `complexity_hotspots` 423 (ceiling 424) |
| all | `scripts/check_system_md.py` | OK, 1000/1000 |
| all | final tsc, build (run last) | clean; OK |
| review | new pins seen failing | 10 failed before the fixes (+1 slice error in the FreeTextModel pin, fixed); node test failed (no export) |
| review | mutation (scratch `mutate_lane4.py`, from the reviewer's) | 35/35 killed, each by exactly one pin: the reviewer's M01–M24 (M08 re-targeted at the Set; M18 at `htmlFor`) + N01–N11 (draft cleared on click, onSuccess dropped, endpoint Save not focusable, race check dropped, raw provider key, `"::1"`, sr-only reason dropped, SwitchRow label not filling, chip `h-7`, Fill from resume not focusable, object lookup); node test also kills M08, M21, N05, N06, N11 |
| review | browser (1280, temporary uncommitted mount, reverted before commit) | `ftp://nope` + Save: text stays, 400 toast, focus on Save; `http://127.0.0.1:1/v1`: saved (API confirms), field shows the saved value, focus on Save (dimmed) |
| review | browser, catalog race | Add POST held, Remove DELETE held, Add released: row still listed, focus on its Remove; DELETE released: focus to the neighbour's Remove. With the old check: BODY |
| review | browser, SwitchRow at 1280/768/375 | taps at the row's top edge, in the old gap before the switch and at the bottom edge each toggle |
| review | browser, blocklist 375 coarse (touch, `pointer: coarse` true) | 8 chips, every × 44×44 inside its 44px chip, 0 overlaps, no horizontal scroll; fine pointer: chips 28px |
| review | browser, Fill from resume (no contact details) | `aria-disabled`, tabbable, opacity 0.5; keyboard focus opens its reason tooltip |
| review | browser, capability marks (report injected via route) | sr text "Structured answers: response_format rejected. Disables …" in the accessibility tree |
| review | `test_frontend_*.py` + autofill parity, tsc, lint, node | 699 passed; clean; 0 errors / 5 warnings; 171/171 |
| review | `pytest tests/ mcp_server/tests/ -q`; `ruff check .` | 5016 passed, 2 skipped; All checks passed |
| review | frontend duplication (clean export of the tracked tree); `check frontend`, `check backend`; backend hotspots | 437 lines / 36 clones; both OK; 423 |
| review | `npm run build` (last) | OK |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §11 item 31: re-check "the LLM-endpoint … placeholder clips at 768 and 375". The Custom AI server's fields are one column below a 36rem body now, so 768 likely no longer clips; 375 not measured. The placeholder itself goes in wave 3.
- §11 item 32: "a failing settings autosave toasts once per keystroke" still holds (the status moved, the toast did not).
- README and `docs/GETTING_STARTED.md`: Settings › AI & models now has the cards API keys, Models, Available models, Custom AI server; the model roles are Fast, Smart and Assistant; "Sync" is "Find OpenAI models" / "Find Gemini models"; "press **Test** next to each model" still holds (each role has its own Test).

## Deferred to merge (edits left for Claude, with file:line)

- `frontend/app/settings/page.tsx` (lane 3): render `<ModelCatalogSection />` (`components/settings/model-catalog-panel.tsx`) and `<CustomEndpointSection />` (`components/settings/llm-endpoint.tsx`) after `<ModelsSection />`, as C2's code does. **On this branch alone the page shows neither card.** Card ids stay `model-catalog` and `custom-endpoint` for lane 3's anchors.
- `docs/frontend-conventions.md` leave-guard bullet (~:352): this lane changed "Persona, Autofill and Prompts register…" to add Auto-apply and API keys; lane 3 appends to the same bullet, so expect an adjacent-line conflict.
- Lane 6 (A5 row 23): `CAPABILITY_LABELS` moved to `components/settings/models-section.tsx`; its gate already reads "the Assistant".
- Wave 3, Task 16: placeholders the pins still require, kept: `models-section.tsx` `placeholderUnset="e.g. sk-..."`, `"e.g. AIza..."`, `placeholder="e.g. llama3.2:3b"` (FreeTextModel); `llm-endpoint.tsx` `placeholder="e.g. http://host.docker.internal:11434/v1"`; `persona-section.tsx` `PLACEHOLDER` ("e.g.\nVision: …"); `autofill-section.tsx` field-table placeholders ("e.g. Apt 4B" is in `_MUST_SEE`). The pending counts must not list the ones this lane removed (job preferences ×3, quick tailor, auto-apply, the custom question).
- Wave 3, Task 21 (D6.1 rows already done here, skip them): card titles and descriptions of the three model cards, ROLES, the footnote, chip labels and gates, probe toasts :99 and :102, the model note, Find buttons, discovery line, find toasts, "Server settings saved", "Remove school N". Still to do: the Custom AI server's field copy (incl. the D10.2 OpenRouter promise), API keys description, statuses and "Save API keys", the stale option "«…» · unavailable", the unreachable-probe toast, add/remove toasts by label, `err.message` toasts. Also: at 14px the `Label` "· optional" suffix sits at the far right of a wrapped label in Autofill's three columns ("Previously employed by the company…", "Subject to a non-compete…"); D1.2's "(optional)" rewrite of `label.tsx` should wrap inline.
- Review follow-ups not done (noted): a sighted keyboard user still reads a capability chip's reason only by hovering (screen readers get sr-only text); `isRemoteEndpoint` warns "will be sent to this server" for an address the server then rejects (`ftp://nope`), seen in the review's browser check. Pre-existing; a scheme check is a one-liner if wanted.
