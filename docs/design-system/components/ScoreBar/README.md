A score bar shows one value on a fixed scale with its number beside it, such as an ATS score or skills covered.

**You provide:** a `label` (what the number is), a `value` and an optional `max` (default 100), and optionally `valueText` for a number that is not the raw value ("7 of 9"), `digits` and a `width` class (default `w-12`).

- A 6px track in `surface-container` with a `primary` fill that grows over `duration-medium2` with `ease-standard`.
- `role="meter"` with `aria-valuemin`, `aria-valuemax`, `aria-valuenow` and `aria-valuetext`; the visible number is `label-medium`, tabular.
- A score has no threshold and no warning color: the fill is always `primary`. A word such as Weakest goes on the lowest subscore only.

Source: `frontend/components/visual/score-bar.tsx`.
