The filters button is the one control a list's rarer filters sit behind: it opens their row in place and says how many are on.

**You provide:** `open`, `onToggle`, the `controls` id of the row it opens (hide that row while closed), and `active`, how many of the filters behind it are on.

- A `ghost` small button with a 16px `SlidersHorizontal` icon, reading "Filters", or "Filters · 2" while two of its filters are on, in tabular numbers. A filter set from a link or an earlier visit is never hidden without a word.
- A real disclosure: `aria-expanded` and `aria-controls`.
- The frequent choice stays in view (Jobs' five view chips, the inbox's search and sort); what is rare goes behind it (Jobs: the status, the stage and Tracked / Yours / Agents; the Agent inbox: Role, Job board and Minimum score).
- The count leaves out a filter a chip already names, so it never counts the same choice twice.

Source: `frontend/components/filters-button.tsx`.
