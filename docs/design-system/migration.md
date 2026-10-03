# Moving existing code

Use this table when touching a file that still carries the old classes. The tokens exist in `frontend/app/globals.css`; the order of work is in `docs/plans/2026-10-02-design-system-tokens.md`.

## Status and palette classes

| Today | Write instead |
| --- | --- |
| `bg-emerald-*/N text-emerald-*` and `bg-green-*/N text-green-*` with their `dark:` twins | `bg-success-container text-on-success-container` |
| `bg-amber-*/N text-amber-*` | `bg-warning-container text-on-warning-container` |
| `bg-orange-500/10 text-orange-800` (Needs you) | `bg-attention-container text-on-attention-container` |
| `bg-violet-*/N text-violet-*` | `bg-tertiary-container text-on-tertiary-container` |
| `bg-blue-*/N text-blue-*` | `bg-primary-container text-on-primary-container` |
| `bg-red-*/N text-red-*`, `bg-destructive/10 text-destructive` on a chip | `bg-error-container text-on-error-container` |
| A palette dot (`bg-amber-500`, `bg-emerald-600`) | `bg-warning`, `bg-success`, `bg-attention`, `bg-tertiary`, `bg-primary`, `bg-destructive` |
| Palette text on a surface (`text-emerald-700 dark:text-emerald-400`) | `text-success`, `text-warning`, `text-attention`, `text-tertiary` |
| `bg-slate-500/10 text-slate-600 dark:text-slate-400` (a neutral chip) | `bg-surface-container text-muted-foreground` |
| A caution, pass or info box: `border-amber-500/30 bg-amber-500/10 text-amber-900`, `border-amber-300 bg-amber-50 dark:...` | `bg-warning-container text-on-warning-container` (pass: success pair; info: primary pair). Drop the tinted border and the palette class on its icon and spans: they inherit the pair's text |
| A tinted card or row edge (`border-amber-500/40`, `border-violet-500/30`) | `border-border`: the card's own label or action already says its kind (a Serious badge, Review or Answer, the question line) |
| A faint whole-row tint (`bg-amber-500/5`, `bg-emerald-500/5`) | drop it when a chip, dot or icon on the row states the state; otherwise the container fill |
| An outline badge with a tinted border and palette text (`border-amber-500/40 text-amber-700`) | `border-transparent bg-warning-container text-on-warning-container` |
| A gradient on text (`from-primary via-violet-500 to-rose-400 bg-clip-text`) | `text-foreground` |

The fatal gate (`border-destructive/50 bg-destructive/5`) and the note callout (`border-primary/25 bg-primary/[0.04]`) stay as they are.

## Surfaces

| Today | Write instead |
| --- | --- |
| `bg-muted/10` to `bg-muted/30` | no fill, or `bg-surface-container-low` |
| `bg-muted/35` to `bg-muted/60` | `bg-surface-container-low` |
| `bg-muted/70`, `bg-muted` | `bg-surface-container` |
| `bg-muted/70` on a card, dialog or popover (a chip, a track) | `bg-surface-container-high` |
| `hover:bg-muted/50` on a row | `hover:bg-surface-container-low` |

## Type

| Today | Write instead |
| --- | --- |
| `text-[22px] font-medium` | `text-title-large font-medium` (the page title keeps its 500; so does the `h1` of a full-page state such as not found) |
| `text-base font-medium` (card title) | `text-title-medium` |
| `text-base` | `text-body-large` |
| `text-sm font-medium` | `text-title-small` for a heading, name, row primary text or table header; `text-label-large` for a button, field label, tab or control text |
| `text-sm` | `text-body-medium` |
| `text-xs font-medium` | `text-label-medium` |
| `text-xs` | `text-body-small` (on a Badge or a small Button, which already set `text-label-medium`, drop it; on a Label write `text-label-medium`) |
| `text-xs font-normal` on a Badge or Button | `text-body-small`: the weight comes from the scale |
| `text-[10px]`, `text-[11px]`, `text-[0.65rem]`, `text-[0.7rem]` | `text-label-small`; drop any `font-medium` beside it. A sentence at that size is `text-body-small` |
| `text-[0.8rem]` | `text-label-medium` |
| `text-lg font-medium` (a page-level state heading) | `text-title-large font-medium` |
| `text-2xl font-semibold` (a large stat) | `text-headline-small` |
| `text-3xl` (the chat greeting) | `text-headline-medium` |
| `text-3xl font-bold` (the health grade letter) | `text-headline-small font-semibold` (the one 600 besides the current nav row) |
| `text-xs font-semibold uppercase tracking-[0.12em]` (group heading) | `text-title-small text-muted-foreground`, sentence case: no `uppercase`, no tracking |
| `text-[11px] uppercase tracking-wide` (a `dt` or stat label) | `text-label-small text-muted-foreground`, sentence case |
| `leading-snug`, `leading-relaxed`, `leading-tight` beside a size | drop it: the scale sets the line height. Long reading text (the chat reply and its code blocks, notes, the profile summary, judged text) and inline diff highlights keep `leading-6` or `leading-7` |
| `font-medium` or `font-semibold` beside a size | drop it: the scale sets the weight (a semibold name or heading is now 500) |

## Buttons

| Today | Write instead |
| --- | --- |
| `<Button variant="secondary">`, `buttonVariants({ variant: "secondary" })` (grey fill) | `variant="tonal"` (`secondary-container`, the one low-emphasis filled button); `outline` on a `secondary-container` surface |
| `<Badge variant="secondary">` | stays: Badge's grey fill is for plain metadata |

## Shape, shadow, motion

| Today | Write instead |
| --- | --- |
| `rounded-lg`, `rounded-md` on a control, a small icon button or an option tile (a selectable flex-1 or full-width tile) | `rounded-corner-sm` |
| `rounded-full` passed to a `Button`, a `SelectTrigger`, a `TabsList` or a `TabsTrigger` | drop it: the Button, TextField and Tabs READMEs set 8px, and none sanctions a round icon button or a pill tab strip |
| A segmented toggle (an outline holding option segments) | `rounded-full` on the outline and on each segment, as `source-toggle.tsx` |
| A `TabsTrigger` inside its 3px-padded `TabsList` | the list stays `rounded-corner-sm`, the trigger is `rounded-corner-xs` so they nest |
| `rounded-[min(var(--radius-md),10px)]` and its `in-data-[slot=button-group]:rounded-lg` twin on a Button or Select size | drop it: every size is `rounded-corner-sm` |
| `rounded-xl`, `rounded-2xl`, `rounded-lg`, `rounded-md` on a card, tile, table frame, callout, panel, well, list box, dropzone, image frame or empty-state box | `rounded-corner-md` |
| `rounded-2xl` in a `Card`'s `className` | drop it: the `Card` already is `rounded-corner-md` |
| A container nested in a container (a well in a card, a row in a list box) | its own kind's corner: `rounded-corner-md` |
| A sheet's open edge | `data-[side=right]:rounded-l-corner-lg` and its three siblings, set in `ui/sheet.tsx` |
| A header or reveal control that reads as a pill (the sidebar reveal button, the health and sync chips) | `rounded-full` |
| `rounded-t-xl`, `rounded-b-xl` on a card's header, footer or image | `rounded-t-corner-md`, `rounded-b-corner-md` |
| `rounded-r-md` on a joined control | `rounded-r-corner-sm` |
| `rounded-[16px]` (the FAB) | `rounded-corner-lg` |
| `rounded-xl`, `rounded-b-xl` on a dialog and its footer | `rounded-corner-xl`, `rounded-b-corner-xl` |
| `rounded-md`, `rounded-lg` on a menu surface or a menu, select or listbox item | `rounded-corner-xs` |
| A popover used as a panel (prose, a button, a link), not a menu | `rounded-corner-md` (`PopoverContent` sets it; `POPUP_SURFACE` carries no corner) |
| `rounded`, `rounded-sm`, `rounded-[4px]` on a code chip, a `kbd`, a grade chip, an overlay label, the checkbox, a heatmap cell, a chart tooltip | `rounded-corner-xs` |
| `rounded-md` on a removable tag or a chip, `rounded-sm` on the remove button inside it | `rounded-full` |
| `rounded` on a progress track or its bar | `rounded-full` |
| `rounded-md` on a `SidebarMenuButton` or its sub-menu row, its skeleton, its count badge and its row action | `rounded-full` (hover and current share the shape) |
| `rounded-4xl` on a pill | `rounded-full` |
| `rounded-2xl rounded-br-md` (a chat bubble with a tail) | `rounded-corner-md rounded-br-corner-xs` |
| `rounded-[2px]` on a rendered PDF page | `rounded-corner-xs`; the tooltip arrow's `rounded-[2px]` stays, a 4px corner would blunt its point |
| `--radius`, `var(--radius-md)` in a class or a style | `--radius-corner-*`; the `--radius-sm` to `-4xl` ladder is only for third-party components |
| `shadow-sm`, `shadow`, `shadow-xs`, `shadow-none` on a card, tile, panel, input, button, tab, switch, slider, rendered PDF page or a selected segment | none: delete it, and delete a `shadow-none` that only cancelled a primitive's shadow (no primitive has one now). A card that lifts on hover moves and tints instead: no `hover:shadow-sm` |
| `hover:shadow-sm` on a clickable chip (`StatusChip`, a removable tag) or the FAB | `hover:shadow-level1` |
| `shadow-md`, `shadow-lg` on a menu, select, popover or tooltip surface; `shadow-sm` on a chart tooltip; a toast | `shadow-level2` (a chart tooltip's inline style is `boxShadow: "var(--shadow-level2)"`) |
| `shadow-md` on a dragged row; `shadow-sm` or `shadow` on a sticky bar or pill that floats over scrolling content | `shadow-level2` |
| `shadow-lg` on a sheet; none on a dialog | `shadow-level3` |
| `shadow-[0_0_0_1px_hsl(var(--sidebar-border))]` (a hairline in a shadow) | a real `border border-sidebar-border`; `hsl(var(--x))` around an oklch token paints nothing |
| `shadow-[inset_0_-1px_0_var(--color-border)]` on a sticky table header cell | stays: a border on a sticky `<th>` under `border-collapse` scrolls away from the header (the one allow-listed literal) |
| `duration-150 ease-out` | `duration-(--duration-short3) ease-standard` |

## Rules while moving

- Add a new `@theme` scale name to the tailwind-merge list in `frontend/lib/utils.ts` in the same change, or `cn()` drops it.
- There is no Button `variant="secondary"` any more: every grey secondary button is `tonal`, or `outline` when it sits on a `secondary-container` surface. A Badge's `variant="secondary"` stays (plain metadata).
- Do not mix old and new in one component: move the whole file.
