The jobs table lists one job per row: who and what, which resume, its status and its dates.

**You provide:** the rows. Each needs a company, a role line, the base resume name or an em dash, a status, and dates. The company name is the row's link.

- A `radius-corner-md` frame with a `border`; rows divide with a `border` hairline and hover to `surface-container-low`.
- Header cells are 40px in `title-small`; the sorted column carries `aria-sort` and an arrow. In a long list the header sticks under the toolbar.
- Company in `title-small`, role line and metadata in `body-small` `muted-foreground`. An empty cell is an em dash.
- The Resume cell is a ResumeTag: the resume's color square, then its name in `foreground` (not muted), truncating at the cell. A saved job with no resume shows a muted em dash.
- Status is always a StatusChip. While the job is moving between copies the chip is locked (see StatusChip).
- Where is a narrow column after Status, with no sort. It appears only when some visible row has an owner: a muted icon and one word, "Laptop", "Bot" or "Moving" (a handover is on its way). The icon shows who holds the job now, so Moving keeps the laptop's icon while a job goes to the bot and the bot's while it comes back. The tooltip and a screen-reader sentence are the full sentence; a request of yours still waiting for the next sync ends it with " · Sent at the next sync" and adds a small muted "Waiting" under the label (not "Queued", which is a saved job's status chip). The count includes status changes and take-overs, so it is only a note. With sync off no row has an owner and the column is not there; Role and Resume share its room, 65/35 either way.
- Columns with fixed content (Match score, Status, Where, Applied, Added) are in rem, with `px-3` on head and cell, so their content always fits at the table's 52rem minimum; Role and Resume (`px-4`) share the rest as percentages. A row is always two lines, so every row is one height. "Work on it here" and "Keep it here" live in the row's menu (disabled only while its own request is in flight; a waiting request does not block it, since the server keeps one take-over per job).
- Row actions are one ghost icon button that appears at the row's end.
- A capped list says so at its end; a failed fetch is its own state, never the empty one.
- CompanyMonogram: a 32px disc with the company's initial, tinted by a hash of the name across four non-status tones (`primary-container`, `tertiary-container`, `secondary-container` and `surface-container-highest` with `foreground`). The status containers are not among them: StatusChip is the only place a state is coloured, and a monogram's tint is identity. It is decoration (`aria-hidden`); the name beside it carries the meaning.

Source: `frontend/components/ui/table.tsx`, `company-monogram.tsx`, `empty-state.tsx` (`TableFrame`). Changed from source: row hover `bg-muted/50` to `surface-container-low`; monogram palette pairs become four non-status tones.
