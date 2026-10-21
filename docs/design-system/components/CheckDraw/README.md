A check draw marks a thing done the moment it is: the done mark's tick draws itself once.

**You provide:** optionally a `className` (a size, or a colour once the mark settles).

- The register's done mark, `CircleCheck` in `success`, 16px. Its tick draws over 300ms (`animate-check-draw`: `--duration-medium2`, strong ease-out) when it mounts.
- Mount it when the save lands, beside its word ("Saved"); the 1.2s hold and the settle are the caller's (`useSavedHold`).
- `animate-check-draw` is a registered `@utility`, so it takes variants (`data-saved:animate-check-draw`).
- Decoration (`aria-hidden`): the word says it.
- With reduced motion the tick is drawn at once.

Source: `frontend/components/visual/check-draw.tsx`.
