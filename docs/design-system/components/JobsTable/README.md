The jobs table lists one job per row: who and what, which resume, its status and its dates.

**You provide:** the rows. Each needs a company, a role line, the base resume name or an em dash, a status, and dates. The company name is the row's link.

- A `radius-corner-md` frame with a `border`; rows divide with a `border` hairline and hover to `surface-container-low`.
- Header cells are 40px in `title-small`; the sorted column carries `aria-sort` and an arrow. In a long list the header sticks under the toolbar.
- Company in `title-small`, role line and metadata in `body-small` `muted-foreground`. An empty cell is an em dash.
- Status is always a StatusChip. Row actions are one ghost icon button that appears at the row's end.
- A capped list says so at its end; a failed fetch is its own state, never the empty one.
- CompanyMonogram: a 32px disc with the company's initial, tinted by a hash of the name across four non-status tones (`primary-container`, `tertiary-container`, `secondary-container` and `surface-container-highest` with `foreground`). The status containers are not among them: StatusChip is the only place a state is coloured, and a monogram's tint is identity. It is decoration (`aria-hidden`); the name beside it carries the meaning.

Source: `frontend/components/ui/table.tsx`, `company-monogram.tsx`, `empty-state.tsx` (`TableFrame`). Changed from source: row hover `bg-muted/50` to `surface-container-low`; monogram palette pairs become four non-status tones.
