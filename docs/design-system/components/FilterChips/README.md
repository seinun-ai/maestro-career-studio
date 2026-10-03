Filter chips narrow a list by one field when it has about six values or fewer, showing every choice and its count at once.

**You provide:** a label and a count per value, which values are on, and an `aria-label` for the group. Several chips can be on together.

- 28px tall, `radius-full`, `label-medium`, 8px apart; the count uses tabular numerals.
- Off: `border` outline, `muted-foreground` text. On: `secondary-container` / `on-secondary-container`, a leading Check, `aria-pressed="true"`.
- No chip on means no filter; do not add an "All" chip.
- A filter with more values than fit on one line stays a Select.

Source: `frontend/components/filter-chips.tsx`. Used for the Agent inbox's History statuses. The Jobs status filter stays a Select: its eight application values (more with the agent lane) take about 770px, and the toolbar row is 720px at 1024 and 976px at 1280, of which about 500px and 760px are free beside the Tracked / Yours / Agents toggle. The inbox's Sort and Minimum score are single-valued, and Role and Job board have too many values, so they stay Selects.
