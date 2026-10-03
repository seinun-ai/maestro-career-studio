Text fields, selects and text areas share one outlined shape: a visible label above, an optional hint between the label and the control, and the control.

**You provide:** a visible `Label` (sentence case, no colon), an `id` from `useId()`, and optionally one short hint tied with `aria-describedby`. For an error, set `aria-invalid` and say how to fix it under the control.

- 32px tall, `radius-corner-sm`, 1px `input` border, transparent fill, value in `body-medium`, label in `label-large`, hint and error in `body-small`.
- Focus: the border turns solid `ring` with a 3px halo. Invalid: `destructive` border and halo.
- No placeholder in a blank field: no example value, no instruction, no restated label. A format or a consequence is hint text. The one exception is a short "…" prompt in a search box.
- Delete a hint that only restates the label.
- The list search is the same input at 40px and `radius-full` with a leading Search icon.

Source: `frontend/components/ui/input.tsx`, `textarea.tsx`, `select.tsx`, `label.tsx`, `list-search.tsx`.
