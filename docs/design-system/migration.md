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

The fatal gate (`border-destructive/50 bg-destructive/5`) and the note callout (`border-primary/25 bg-primary/[0.04]`) stay as they are.

## Surfaces

| Today | Write instead |
| --- | --- |
| `bg-muted/10` to `bg-muted/30` | no fill, or `bg-surface-container-low` |
| `bg-muted/35` to `bg-muted/60` | `bg-surface-container-low` |
| `bg-muted/70`, `bg-muted` | `bg-surface-container` |
| `hover:bg-muted/50` on a row | `hover:bg-surface-container-low` |

## Type

| Today | Write instead |
| --- | --- |
| `text-[22px] font-medium` | `text-title-large font-medium` |
| `text-base font-medium` (card title) | `text-title-medium` |
| `text-sm font-medium` | `text-title-small` for a heading or name, `text-label-large` for a button or field label |
| `text-sm` | `text-body-medium` |
| `text-xs font-medium` | `text-label-medium` |
| `text-xs` | `text-body-small` |
| `text-[10px]`, `text-[11px]`, `text-[0.65rem]`, `text-[0.7rem]` | `text-label-small` |
| `text-[0.8rem]` | `text-label-medium` |
| `text-xs font-semibold uppercase tracking-[0.12em]` (group heading) | `text-title-small text-muted-foreground`, sentence case |

## Shape, shadow, motion

| Today | Write instead |
| --- | --- |
| `rounded-lg` on a control | `rounded-corner-sm` |
| `rounded-xl` on a card, tile, table or callout | `rounded-corner-md` |
| `rounded-[16px]` (the FAB) | `rounded-corner-lg` |
| `rounded-xl` on a dialog | `rounded-corner-xl` |
| `rounded`, `rounded-[4px]` | `rounded-corner-xs` |
| `rounded-4xl` on a pill | `rounded-full` |
| `shadow-sm`, `shadow` | `shadow-level1`, or none on a card |
| `shadow-md` | `shadow-level2` |
| `shadow-lg` | `shadow-level3` |
| `duration-150 ease-out` | `duration-(--duration-short3) ease-standard` |

## Rules while moving

- Add a new `@theme` scale name to the tailwind-merge list in `frontend/lib/utils.ts` in the same change, or `cn()` drops it.
- A Button's `variant="secondary"` becomes `tonal` when it is a create or secondary action, `outline` otherwise.
- Do not mix old and new in one component: move the whole file.
