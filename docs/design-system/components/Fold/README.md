A fold is the Folded tier: one row that keeps advanced or rare things one click away and says what is inside without opening.

**You provide:** a `title`, the `children` it opens to, and optionally a `summary` (a count or a few words: Automations' Recent runs says "3 · 1 failed"), `defaultOpen` and a `className`. Pass `open` and `onOpenChange` when something else on the page opens it too (the Agent inbox's "applied this week" count opens History).

- A `radius-corner-md` row on `card`, 52px tall with `px-5`: a 16px `ChevronRight` in `muted-foreground`, the title in `title-small`, and the summary on the right in `body-small` `muted-foreground` with tabular numbers.
- The chevron turns a quarter (`rotate-90`) on `transition-[rotate]` at `--duration-short3` with `ease-standard`. The property is named, never `transform`.
- A real disclosure: the row is a button with `aria-expanded` and `aria-controls`, and the panel under it is `hidden` while closed, so its controls leave the tab order.
- Folds go last on a page, after the Lead and the Also tiers.

Source: `frontend/components/ui/fold.tsx`.
