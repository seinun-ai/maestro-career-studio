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
- Step 3, surfaces, and UX change 6: all 74 `bg-muted/N` uses are gone. Hovered rows, quiet panels and tiles
  take `surface-container-low`, chips and tracks `surface-container`; five barely-there tints on bordered or
  dimmed boxes were dropped. `StatTile` is a filled card (`surface-container-low`, `rounded-corner-md`,
  `text-title-large` value at weight 500). `test_frontend_design_tokens.py` fails on any `bg-muted/N` left.
- Step 2, palette classes: the 205 `text-/bg-/border-<palette>-N` uses in 36 files outside the monogram are roles. Chips and small
  labels are container pairs, dots are `bg-success` / `bg-warning` / `bg-primary`, text on a surface is
  `text-success` / `text-warning`. Caution, pass and info boxes are container callouts without a tinted
  border; tinted card edges (the health report's Fix and Question cards, the Serious gate) are `border-border`
  (UX change 5). The Chat greeting's blue-to-rose gradient is plain `text-foreground`. `CompanyMonogram`
  was the one exception until step 8; `test_frontend_design_tokens.py` now fails on any palette utility.
- Step 4, type, and UX change 4: every raw size (826 `text-xs`/`sm`/`base`/`lg`/`2xl`/`3xl` and 33 bracketed
  `text-[Npx]`/`[Nrem]` uses) is a scale utility, and the hand-paired `font-medium`/`font-semibold`/`font-bold` beside
  them is gone, except the page title (`text-title-large font-medium`), the current nav row (600) and the health
  grade letter (`text-headline-small` at 600). Group headings and meta labels are sentence case, with no
  `uppercase` and no tracking: 17 uses in 12 files. `test_frontend_design_tokens.py` fails on a raw size, on
  `uppercase`, and on a weight paired with a scale utility outside an allow-list.
- Step 5, corners, and UX change 1: every `rounded-*` is `rounded-corner-xs|sm|md|lg|xl`, `rounded-full` or
  `rounded-none` (about 230 uses in 107 files). Cards, tiles, callouts, wells and every other container are
  12px (cards and `rounded-2xl` boxes were 14 to 18px, `rounded-md` boxes 8px), controls and toggle segments
  8px (Button, Input, Select and Textarea were 10px; the 69 `rounded-full` overrides on Buttons and Select
  triggers are gone, since the READMEs sanction no round icon button), segmented toggles and chips pills, menus, tooltips and their items 4px, dialogs 28px, the
  FAB and sheets 16px. A popover is a panel, so it is 12px; `POPUP_SURFACE` carries no corner and the menu
  adds its own. Every sidebar row is a `rounded-full` pill, so hover and the current row share a shape.
  Chips and removable tags are `rounded-full`. `test_frontend_design_tokens.py` fails on a Tailwind
  `rounded-*` or a bracketed radius (one allow-listed literal: the tooltip arrow) and pins the primitives.
- Step 6, shadows: of the 39 stock shadow utilities, 5 became `shadow-level1` (the hovered FAB, status chip and
  two interactive chips, the focused skip link), 9 `shadow-level2` (menus, selects, popovers, a dragged row, the sticky
  bars and the PDF page pill over scrolling content, an inline chart tooltip) and 1 `shadow-level3` (the sheet, since moved to `shadow-level1`); the other 24 are gone,
  8 of them `shadow-none` that only cancelled a card's or input's shadow. Elevation follows M3: level1 a hovered FAB
  or chip, a focused skip link and the modal sheet (under its scrim); level2 menus, popovers, rich (chart) tooltips,
  sticky bars, the PDF page pill and a dragged row; level3 dialogs and toasts; none for cards, tiles, tables, plain
  tooltips and controls at rest. The dialog gains `shadow-level3` and the chart-kit tooltip `shadow-level2`, neither of
  which had one. Toasts had Sonner's own `0 4px 12px rgba(0,0,0,.1)`; it is replaced by `shadow-level3!` (Sonner's CSS
  is unlayered, so the utility needs `!`) with a `focus-visible:ring-2 ring-ring` that restates Sonner's box-shadow
  focus indicator. The plain tooltip stays flat. The sidebar outline
  variant's hairline is a real `border` (its `hsl(var(--sidebar-border))` wrapped an oklch token and painted nothing);
  the sticky table header's inset hairline is the one allow-listed literal. `test_frontend_design_tokens.py` fails on any
  `shadow-*`, `drop-shadow-*`, `inset-shadow-*` or `text-shadow-*` that is not `shadow-level1|2|3`, on a stylesheet
  `@apply` shadow, on a shadow passed to `Card`, `GalleryCard`, `StatTile`, `TableFrame` or `EmptyState`, and pins which
  primitives carry which level.
- Step 7, buttons: of the 35 `variant="secondary"` in the app, 8 were Buttons and 27 were Badges. Six (Add section,
  Add item, See all skill gaps twice, Choose file, Add group) are `tonal`; the two Try again buttons are `outline`,
  like every other retry in the app (tonal on a red-tinted alert is wrong). The Button's `secondary` variant is
  deleted; Badge keeps its own for plain metadata. `test_frontend_design_tokens.py` fails on a Button, IconButton or
  `buttonVariants` call that asks for `secondary`.
- Step 8, CompanyMonogram: its six palette pairs are four tones that are not statuses (primary, tertiary and
  secondary container, and `surface-container-highest` with `text-foreground`), not the six containers first planned:
  StatusChip is the only place a state is named and coloured, so a success, warning or attention monogram would share
  an exact fill with the status chip in the same Jobs row. The hash is kept and the modulo is 4, so each company
  re-slots once; the tint is identity only, and its comment says so. The palette pin has no allow-list now, a new pin
  holds the tones to that list and rejects any status container, and `test_frontend_color_roles.py` lost the copied
  Tailwind shades, the theme-match test and the palette-text scan, which measured only the monogram.

## Steps, in order

Each step is one reviewable change. Counts are from `frontend/app` and `frontend/components` at the
branch point.

| # | Step | From | To | Size |
|---|---|---|---|---|
| 2 | ~~Remaining palette classes~~ done | the `text-/bg-/border-<palette>-N` uses left after step 1 (302 in 39 files before it; amber and emerald lead) | `success` / `warning` / `attention` / `tertiary` / primary container | largest step; split by folder |
| 3 | ~~Surfaces~~ done | 74 `bg-muted/N` uses in 45 files, 11 opacities | `/10`–`/30` → page (drop the fill) or `surface-container-low`; `/35`–`/60` → `surface-container-low`; `/70` and solid → `surface-container` | mechanical |
| 4 | ~~Type~~ done | `text-[22px]` page titles, `text-[10px]`/`[11px]`/`[0.8rem]` (33 uses), size + weight pairs | `text-title-large`, `text-label-small`, `text-title-medium` and the rest | start with `PageHeader`, `CardTitle`, `Badge` |
| 5 | ~~Corners~~ done | 14 `rounded-*` variants | controls `corner-sm`, cards `corner-md`, dialogs `corner-xl`, pills `rounded-full` | primitives first; visible change (cards 14px → 12px, controls 10px → 8px, dialogs larger) |
| 6 | ~~Shadows~~ done | 54 `shadow`/`shadow-sm`/`-md`/`-lg` uses | `shadow-level1..3` on what floats (see Step 6 above); none elsewhere | visible change: resting cards, inputs, switches and tabs lose their shadow |
| 7 | ~~Buttons~~ done | `variant="secondary"` (35 uses) beside `tonal` (6) | one low-emphasis filled variant: `tonal` (`outline` for a retry) | drop `secondary` when its last caller moves |
| 8 | ~~CompanyMonogram~~ done | six palette pairs | four non-status tones: primary, tertiary and secondary container, `surface-container-highest` | keeps the hash (modulo 4), changes the tints |

## UX changes that go with it

The owner approved all six on 2026-10-03. Each lands with the step that touches its surface: 1 with
corners (step 5), 4 with type (step 4), 6 with surfaces (step 3), 2, 3 and 5 as their own changes after
step 3.

1. **Sidebar current row is a full pill** (`rounded-full`), as in M3's navigation drawer. It already
   uses the secondary container, semibold and `aria-current`.
2. ~~**Page sections use line tabs**~~ done (`TabsList` in `ui/tabs.tsx` is the line style; the indicator is `primary`): Analytics,
   Settings and Profile, Career history, the job page, the health report. The filled segmented look stays for view
   switches only (Tracked / Yours / Agents, Day / Week). The row is full width with a hairline under it; a count is a
   plain muted number. Every other tab strip followed (the resume studios' section tabs, the template editor, the chat scope
   picker, the import and New base resume dialogs and the career-history import drawer), so the filled strip
   and its `variant` are deleted; the row scrolls sideways rather than wrapping, and every panel stays mounted.
3. ~~**The Jobs status filter becomes filter chips**~~ done as `components/filter-chips.tsx` (one chip per value
   with its count, selected = tonal + Check + `aria-pressed`, several on, none on = no filter), but the Jobs filter
   stays a Select: measured in Geist 12px, its eight application values are 773px of chips and gaps (more with
   the four agent-lane values) against a 720px toolbar row at 1024 and 976px at 1280, with the 209px Tracked /
   Yours / Agents toggle sharing it. None of the Agent inbox's four dropdowns qualifies (Sort and Minimum score
   are single-valued, Role has six or more values and Job board dozens), so the one caller is the inbox's
   History status filter, which was hand-built chips with an "All" chip and no counts.
4. **Group headings lose the capitals.** `CONTACT`, `SUMMARY`, `SKILLS`, `TO REVIEW · 19` (19 `uppercase`
   uses in 12 files) become sentence-case `text-title-small text-muted-foreground`.
5. **Health-report rows use the outline-variant edge**, not a tinted violet border, and the "Answer"
   action stays the one text button per row.
6. **Stat tiles are filled cards** on `surface-container-low`, corner-md, label in `text-label-medium`,
   value in `text-title-large` (amended 2026-10-03: label in `text-body-small`, to match the StatTile README).

## Ledger row to add when SYSTEM.md has room

With step 8 landed, the grep below finds only a comment in `globals.css` (checked 2026-10-03), so the row's delete
condition is already met; the pins in `test_frontend_design_tokens.py` now hold the line, and the row is worth adding
only if the owner wants the ledger to name the migration.

`SYSTEM.md` is at its 1,000-line cap, so the §13 row was not added on this branch. When a line frees up:

`| design-tokens | palette status classes, bg-muted/N, bracketed text sizes → role, surface and type tokens | both-live | grep -rnE "(text|bg|border)-(amber|emerald|green|blue|violet|orange|red|rose|cyan|sky)-[0-9]|bg-muted/[0-9]|text-\[[0-9.]+(px|rem)\]" frontend/app frontend/components returns only the chart palette and comments | large |`
