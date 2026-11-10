# App brand refresh: ink, one marigold signal, a one-colour mark

Date: 2026-11-09. Status: approved by the owner as a direction (job-page mock in marigold), built from this plan.

## Goal

Today one blue does every job in the app: the filled button, links, the current menu item, step and
progress bars, tinted chips and focus rings. When everything is the same colour, nothing stands out,
and the app looks like every other blue-and-white tool.

After this change the app is **neutral greys and ink, with one marigold signal that means "this is
your move"**. A person glancing at any screen should find the one thing to do next by colour alone.
Green, amber and red keep their meanings. The logo becomes one colour.

If a case is not covered below, choose what keeps marigold **rare** and the screen **calm**. Do not
add decoration. Do not invent new uses for the signal.

## Decisions

**D1. `--primary` becomes ink.** It stays a text-capable role, so every existing pin about primary as
text still holds.

| Token | Light | Dark |
|---|---|---|
| `--primary` | `oklch(0.205 0 0)` | `oklch(0.92 0 0)` |
| `--primary-foreground` | `oklch(0.985 0 0)` | `oklch(0.205 0 0)` |
| `--ring` | `oklch(0.4 0 0)` | `oklch(0.8 0 0)` |
| `--sidebar-primary` (dark) | unchanged | `oklch(0.92 0 0)` |

So links, the tab underline, progress and score bars, checked controls, the status dot and icon tints
turn ink without touching their classes.

**D2. The tinted containers go quiet.**

| Token | Light | Dark | Used for |
|---|---|---|---|
| `--secondary-container` / `--on-secondary-container` | `oklch(0.89 0 0)` / `oklch(0.2 0 0)` | `oklch(0.34 0 0)` / `oklch(0.93 0 0)` | tonal buttons, the current menu row, selected chips |
| `--primary-container` / `--on-primary-container` | `oklch(0.9 0.014 259)` / `oklch(0.3 0.03 259)` | `oklch(0.33 0.014 259)` / `oklch(0.92 0.01 259)` | the "info" status tint (Applied, Proposed, the Add job button) |

Secondary is pure neutral but one step darker than the surface ladder, so a selected chip never
matches an unselected one. Primary container keeps a trace of slate so "info" chips stay
distinguishable from neutral chips. The `-hover` mixes stay as they are. Check both by eye and by
the contrast pins; adjust lightness by at most 0.02 if two things that must differ end up the same.

**D3. A new role, the signal.** Marigold, in both schemes.

| Token | Light | Dark |
|---|---|---|
| `--signal` | `oklch(0.828 0.166 79.4)` (#ffb81f) | same |
| `--on-signal` | `oklch(0.19 0.039 92.2)` (#1a1300) | same |
| `--signal-hover` | `oklch(0.792 0.165 77.5)` | `oklch(0.856 0.156 84.4)` |
| `--signal-outline` | `oklch(0.717 0.151 75.7)` | `oklch(0.856 0.156 84.4)` |

Expose all four in the `@theme inline` block (`--color-signal`, `--color-on-signal`,
`--color-signal-hover`, `--color-signal-outline`). `on-signal` on `signal` is 10.7:1.

Rules for the signal:
- It is a **fill with dark text**. It is never a text colour, never an icon colour on a light
  surface, never a border on its own, never a chart colour. There must be no `text-signal` class
  anywhere.
- A signal fill on a light surface carries a 1px `signal-outline` edge, because marigold on white is
  only 1.7:1.

**D4. Where the signal appears. Exactly these, nowhere else:**
1. The filled button: `Button` variant `default` becomes
   `bg-signal text-on-signal hover:bg-signal-hover` plus the outline edge. The existing rule of one
   filled button per view is what keeps it rare; do not weaken that test.
2. The "needs you" count (the Today badge in the sidebar and anywhere the same badge component is
   used).
3. The current step of the four-step job page (`components/job-steps.tsx`): the current step's bar or
   ring uses the signal; finished steps use `primary` (ink); future steps stay as they are.

Everything else that is filled with `bg-primary` today (badges, the selected formatting segment,
checked controls, bars) becomes ink through D1 and stays that way.

**D5. Links must not rely on colour.** Ink links look like body text. Audit every `text-primary`
site (about 40). Where the text is clickable and was told apart only by being blue, it now carries
an underline (`underline underline-offset-2`), unless it already has a chevron or icon affordance or
sits in a button shape. The `Button` variant `link` becomes underlined at rest. Keep the pinned
literal for the referral link (`text-primary underline underline-offset-2`).

**D6. Charts keep their palette.** `--chart-1` stays the blue it is: in charts blue is data, not
brand. `charts/heatmap-chart.tsx` moves its ramp from `--primary` to `--chart-1` so it stays a data
colour; the sparkline may follow `--primary` (ink). Do not touch the chart validator's thresholds.

**D7. The Companion follows in the same change.** `extension/panel/panel.css` mirrors the app's
tokens by hand and a test compares them string for string. Update every mirrored `--cs-*` value, add
`--cs-signal`, `--cs-on-signal`, `--cs-signal-hover`, `--cs-signal-outline`, and apply D4 and D5
there: its one main filled button per view takes the signal, the rest go ink or neutral.

**D8. The mark is one colour.** The original two bolts joined into one shape. Source geometry and a
generator are provided (see Task 2). In the app the mark takes the text colour. Icons (favicon, app
icon, Companion icons, the Claude Desktop bundle icon) are a **marigold rounded tile with the ink
mark**: tile `#ffb81f`, mark `#1a1300`.

**D9. Warning stays where it is for now.** Warning is a dark amber text on a pale tint; the signal is
a bright fill. They differ in lightness and shape. Do not move the warning hue in this change. If,
on screen, a warning chip can be mistaken for a signal fill, report it; do not fix it by guesswork.

## Out of scope

The marketing site, the hero GIF and launch video, store listings, the README's copy, new features,
and any layout change. No new dependencies.

## Tasks

Two tasks touch disjoint files and may run at the same time. Task 3 runs after both.

### Task 1: colour roles (frontend, Companion, pins, colour docs)

Files: `frontend/app/globals.css`, `frontend/components/**` (not `brand-logo.tsx`),
`frontend/lib/**`, `extension/panel/**`, `backend/tests/test_frontend_*.py`,
`backend/tests/test_extension_*.py`, `docs/frontend-conventions.md`, `docs/design-system/README.md`
(all sections except Logo), `docs/design-system/tokens.json`.

1. Apply D1 to D3 in `globals.css` (both schemes) and the `@theme inline` block. Write every colour
   as `oklch(L C H)`; the pins read nothing else.
2. Apply D4: `ui/button.tsx`, the needs-you badge, `job-steps.tsx`.
3. Apply D5 across the `text-primary` sites and `ui/badge.tsx`'s link variant.
4. Apply D6.
5. Remove the hard-coded blues that are not data: `chart-kit.tsx`'s fallback stays equal to
   `--chart-1`; anything else found by searching for hue 259, `#2563EB`, `#1358bb`, `#d1e3ff` in
   `frontend/` and `extension/` is brought onto a role.
6. Apply D7 in the Companion.
7. Update the pins so they describe the new rules. **Do not delete an assertion to make it pass.**
   Keep every contrast floor. Change literals that moved (job steps, the button, the badge, the
   sidebar's badge). Add: `on-signal` on `signal` and on `signal-hover` is at least 4.5:1 in both
   schemes; no `text-signal` class exists in `frontend/` or `extension/`; `Button` `default` uses the
   signal; the Companion's `--cs-signal*` values equal the app's. If a pin encodes a rule this plan
   changes on purpose (for example a hue assertion on primary), rewrite it to the new rule and say
   so in your report.
8. Update `docs/frontend-conventions.md` and the Color section of `docs/design-system/README.md` and
   `tokens.json` so they state the new roles: primary is ink, the signal and its three uses, links
   are underlined ink, "info" is the slate container, blue is a chart colour only.

### Task 2: the mark and the icons

Files: `scripts/build_brand_assets.py` (new), `docs/assets/brand/**`,
`frontend/components/brand-logo.tsx`, `frontend/app/icon.svg`, `frontend/app/apple-icon.png`,
`extension/icons/*.png`, `mcpb/icon.png`, `docs/design-system/assets/Logos/README.md`,
`docs/design-system/components/Sidebar/preview.html`, the Logo section of
`docs/design-system/README.md`.

1. Add `scripts/build_brand_assets.py`: the one source of the mark's geometry. It writes the SVGs in
   `docs/assets/brand/` (mark in ink, in white and in `currentColor`; the tile avatars; the light and
   dark lockups with the existing wordmark paths untouched and only the mark swapped) and rasterises
   the icon PNGs and `favicon.ico` with Pillow (already a backend dependency), supersampled so edges
   are clean. A working prototype of the SVG half is supplied to the implementer; port it, keep its
   geometry exactly.
2. Generate: `frontend/app/icon.svg` (marigold tile, ink mark), `frontend/app/apple-icon.png`
   (180), `extension/icons/{16,32,48,128}.png`, `mcpb/icon.png` (512),
   `docs/assets/brand/icons/{favicon.ico,icon-192.png,icon-512.png}`. Fix `site.webmanifest` (theme
   colour `#0c0c0f`, and only name files that exist).
3. `brand-logo.tsx`: `MaestroMark` draws the one-colour mark in `currentColor`; `MaestroLogo` keeps
   its wordmark. Keep the exported names and props so callers do not change.
4. Replace `docs/assets/brand/social-preview.png` with the supplied new card and remove the stale
   `social-preview.svg` if nothing references it.
5. Rewrite the brand docs to the new rules: `docs/assets/brand/README.md`,
   `brand-tokens.css`/`.json` (ink `#0f172a` stays for print lockups, add marigold `#ffb81f` and
   on-marigold `#1a1300`, drop the blue and yellow facets), and `docs/design-system/assets/Logos/README.md`
   (its line forbidding yellow elsewhere in the UI is replaced by D3's rules).

### Task 3: reference docs and gates

1. `SYSTEM.md`: follow its header contract. Update, in place, whatever §8, §7 or §12 now say wrongly
   about the primary colour, the Companion's mirrored tokens or the brand files; keep section numbers;
   run `python3 scripts/check_system_md.py`.
2. `CHANGELOG.md`, under Unreleased: one "Changed" entry in plain words (the app is ink and grey with
   one marigold signal for your next move; the logo is one colour; the Companion matches).
3. Run every gate in Verification and fix what this change broke.

### Task 4: five first-run fixes (after Task 1, before Task 3)

Approved by the owner on 2026-11-09 after a fresh new-user audit. The goal: in a new user's first ten
minutes, every screen has exactly one obvious next step, and that step works. Each fix is small. Do
not widen any of them; if one turns out to need a larger change, stop and report.

**F1. Setup, step 1 (AI key): the main button saves.** Today the key is saved only by Test
(`frontend/components/setup/setup-model-step.tsx`), while Continue and Skip for now just move on
(`setup-flow.tsx`). A pasted key followed by Continue is lost. Make the step's main button
"Save and continue": it saves what was typed, runs the same check Test runs, and moves on only if
the check passes; on failure it stays and shows the existing problem message. If nothing was typed
and a key or server is already set, it simply moves on. Remove the separate Test button from this
step. "Skip for now" stays and still saves nothing. The same applies to the "your own server" choice.

**F2. Today leads a new user somewhere.** With setup done and no finished PDF, Today says "Nothing
waiting on you." (`frontend/app/today/page.tsx`), because Next up only picks an offer, a ready PDF or
an agent question (`backend/app/services/today.py`). Change: with no jobs saved, the lead is "Add
your first job" with one button to the add-job page. With at least one job that is not yet applied
to and has no ready PDF, Next up is the most recently touched such job and its next step, worded as
the job page words it. Existing Next up picks keep their priority over these two. Hide "This week"
until there is a first application.

**F3. After tailoring, land on the job page.** Today "Tailor resume" ends in the full editor, whose
main button is Save and whose only way on is a back arrow. Land instead on the job page's Tailored
resume step, which already lists the changes with undo and holds Create PDF. The editor stays one
click away behind Edit resume.

**F4. One setup list.** Remove the "Getting started" card from the Jobs page
(`getting-started-card.tsx` and its use), and point the two "no AI key" notices
(`frontend/app/new/page.tsx`, `frontend/app/applications/page.tsx`) at `/setup` instead of Settings.
Delete code the removal leaves unused.

**F5. The Companion on the Apply step.** Add one row to the job page's Apply step
(`apply-step.tsx`): "Fill the form with the Companion", linking to the Chrome Web Store listing the
README uses. If the app already knows a Companion has connected, show the row as a plain hint
without the store link; if it has no such knowledge, show the link always. One row, no card.

For all five: update or add the tests that pin these screens (the backend suite reads frontend
source), keep `test_frontend_one_filled_button.py` true on every screen you touch, follow D4 and D5
for any button or link you add, and write copy in the app's voice: short, literal, second person,
no em dashes.

## Verification

From the worktree, with the per-worktree virtualenv at `backend/.venv` and `frontend/node_modules`
installed:

- `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
- `cd frontend && npx tsc --noEmit && node --test lib/*.test.ts && node --test "components/**/*.test.mjs" && npm run lint && npm run build`
- `python3 scripts/check_system_md.py`

Then, by eye, on a throwaway stack (never the live app): Today, Jobs, a job page on each of its four
steps, Agent inbox, Base resumes, Career history, Analytics, Profile, Settings, and the Companion
panel, each in light and dark at 1280 and 1024 wide. On every screen: one marigold fill at most plus
the needs-you count; no blue outside charts; every link visibly a link; focus rings visible.
