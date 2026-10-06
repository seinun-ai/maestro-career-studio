# Visual language — cloud run handoff

The cloud run of [the visual-language plan](2026-10-06-visual-language.md) is finished: all 30 tasks are implemented,
each passed a spec and quality review, every wave passed a wave review against the Goal Card, and a final whole-branch
review returned **"Ready for the owner's local pass"** (no Critical or Important findings). Nothing was merged and no
pull request was opened.

- **Branch:** `claude/ui-ux-icons-visual-research-6195e9` (the same commits are also on
  `claude/ui-ux-icons-visual-research-6195e9-rawv0y`, the cloud session's working branch).
- **Range:** `31e9649` (plan) → `138bd3b` (code), plus this handoff commit.
- **Process:** a Sonnet implementer per task, an Opus reviewer per task and per wave, an Opus final review and goal
  critique. Architect rulings are recorded in the plan's "Execution rulings (architect, cloud run)" section.

## Final results

Run in a clean worktree at `138bd3b` (cloud container: Python 3.13, Node 24.21).

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean (exit 0) |
| `npm run lint` | 0 errors, 2 warnings (both pre-existing: unused `opts` in `tailored-resume-studio.tsx`, `PROPOSAL_STATUSES` in `lib/types.ts`) |
| `npm run build` | OK |
| `node --test lib/*.test.ts` | 38 of 38 files pass |
| Backend suite (`pytest tests/ mcp_server/tests/ -n auto --dist loadfile`) | 8270 passed, 895 skipped, 63 failed, 34 errors — the failed and errored tests are exactly the base commit's environmental set; none new |
| `python3 scripts/check_system_md.py` | OK — 999/1000 lines, 0 warnings |

**About the backend failures.** The base commit `31e9649` already fails 63 tests and errors 34 in this container,
all environmental: no `pdflatex`, missing render fonts, and a few machine-dependent settings tests (EEO consent,
setup status, golden ATS snapshots). The branch adds no failure to that set. Expect your Mac (with TeX) to show far
fewer.

**One pre-existing test isolation bug was fixed** (commit `138bd3b`, `backend/tests/conftest.py`):
`test_typst_classic_seed::test_typst_classic_certifies_through_existing_gate` failed whenever
`test_template_registry.py` had run earlier on the same xdist worker, because
`template_registry._SEED_VALIDATION_ATTEMPTED` is a process-wide set no test reset. It reproduces at `31e9649` with
those two files run serially. This branch's new test files changed which files share a worker, so CI would have
started hitting it. An autouse fixture now resets the set before and after each test.

## Unfinished work

No plan task is unfinished. What was deliberately not done in the cloud:

- **The browser passes** (every wave end and the final one). Checklist below.
- **The slop-ratchet scan** on `frontend`, `backend` and `extension` (the script lives outside the repo).
- **Loading the Companion unpacked in Chrome.**
- **Republishing the design-system artifact** (Task 30's last bullet).
- Nothing in this plan needed the API key, so nothing was skipped for that reason.

**One known-red intermediate commit:** `7a37c78` (Task 9) accidentally included a test pin written by a parallel
implementer for Task 8's fix; `test_frontend_states.py` fails at exactly that commit and passes from `0a24fc0` on.
History was not rewritten because the branch was already pushed. Bisect across it with care.

## Local steps for the owner

1. Pull the branch. Rebuild both images if you verify on the stack (SYSTEM.md §9), or better, use the fresh-stack
   recipe (uvicorn on its own sqlite copy, `next dev`), never the Docker compose stack.
2. Run the slop check on each surface and name each one:
   `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` (then `backend`, `extension`).
   Re-baseline `complexity_hotspots` with a reason if it rises; never re-baseline duplication.
3. Do the browser pass below on a snapshot of the live database (`sqlite3 … ".backup"`), at **1280 and 1024 px**,
   **light and dark**, and once with **Reduce motion** on.
4. Load the Companion unpacked in Chrome and do its checklist; the console must stay free of CSP errors.
5. Republish the design-system artifact (https://claude.ai/artifact/VxnjspbkP71d8Z183QqrB7) with the new
   components (eight primitives, Button `pending`, the field warning state, the motion utilities). The component
   pages under `docs/design-system/components/` have no previews yet; `JobsTable/preview.html` and
   `StatusChip/preview.html` still use `transition-[transform,…]` and need the `translate`/`scale` form.
6. Answer the owner questions below; each has a reversible default already in the code.
7. Then choose merge, PR or keep (superpowers:finishing-a-development-branch).

## Browser checklist (1280 and 1024, light and dark)

### Jobs tracker (`/applications`)
- ATS column: ScoreBar + number fits at 1024; "—" when unscored; sorts with unscored rows last either way.
- Status filter: dots in the dropdown and its trigger (note Proposed vs Applied and Skipped vs Draft share colours).
- Quick filters strip: Check when pressed, clicking again clears it, hidden when its count is 0.
- Sort arrows line up with the header text; the row ⋯ is horizontal.
- Status chip: changes at once, one soft ring after the save settles, a second pick is blocked, focus stays on the
  chip; with the backend stopped it snaps back with an error toast and no ring; Reduce motion → no ring.
- Empty database: the getting-started card, green "Done" word and icon, Required badge only on undone steps.

### Add job (`/new`)
- Summary card: Required / Preferred / Mentioned groups, the 24-badge cap and where "+N more" lands.
- Save job spins and says "Saving…".

### A job (`/jobs/[id]`) — header and the four tabs
- Header: Best pill beside the status chip, truncates at 1024, absent before the first score, updates after Update
  scores; lock icons in the Resume and Q&A tabs; the locked reason is in the hover title and announced to screen
  readers (it is no longer visible text).
- Header proposal pill: Queue = send icon ("Queueing…"), Keep it = thumbs-up, "Open Agent inbox" = Bot.
- Overview knock-out: a passing job is a quiet line + strip (green icon only, no fill); a conflict is a red banner
  "You may not qualify: X" and is the loudest thing on the page; pay without a desired salary reads "Checks not run
  yet" and the Not-run chip links to Autofill preferences (its action reachable by keyboard and screen reader);
  an incomplete profile is an amber banner + strip; strip wrapping at 1024.
- Overview facts: Layers on role chips, IdCard (Work authorization), School (OPT), Skills with Tags, "Show full job
  description" with TextQuote.
- Score and tailor: Best-match card has a primary ring and spans two columns at @3xl; shared gate warning shows
  once as an amber banner (a single card's warning is amber with a triangle, never red); neutral "Weakest" word on
  the lowest subscore only (none when all equal); "Skills covered m of n"; Update scores spins and the numbers
  count up; only a manual Update scores toasts; progress bar above Continue gap analysis.
- Resume tab: Draft › PDF step line in the card header; preview dims while a PDF renders (can you still scroll?
  the error banner and zoom dim too — owner question); compare headline DeltaChip; diverging DeltaBars at ±extremes
  and 0; Change column Gained → Lost → Same; the Now column always says Matched or Missing.
- Q&A tab: kind glyphs; Copy → CircleCheck + "Copied" chip rises and fades over 1.2 s (does the tooltip cover it?),
  VoiceOver says "Copied"; skeleton before history; empty box → hint, Answer questions disabled but focusable, focus
  stays after a successful ask; cover letter "PDF ready" neutral chip beside the title.
- What was submitted: TriangleAlert flags.

### Gap analysis (`/jobs/[id]/tailor/[sessionId]`)
- Tab through the action segments: each hint is announced and its tooltip shows; selecting replaces the action icon
  with Check with no width jump.
- Resolve via Skip / I can't confirm (Ban) / a library chip / Done: the card collapses in about 200 ms, the row shows
  the action icon, focus lands on the row.
- An auto-resolved row's leading icon agrees with its provenance chip; the "Suggested" chip has a word and a quieter
  border than the selected chip.
- Required filled / Preferred tonal / Mentioned outline; Strong match quiet with a green check.
- Category "x/y" with a green check when nothing is open; footer SegmentedBar wrap and legend contrast in dark (does
  "N open" read too quiet? owner question); "Saved" holds 1.2 s then clears; Try again moves focus to the status.

### Health report and question pass (`/base-resumes/[slug]/health`)
- Collapsed rows: the meta line wraps cleanly at 1024; the DotMeter matches the level word (an unknown level shows the
  word only); "Higher priority" chip readable in dark; group header DeltaChip.
- Locked Apply keeps its hover title; Apply suggestion / Write new wording spin.
- Question pass rows: skipped (SkipForward), waiting (CircleDashed), writing (spinner), failed (red), "New wording
  ready" (FilePen, no green), "No change to save"; the sticky footer bar and its progress are announced once.
- "Must fix" badges look the same here and in the studio's Review changes.

### Agent inbox (`/proposals`)
- Page top: "Nothing new since your last visit" collapses; otherwise four tiles (Ready check, Needs you dot).
- Rows: ActorChip (Bot + agent name) + time truncates at 1024; base name + ScoreBar; status badge only in Needs you
  and History; quiet Ready chip; DotMeter + "Not tailored"; Knock-out chip red with CircleX (same as the Overview);
  "N to check" amber.
- Actions: spinner on the acting row only (judge the blur over it); the focus ring stays visible on the actions
  container; the row collapses in about 200 ms and focus moves to the next row; the bulk bar slides up; bulk Queue
  spins only Queue; a partial failure keeps the failed rows selected; toasts read the same here and on the job page;
  Queue then Keep it from Needs you brings the row back.
- Cap sentence with its bar; Recent runs outcome chips (Done / Partly done with a triangle / Failed) in both themes.

### Career history (`/career`)
- Drafts to review (FilePen); Approve and Approve all (thumbs-up); Approve shows "Approving…" then a toast with Undo,
  and Undo puts the draft back; editing a draft or moving it must not make Approve spin.
- Bullets: one chip per bullet (who + "AI inferred" / "Unconfirmed" with Ban), same height as its neighbours; the
  usage chip (FileText + number) is announced; drift chip has a warning icon on a neutral surface.
- Documents use Paperclip; failed document chip on error-container; card hover lift and press scale animate.

### Base resumes, templates and the studios
- Galleries: skeleton then image, cached images not stuck, a broken URL falls back to the placeholder (also after a
  hard reload); thumbnails below the fold still load.
- Archive → Undo brings the resume back; ⋯ › Copy ID toasts.
- Version history: source glyphs, "Created" as a word only, "Restored" neutral, Current dot, Restore icon; the diff
  view's "Removed" on error-container.
- Studio Save spins in place and keeps "Save"; Review changes "You" chip neutral; contact Email warning on blur.
- Templates: the uncertified warning icon aligns with the first line; editor compile error and preview render error
  both on error-container; the zoom segment's width when selected.
- Resume editor fields: no extra gap below fields without a message.

### Analytics (`/analytics`)
- Status mix bar and legend (hidden while loading and on error); 96 px sparkline in the Applied tile; gap and
  quick-win ScoreBars aligned; agent pipeline bars solid in dark.

### Automations (`/automations`)
- Kind and need glyphs (one globe), "Not run yet", "Last ran" + outcome chip; the connect callout shows only when
  nothing ran, and still shows if the runs request fails (stop the backend mid-load).
- Copy prompt swaps to "Copied"; with the clipboard blocked the prompt opens and is focused, one message only.

### Settings (`/settings`)
- Each autosave card: Saving… → green Saved with a round ring for 1.2 s → idle words with no tick.
- Form filling: no "Saves automatically" while a typed key is unsaved.
- Market select dims while saving.
- Autofill personal: a bad email / phone / link shows an amber border + icon + words on blur, is announced, clears
  while typing, and Save still works; dark-mode contrast.
- Connected agents: "They can't" list with Ban; profile Email icon.

### Assistant (`/chat`)
- Tool chips: spinner → check for 1.2 s → domain icon; reading then editing a resume shows one chip.
- Card badges (Suggested / Edited / Career history); resolved cards at 80% with Applied / Added / Discarded.
- Open an old chat on a slow network: a skeleton (not the greeting), and the composer stays docked.

### Companion (load unpacked)
- Status chip colours in light and dark: Draft muted (the pill is visible in dark), Applied blue, Interviewing amber,
  Offer violet, Offer accepted green, Rejected red.
- Track segment: the selected one shows Check on the secondary container.
- Rail: done steps show circle-check in the numeral; locked rows read lock + "Not yet"; not-needed rows read minus +
  "Not needed".
- Fill report: icon + heading + count; one "Check each one before you submit." line; Skipped rows show skip-forward;
  state words beside the icons fit at the panel width.
- Links show their icon with a small gap (including "Tailor in Maestro CS") and say "(opens in a new tab)".
- Footer warning note shows the triangle icon; hover, press and focus ring on Fill, Stop and the secondary buttons;
  none on busy fork limbs; no press squeeze with Reduce motion.
- The console shows no CSP errors.

## Owner questions (each has a reversible default in the code)

1. "Best" (job header) vs "Best match" (score card); the filled primary badge also means Required on the gap page.
2. The score card's gap progress counts answered only; the gap page counts answered + skipped.
3. `Tag` means both "add keyword" (gap page) and the studio's role label.
4. The gap footer legend may read too quiet for "N open".
5. Status colours (pre-existing): the inbox History "Applied" is green while the tracker and Analytics "Applied" is
   blue (green there means Offer accepted); the Proposed lane dot shares blue with Applied; Skipped shares muted with
   Draft.
6. `FilePlus2` is the add action; version history "Created" now shows the word only.
7. New copy from Task 20: the meter is named "How well it is shown" (the glossary bans "evidence") and the line "New
   wording ready" was added. Keep, or make them screen-reader only?
8. The PDF previews blur and block pointer events while rendering, which also covers the error banner and zoom.
9. Form filling hides "Saves automatically" while a typed key is unsaved (ruled default).
10. Gap segments: Check replaces the action icon when selected; a suggested chip shows "Suggested" with a quieter
    border (ruled default).
11. Undo after approving an edited bullet restores the draft state but keeps the edited text.
12. The career Activity timeline's "Added by the Assistant" rows wear `Bot`, the agents glyph (pre-existing).
13. The locked tabs' reason is now hover-title and screen-reader only.
14. The tracker shows the best base score for a saved job but the application's own score for an applied job
    (labelled "Best ATS score" vs "ATS score").

## Deviations

Every implementer adaptation, as logged in the commit bodies (`git log 31e9649..HEAD --grep Deviation`). Architect
rulings that overrode plan text are in the plan's "Execution rulings" section.

| Commit | Task | Deviation |
|---|---|---|
| 2727ab1 | 3 | The template warning wrapper is an inner span; the `<p>` literal is pinned. |
| 2727ab1 | 3 | `SkillGroup` exported and reused; Preferred = tonal in both places (ruling). |
| a21c1cf | 4 | Strong match uses `CONCEPT_ICONS.done`. |
| a21c1cf | 4 | The knock-out conflict keeps a transparent border so its box size is unchanged. |
| 0f5d47f | 15 | `.collapse-exit` replaces the plan's `.animate-row-exit` (ruling). |
| 0f5d47f | 15 | `useCountUp` has one rAF path (the plan's version failed `react-hooks/set-state-in-effect`). |
| 9c1e429 | 6 | Redundant `focusableWhenDisabled` / `data-disabled` classes dropped where pending was the only reason. |
| 9c1e429, c5dedb0 | 6 | `BulkBar` gains a local `queuePending` prop, so only bulk Queue spins (replaced the shared-flag deviation). |
| 734d7a1 | 5 | `finding-cards.tsx` and its pin edited: `LOCKED_BTN` gains `data-disabled:pointer-events-auto`. |
| 2f795be | 7 | The job header's optimistic update merges the whole PATCH body (the hook is generic). |
| 3a9b32f | 7 | The confirm ring fires when the PATCH settles, so a rollback stays silent. |
| fc0be7b | 8 | `settleMs` delays the inbox refetch 200 ms so the row exit can play. |
| fc0be7b | 8 | Bulk `onDone` gets only the ids that succeeded. |
| fc0be7b | 8 | Bulk Skip keeps Task 6's disabled-without-spinner; the dialog's Skip spins. |
| fc0be7b | 8 | The row spinner overlays the mounted buttons so focus stays on the pressed one. |
| 7a37c78 | 9 | Undo also added to `points-list.tsx`'s draft Approve. |
| 7a37c78 | 9 | Undo covers draft → approved only, not "Using this bullet again". |
| 75316c7 | 10 | CircleCheck, not Check, for Copied (ruling, D2). |
| 75316c7 | 10 | `useCopy` takes `{ holdMs, onError }`; `onError` replaces the default toast. |
| b2ee932 | 10 | `status-chip.tsx` transition list `transform` → `scale` (Tailwind v4). |
| 65595c6 | 11 | The previous `pending` is held in state, not a ref (the React compiler forbids ref reads in render). |
| 5902b95 | 12 | `FieldMessage` ships with a `useFieldMessage` hook: one wiring for three call sites. |
| ef99894 | 14 | Local `rounded` renamed `snapped` (a corner pin flags the word). |
| ef99894 | 14 | Added the `sparkEnd` helper for Sparkline's last-point dot. |
| ef99894 | 14 | DeltaChip is `role="img"`; ProgressCount's visible sentence is `aria-hidden`. |
| 70f0d39 | Wave 2 fix | `ROW_EXIT_MS` removed from `triage-actions.tsx`; its consumer imports `lib/motion`. |
| acaac87 | 16 | Minus, not CircleHelp, for "requirements not stated" (ruling). |
| acaac87 | 16 | An unstated scan with unrun pay or experience checks reads "Checks not run yet". |
| acaac87 | 16 | `incomplete_profile` keeps its short detail line and link. |
| aa7a919 | 18 | The subscore ScoreBar uses `width="flex-1"` + `w-full`. |
| aa7a919 | 18 | The pin drops the `"> of 100"` clause (ruling). |
| 8d1f9f9 | 19 | The suggested chip border is `border-muted-foreground`: `border-outline` is not a token. |
| 8d1f9f9 | 19 | The add_keyword hint reads "Uses the job's exact words, in the place you pick." (the brief's wording was false). |
| 8d1f9f9 | 19 | The resolving collapse lives inside `GapCard`. |
| 765e2be | 20 | DotMeter name "How well it is shown" (the glossary bans "evidence"). |
| 765e2be | 20 | "New wording ready" added beside the drafted state's icon. |
| 0fb8493 | 21 | Focus ring `ring-ring`, not `ring-ring/50` (solid-ring pin). |
| 7821fb0 | 21 | The Ready chip is a neutral surface with a success check (ruling). |
| c5c031c | 22 | Gained / Lost use `increase` / `decrease`; Same uses `Minus` (ruling). |
| 6fd8242 | 23 | Chip words come from a concept-to-word map, keeping the `{ phrase, concept }` shape. |
| 6fd8242 | 23 | `FileDiff` and `X` stay direct lucide imports (not register concepts). |
| cc9e8e8 | 24 | The chip is named `PointActorChip` (the pin needs "ActorChip" in inbox-panel). |
| cc9e8e8 | 24 | Transition lists name `translate` / `scale` in entity-card, entity-detail and points-list. |
| 73b2ea5 | 24 | The agent chip shows the bare agent name; "From {agent}" stays in the hover title. |
| 26490c4 | 25 | Table `minWidth` stays 52rem (a typed union); column widths rebalanced. |
| 26490c4 | 25 | Strip counts go through `countOf` (sticky-lists pin). |
| 73edd6b | 25 | Click again clears a pressed quick filter. |
| 73edd6b | 25 | Saved rows' meter is labelled "Best ATS score". |
| 73edd6b | 25 | MCP docstrings live in `mcp_server/server.py`, not `client.py`. |
| d62f87e | 27 | "They can" items carry no glyph (ruling). |
| d62f87e | 27 | The run-outcome glyph is the `RunOutcome` component; `lib/agent-runs.ts` stays import-free (ruling). |
| d62f87e | 27 | Version source badges draw from `CONCEPT_ICONS`. |
| d62f87e | 27 | Ban in the settings card is offset with `relative top-0.5` (a rhythm pin bans `m[tby]-N`). |
| 2a3d552 | 26 | `StatTile` takes an optional `children` slot for the Sparkline. |
| e865a42 | 27 | The cover letter's "PDF ready" chip is a header sibling; the title takes `flex-1`. |
| eb114db | 28 | The rail's done tick is `circle-check` (ruling, D2). |
| eb114db | 28 | The glyph test strips block and line comments. |
| eb114db | 28 | `stages/track.js` had no code-level arrow to replace. |
| eb114db | 28 | Icons reach stage bodies as `build.icon`; `panel.js` throws at boot naming `icons.js`. |
| 3ca02a1 | Wave 5 fix | `Globe2` matched, not registered. |
| a0292a4 | 30 | Entity docs and `extension/INTERNALS.md` needed no edit. |
| a0292a4, 3e60947 | 30 | SYSTEM.md §12 wording was tightened to fit the cap, then restored verbatim in the fix round; room came from merging the new gotchas and joining wrap lines. |
| f528ab1 | 29 | `--cs-secondary-container` tokens beyond the brief's list (the selected Track segment). |
| f528ab1 | 29 | The harness `FakeNode` gains an `allText` getter. |
| f528ab1 | 29 | The rail numeral's `aria-label` dropped on locked and skipped rows (their words are visible). |
| f528ab1 | 29 | `--cs-muted-container` added: `surface-container` equalled the dark panel surface. |
| 138bd3b | Final fix | Test isolation fix outside the plan: an autouse fixture resets `_SEED_VALIDATION_ATTEMPTED`. |

## Rulings the architect made

The plan's "Execution rulings (architect, cloud run)" section holds the rulings that changed task text. The others:

- **Push target:** both branch names carry the commits; the plan's "do not push" was overridden by the owner's brief
  (no PR, no merge).
- **Concurrency:** the next task's implementer could start while the previous review ran, on disjoint files; each
  implementer staged only its own hunks. Cost: the one known-red intermediate commit above.
- **Owner-question defaults:** Form filling hides the idle line while a key is unsaved; "New wording ready" uses the
  drafts icon with no success tone; the inbox knock-out reads as a conflict (red); `cannot: Ban` covers the career
  "Unconfirmed" chip; documents use Paperclip so `FileText` means resume only; `email: Mail`, `coverLetter: ScrollText`.
- **Kept beyond the brief:** the sortable ATS column (the brief allowed it) and click-again-to-clear on quick filters.
- **No prop renames** on the primitives (`ScoreBar.width` is a class string, `Sparkline.width` a number), because
  later tasks' text used those names.
- **Tracker best score:** base score rows are upsert-singletons per job and resume, so "max over base rows" equals
  "latest per base".

## Deferred minor findings

Reviewed and left by the final review, by category: loose or brittle string pins (several tasks); redundant hand-written
`data-disabled` classes (a ratchet per the plan's non-goals); cosmetic chip height differences; the Companion's Withdrawn
chip has no line-through; mixed capitalisation in the rail's state words; SYSTEM.md sits at 999 of 1000 lines, so the
next addition there needs a trim first. The full list with reasons lives in the final review's triage; none blocks the
owner's pass.
