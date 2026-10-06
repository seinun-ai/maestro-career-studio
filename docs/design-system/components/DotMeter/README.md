A dot meter shows a step on a short ordinal scale, such as the health evidence ladder or inbox readiness, with the step's word beside it.

**You provide:** `name` (what is measured), `filled` and `total` (the step and the scale) and `word` (what the step is called).

- Filled dots are `foreground`; empty dots are `surface-container-highest`. Each dot is 6px, `radius-full`, 2px apart.
- The group is one `role="img"` named "Evidence 3 of 5: Specific, no result"; the dots and the word are hidden from assistive tech so it reads once.
- The word always stays: the dots are the shape of the answer, not the answer.

Source: `frontend/components/visual/dot-meter.tsx`.
