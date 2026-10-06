A sparkline shows a trend with no axes: the area, the line and a dot on the latest value.

**You provide:** `values`, a `label` that says what the trend is, and optionally `width` (120) and `height` (32).

- The area is `primary-container`, the line `primary` at 1.5px, the last point a 2.5px dot.
- The SVG is `role="img"` named by `label`; put the latest number beside it in text.
- Pass `width` and `height` that match the size it is drawn at: the SVG stretches to fit, and only the stroke stays 1.5px. A flat or single-value series draws a line across the middle; an empty one draws nothing.

Source: `frontend/components/visual/sparkline.tsx`.
