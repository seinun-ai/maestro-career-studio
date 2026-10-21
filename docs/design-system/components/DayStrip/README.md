A day strip shows what an automation's runs reported over the last 14 days, one round dot per day.

**You provide:** the `runs` (`finished_at` and `outcome` from the run log); optionally `days` (default 14) and `today`.

- One 14px dot per local calendar day, oldest on the left and today on the right; "14 days ago" and "today" mark the ends in `body-small` `muted-foreground`.
- A day shows its worst outcome: `destructive` failed, `warning` partly done, `success` done. A day with no report is `surface-container-high`: Maestro schedules nothing, so an empty day is not a miss.
- Round, because it is status. Never a square: a square is a base resume.
- The strip is one `role="img"` sentence: "Last 14 days: a report on 4 days, 1 failed, 1 partly done". The legend under it names each colour that appears in the run log's words (Done, Partly done, Failed) and "No report"; screen readers skip it because the sentence says it.
- A day is local, not UTC, so a run at 23:30 counts on the evening it ran (`lib/day-strip.ts`).

Source: `frontend/components/visual/day-strip.tsx`, `frontend/lib/day-strip.ts`.
