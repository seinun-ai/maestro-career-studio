Select mode picks rows in a list, then acts on them, as in Photos: a quiet **Select** turns it on, a bar at the bottom offers what fits, and **Done** turns it off. Jobs and the Agent inbox share it.

**You provide:** for `SelectToggle`, whether the list is `selecting` and its `onClick`. For `SelectionBar`, the `selectedCount`, the actions as `children`, `nothingFits` and its `hint` (what to pick instead when no action fits every picked row), `pending` while an action runs, and `onDone`.

- `SelectToggle` is a `ghost` small button reading **Select**, then **Done**. With it on, every row shows a checkbox, a "Select all" sits on the list (per lane, per day in To review), and a click on a row picks it instead of opening it; a row's own buttons step aside.
- `SelectionBar` is fixed to the bottom on `background` at 95% with a blur (a bar that floats over scrolling content), a hairline on top, sliding in over `--duration-short4` with `ease-emphasized-decelerate`. It says "3 selected" (a polite `role="status"`, tabular numbers), or "Pick the jobs to act on" before a pick.
- **Offer only what every picked row's own controls offer**, under the same ownership locks (`bulkActionsOf`). No bulk endpoint exists, so each action sends the row's own request one row at a time; a Delete asks once.
- At most one filled action (the Agent inbox's Queue); Jobs' Change status, Queue in Agent inbox and Delete are all quieter.
- Done sits beside the actions, not at the far end, where toasts land. While an action runs, Done waits, focusable and dimmed. The bar's action, or Done, ends the mode and hands focus back to Select.
- `globals.css` keeps a focused row clear of the bar (`data-slot="bulk-bar"`).

Source: `frontend/components/selection-bar.tsx`; the bars in `frontend/app/applications/job-bulk.tsx` and `frontend/components/proposals/triage-actions.tsx`.
