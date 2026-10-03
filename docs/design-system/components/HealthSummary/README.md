The health summary band opens a resume's health report: the grade, the score, how far the next grade is, and the one filled action.

**You provide:** the report (grade, score, level, the server's next-grade line, counts) and the link that starts the question pass.

- One `radius-corner-md` outlined band across the full column.
- The grade is a 56px `radius-corner-sm` tile in `headline-small` at weight 600. A and B are `success-container`, C `warning-container`, D `attention-container`, F and Must fix `error-container`.
- Score in `title-small`; the level is a neutral Badge.
- Progress to the next grade is a 6px `radius-full` bar, `primary` on `surface-container`, with the server's sentence under it in `body-small`.
- **Start the questions** is the report's only filled button; every card action below is tonal or text-style.
- Small grade chips (lists, headers) use the same four roles at `label-small`, `radius-corner-xs`. The letter is always shown, so the grade never depends on color.
- The health chip in an editor header is a `radius-full` outlined pill holding that grade chip.

Source: `frontend/components/resume-health/summary-band.tsx`, `health-badges.tsx`, `finding-cards.tsx` (`GRADE_STYLES`). The grade colors match the source. Changed from source: the track from `muted` to `surface-container`.
