Filter chips narrow a list by one field when it has about six values or fewer, showing every choice and its count at once.

**You provide:** a label and a count per value, which values are on, and an `aria-label` for the group. Several chips can be on together.

- 28px tall, `radius-full`, `label-medium`, 8px apart; the count uses tabular numerals.
- Off: `border` outline, `muted-foreground` text. On: `secondary-container` / `on-secondary-container`, a leading Check, `aria-pressed="true"`.
- No chip on means no filter; do not add an "All" chip.
- A filter with more values than fit on one line stays a Select.

New pattern, proposed for the Jobs status filter (today a "Status: All · 143" Select) and the Agent inbox filters. It applies the existing "selected in a set" rule; no source file yet.
