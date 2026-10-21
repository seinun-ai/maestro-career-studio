A number roll shows a count that changes in place: each digit rolls to its new value.

**You provide:** the `value` and optionally a `className` for its type style.

- Each digit is a 0–9 column in a one-line box that slides on `translate` over `ROLL_MS` (400ms, `lib/motion.ts`) with the strong ease-out. Only the digits that changed move; a new digit appears in place.
- Tabular numbers, so the width holds still.
- The value is read once as text and the columns are hidden from screen readers. It never announces: if the change should be spoken, the parent holds the live region.
- With reduced motion it is the plain number.
- A number that should pass through every value on the way (a score) counts with `useCountUp` instead.

Source: `frontend/components/visual/number-roll.tsx`.
