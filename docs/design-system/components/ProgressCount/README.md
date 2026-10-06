A progress count says how far through a set you are, in words and a bar: "3 of 5 answered".

**You provide:** `done`, `total` and a `noun` ("answered"); `showText={false}` keeps the bar alone.

- A 6px, 64px-wide track in `surface-container` with a `primary` fill.
- The bar is `role="progressbar"` with `aria-valuenow`, `aria-valuemax` and an `aria-label` holding the full sentence, so the sentence is always available even when `showText` is false.
- Use it for counts that move toward done; a fixed-scale value is a ScoreBar.

Source: `frontend/components/visual/progress-count.tsx`.
