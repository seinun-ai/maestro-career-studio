A segmented toggle switches between two or three views of the same list or chart.

**You provide:** two or three one-word options, the current value, and an `aria-label` for the group saying what it switches.

- A 32px `radius-full` outline holding 28px pills in `label-medium`.
- The selected option is `secondary-container` / `on-secondary-container` with a leading Check and `aria-pressed="true"`. The tonal fill is only about 1.16:1 against the light page, so the Check carries the state.
- Unselected options are `muted-foreground` and hover to `surface-container`.
- Use it for view switches only (Tracked / Yours / Agents, Day / Week). Sections of a page are Tabs; a filter with counts is FilterChips.

Source: `frontend/components/source-toggle.tsx`.
