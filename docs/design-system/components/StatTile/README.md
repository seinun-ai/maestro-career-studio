A stat tile shows one number with what it counts and what it is out of.

**You provide:** a `label` (what is counted), a `value`, and an optional `sub` line that gives the denominator or the period, and an optional `icon` beside the label (only a glyph that already means that tile's thing; decorative, the label names it).

- A filled tile: `surface-container-low`, `radius-corner-md`, 16px padding, no border and no shadow.
- Label and sub line in `body-small` `muted-foreground`; the value in `title-large` at weight 500.
- Put three to five tiles in one row with a 12px gap. Every tile in a row is the same width and the value is the same size in each.
- A long value, such as a pay range, wraps after its dash. Never shrink one tile's value or widen one tile to keep it on a line.
- A number alone is not a stat: always say what it is of ("of your 52 applications").

Source: `frontend/components/analytics/stat-tile.tsx`.
