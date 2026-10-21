A next step is a row's next move, in one look for every row: yours is a link, theirs is grey text.

**You provide:** either a `label` and an `href` (your move: "Apply", "Review resume") or `waiting` (their move: "Waiting to hear back").

- Your move is a text link in `label-large` `primary` with a 14px `ChevronRight`, 28px tall with `radius-corner-sm`; `-ml-2` lines its text up with the column.
- Their move is `body-medium` `muted-foreground` with tabular numbers, never a link.
- No fill at rest. While the row is hovered the link takes `secondary-container` with `on-secondary-container` (150ms), so the row that holds it carries `group/row`.
- Never a filled button: the one filled button belongs to the Lead.
- The link is a `GuardedLink`, so leaving unsaved work asks first.

Source: `frontend/components/visual/next-step.tsx`.
