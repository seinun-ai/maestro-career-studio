A stat tile shows one number with what it counts and what it is out of.

**You provide:** a `label` (what is counted), a `value`, and an optional `sub` line that gives the denominator or the period.

- A filled tile: `surface-container-low`, `radius-corner-md`, 16px padding, no border and no shadow.
- Label and sub line in `body-small` `muted-foreground`; the value in `title-large` at weight 500.
- Put three to five tiles in one row with a 12px gap.
- A number alone is not a stat: always say what it is of ("of your 52 applications").

Source: `frontend/components/analytics/stat-tile.tsx`.
