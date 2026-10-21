Working dots say the AI is working, beside the words for what it is doing: "Writing your cover letter".

**You provide:** the `label`, and optionally a `className`.

- Three 7px `primary` dots that rise and brighten in turn (0, 120 and 240ms apart) on a 900ms loop, then the label in `label-large`.
- A loop that says "still going", like the skeleton shimmer, so it runs past the 400ms budget. No transition may.
- `role="status"`: the label is spoken when it appears. The dots are hidden.
- It replaces a spinner where the work is shown. A button that runs its own request keeps `pending`.
- With reduced motion the dots hold still at 60% opacity.

Source: `frontend/components/visual/working-dots.tsx`; `.working-dot` in `frontend/app/globals.css`.
