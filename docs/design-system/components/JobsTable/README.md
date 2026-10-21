The jobs table lists one job per row: what and where, its match score, its status and its next step.

**You provide:** the rows. Each needs a role title, a company and place line, a status, the applied date and `status_since` (when the current status began, from the status log) when the server has them, and the server's stage. The row is the link to the job.

- A `radius-corner-md` frame with a `border`; rows divide with a `border` hairline and hover to `surface-container-low`. A row carries `group/row`, so its NextStep fills on hover.
- Five columns: Role, Match, Status, Next step and a 32px slot. There is no Resume column (a resume is picked after a job is saved), no Where column and no Applied or Added column; sorting by added or applied stays in the sort menu, and the sorted column carries `aria-sort`.
- Header cells are 40px in `title-small`. In a long list the header sticks under the toolbar.
- Role: a CompanyMonogram, the title in `title-small`, then "Company · Place" in `body-small` `muted-foreground`. A row is always two lines, so every row is one height. An empty cell is an em dash.
- Match is a ScoreBar and its number; its accessible name and its hover name the application's resume.
- Status is always a StatusChip with one date beside it: Applied shows the date you applied, any other status the day it began ("Since", from `status_since`, in its title and a screen-reader word), and a status older than the log the applied date, never a guess. While the job is moving between copies the chip is locked (see StatusChip).
- Next step is a NextStep: your move a blue text link with a chevron ("Apply", "Continue gaps · 2 of 5"), grey text while you wait ("Waiting to hear back"), nothing once applied further or closed. Never a button, never filled.
- The 32px slot holds `JobOwnershipPopover`, the Agent inbox's ownership icon, only when the job is not on this copy or a request of yours waits for the next sync; its pop-up says why the job is locked and offers Work on it here or Keep it here. Otherwise the slot holds the row's ⋯ (Queue in Agent inbox, Delete), shown on hover.
- Columns with fixed content (Match, Status, Next step) are in rem, with `px-3` on head and cell, so their content always fits at the table's 57rem minimum; Role takes the rest.
- Select mode, the Agent inbox's: a quiet Select puts a checkbox on every row and a "Select all shown" in the header, a row's click picks it, and the bar at the bottom (`SelectionBar`) offers only what every picked row's own controls allow.
- A capped list says so at its end; a failed fetch is its own state, never the empty one.
- CompanyMonogram: a 32px disc with the company's initial, neutral for every company: `surface-container-highest` with `foreground`. The name picks no tone, so the base resume square is the only hue on a page and StatusChip stays the only place a state is coloured. It is decoration (`aria-hidden`); the name beside it carries the meaning.

Source: `frontend/app/applications/page.tsx`, `frontend/components/ui/table.tsx`, `company-monogram.tsx`, `empty-state.tsx` (`TableFrame`). Changed from source: row hover `bg-muted/50` to `surface-container-low`; monogram palette pairs become one neutral fill.
