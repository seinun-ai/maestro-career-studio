# Design system tokens and the move to them

**Branch:** `design-system-tokens` (from `main` at `220950ce`).
**Reference:** `docs/design-system/` (brand book, tokens, component guidelines and previews, the old
class → token table). `docs/frontend-conventions.md` carries the rule; this file carries the order of work.

## Goal

One named token for every colour, surface, text style, corner, shadow and timing the app repeats, so a
new screen cannot pick a value by hand, and the look moves closer to Material 3 without changing the
brand (Geist, Lucide icons, the blue and yellow mark, compact controls).

## Done on this branch (no screen changes)

- `frontend/app/globals.css`: status roles (`success`, `warning`, `attention`, `tertiary`, the
  `error-container` pair), the `surface-container-*` ladder, the M3 type scale, the `corner-*` scale,
  `shadow-level1..3`, M3 easings and durations. Every addition is new; no existing token changed value.
- `frontend/lib/utils.ts`: the new scale names registered with tailwind-merge.
- `backend/tests/test_frontend_design_tokens.py`: contrast, ladder order and registration pins.
- `docs/frontend-conventions.md`: the token rule.
- `docs/design-system/`: the design system as files.
- Step 1, the status vocabulary: `STATUS_STYLES`, `NEEDS_YOU` and `PROPOSAL_STATUS_CHIP` in
  `status-chip.tsx`, both `GRADE_STYLES` maps and the sidebar's Needs you badge are role container pairs.

## What is left, in order

Each step is one reviewable change. Counts are from `frontend/app` and `frontend/components` at the
branch point.

| # | Step | From | To | Size |
|---|---|---|---|---|
| 2 | Remaining palette classes | the `text-/bg-/border-<palette>-N` uses left after step 1 (302 in 39 files before it; amber and emerald lead) | `success` / `warning` / `attention` / `tertiary` / primary container | largest step; split by folder |
| 3 | Surfaces | 74 `bg-muted/N` uses in 45 files, 11 opacities | `/10`–`/30` → page (drop the fill) or `surface-container-low`; `/35`–`/60` → `surface-container-low`; `/70` and solid → `surface-container` | mechanical |
| 4 | Type | `text-[22px]` page titles, `text-[10px]`/`[11px]`/`[0.8rem]` (33 uses), size + weight pairs | `text-title-large`, `text-label-small`, `text-title-medium` and the rest | start with `PageHeader`, `CardTitle`, `Badge` |
| 5 | Corners | 14 `rounded-*` variants | controls `corner-sm`, cards `corner-md`, dialogs `corner-xl`, pills `rounded-full` | primitives first; visible change (cards 14px → 12px, controls 10px → 8px, dialogs larger) |
| 6 | Shadows | 54 `shadow`/`shadow-sm`/`-md`/`-lg` uses | `shadow-level1..3` on menus, popovers, dialogs, the hovered FAB; none elsewhere | |
| 7 | Buttons | `variant="secondary"` (35 uses) beside `tonal` (6) | one low-emphasis filled variant: `tonal` | drop `secondary` when its last caller moves |
| 8 | CompanyMonogram | six palette pairs | the four status containers plus primary and secondary container | keeps the hash, changes the tints |

## UX changes that go with it (owner decides each)

1. **Sidebar current row is a full pill** (`rounded-full`), as in M3's navigation drawer. It already
   uses the secondary container, semibold and `aria-current`.
2. **Page sections use line tabs** (`TabsList variant="line"`, already in `ui/tabs.tsx`): Analytics,
   Settings, Career history, the job page, the health report. The filled segmented look stays for view
   switches only (Tracked / Yours / Agents, Day / Week). Today both look alike.
3. **The Jobs status filter becomes filter chips**: one chip per status with its count, selected =
   tonal + Check + `aria-pressed` (the existing "selected in a set" rule). Same for the Agent inbox's
   four dropdowns where a filter has five or fewer values.
4. **Group headings lose the capitals.** `CONTACT`, `SUMMARY`, `SKILLS`, `TO REVIEW · 19` (19 `uppercase`
   uses in 12 files) become sentence-case `text-title-small text-muted-foreground`.
5. **Health-report rows use the outline-variant edge**, not a tinted violet border, and the "Answer"
   action stays the one text button per row.
6. **Stat tiles are filled cards** on `surface-container-low`, corner-md, label in `text-label-medium`,
   value in `text-title-large`.

## Ledger row to add when SYSTEM.md has room

`SYSTEM.md` is at its 1,000-line cap, so the §13 row was not added on this branch. When a line frees up:

`| design-tokens | palette status classes, bg-muted/N, bracketed text sizes → role, surface and type tokens | both-live | grep -rnE "(text|bg|border)-(amber|emerald|green|blue|violet|orange|red|rose|cyan|sky)-[0-9]|bg-muted/[0-9]|text-\[[0-9.]+(px|rem)\]" frontend/app frontend/components returns only the chart palette and comments | large |`
