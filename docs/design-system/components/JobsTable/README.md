The jobs table lists one job per row: who and what, its match score, its status, its dates and its next step.

**You provide:** the rows. Each needs a company, a role line, a status, dates and the server's stage. The company name is the row's link.

- A `radius-corner-md` frame with a `border`; rows divide with a `border` hairline and hover to `surface-container-low`.
- Header cells are 40px in `title-small`; the sorted column carries `aria-sort` and an arrow. In a long list the header sticks under the toolbar.
- Company in `title-small`, role line and metadata in `body-small` `muted-foreground`. An empty cell is an em dash.
- The Match score is a ScoreBar; its accessible name and its hover name the application's resume. There is no Resume column.
- Next step, between Applied and Added, is one small button linking where the job waits, rising in emphasis without ever being filled (one filled button per view): ghost for Score and Analyze gaps, outline for "Continue gaps · 2 of 5" and Review resume, tonal for Apply. An applied row reads "Waiting to hear back" in muted `body-small` while its status is Applied; later and closed rows leave it empty.
- Status is always a StatusChip. While the job is moving between copies the chip is locked (see StatusChip).
- Where is a narrow column after Status, with no sort. It appears only when some visible row has an owner: a muted icon and one word, "Laptop", "Bot" or "Moving" (a handover is on its way). The icon shows who holds the job now, so Moving keeps the laptop's icon while a job goes to the bot and the bot's while it comes back. The tooltip and a screen-reader sentence are the full sentence; a request of yours still waiting for the next sync ends it with " · Sent at the next sync" and adds a small muted "Waiting" under the label (not "Queued", which is a saved job's status chip). The count includes status changes and take-overs, so it is only a note. With sync off no row has an owner and the column is not there; Role takes its room.
- Columns with fixed content (Match score, Status, Where, Applied, Next step, Added) are in rem, with `px-3` on head and cell, so their content always fits at the table's 57rem minimum; Role (`px-4`) takes the rest as a percentage. A row is always two lines, so every row is one height. "Work on it here" and "Keep it here" live in the row's menu (disabled only while its own request is in flight; a waiting request does not block it, since the server keeps one take-over per job).
- Row actions are one ghost icon button that appears at the row's end.
- A capped list says so at its end; a failed fetch is its own state, never the empty one.
- CompanyMonogram: a 32px disc with the company's initial, neutral for every company: `surface-container-highest` with `foreground`. The name picks no tone, so the base resume square is the only hue in a row and StatusChip stays the only place a state is coloured. It is decoration (`aria-hidden`); the name beside it carries the meaning.

Source: `frontend/components/ui/table.tsx`, `company-monogram.tsx`, `empty-state.tsx` (`TableFrame`). Changed from source: row hover `bg-muted/50` to `surface-container-low`; monogram palette pairs become one neutral fill.
