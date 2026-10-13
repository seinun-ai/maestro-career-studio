The jobs table lists one job per row: who and what, which resume, its status and its dates.

**You provide:** the rows. Each needs a company, a role line, the base resume name or an em dash, a status, and dates. The company name is the row's link.

- A `radius-corner-md` frame with a `border`; rows divide with a `border` hairline and hover to `surface-container-low`.
- Header cells are 40px in `title-small`; the sorted column carries `aria-sort` and an arrow. In a long list the header sticks under the toolbar.
- Company in `title-small`, role line and metadata in `body-small` `muted-foreground`. An empty cell is an em dash.
- The Resume cell is a ResumeTag: the resume's color square, then its name in `foreground` (not muted), truncating at the cell. A saved job with no resume shows a muted em dash.
- Status is always a StatusChip. When the job is on the other copy and the chip cannot change, its chevron becomes a lock and the reason is its tooltip.
- Where is a narrow column after Status, with no sort. It appears only when some row's job has an owner: a muted icon (laptop, or the agent glyph for the bot) and one word, "Laptop", "Bot" or "Moving" (a handover is on its way). The tooltip is the full sentence. With sync off no row has an owner and the column is not there; Role takes its width. "Work on it here" and "Keep it here" live in the row's menu, not in the row. A row is always two lines, so every row is one height.
- Row actions are one ghost icon button that appears at the row's end.
- A capped list says so at its end; a failed fetch is its own state, never the empty one.
- CompanyMonogram: a 32px disc with the company's initial, tinted by a hash of the name across four non-status tones (`primary-container`, `tertiary-container`, `secondary-container` and `surface-container-highest` with `foreground`). The status containers are not among them: StatusChip is the only place a state is coloured, and a monogram's tint is identity. It is decoration (`aria-hidden`); the name beside it carries the meaning.

Source: `frontend/components/ui/table.tsx`, `company-monogram.tsx`, `empty-state.tsx` (`TableFrame`). Changed from source: row hover `bg-muted/50` to `surface-container-low`; monogram palette pairs become four non-status tones.
