A checkbox picks items or agrees to something that applies on save; a switch turns one setting on or off at once.

**You provide:** a visible text label and the checked state.

- Checkbox: 16px, `radius-corner-xs`, 1px `input` border; checked is `primary` with a `primary-foreground` Check.
- Switch: a 40×24px `radius-full` track, `input` when off and `primary` when on, with a 20px thumb that slides in `duration-short4` on `ease-standard`.
- Both take the solid `ring` on focus.
- Use a switch only when the change takes effect immediately; otherwise use a checkbox.
- A checkbox in a list row sits before the row's monogram; "Select all shown" sits above the list on the right.

Source: `frontend/components/ui/checkbox.tsx`, `switch.tsx`.
