Filter chips narrow a list by one field when it has about six values or fewer, showing every choice and its count at once.

**You provide:** a label and a count per value, which values are on, and an `aria-label` for the group. Several chips can be on together.

- 28px tall, `radius-full`, `label-medium`, 8px apart; the count uses tabular numerals.
- Off: `border` outline, `muted-foreground` text. On: `secondary-container` / `on-secondary-container`, a leading Check, `aria-pressed="true"`.
- No chip on means no filter; do not add an "All" chip.
- A filter with more values than fit on one line stays a Select.

- **View chips** borrow the look (`filterChipClass`) for a row of presets where one is on at a time: Jobs' All active, Ready to apply, Waiting to hear, Interviews and Closed, each with its count. Pressing the chip that is on shows All, so these may lead with a preset that is not "no filter".

Source: `frontend/components/filter-chips.tsx`. Used for the Agent inbox's History statuses, and its look for Jobs' view chips. The Jobs status filter stays a Select behind **Filters** (FiltersButton): its eight application values (more with the agent lane) do not fit one toolbar row at 1024. The inbox's Sort and Minimum score are single-valued, and Role and Job board have too many values, so they stay Selects (the last three behind Filters).
