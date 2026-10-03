An empty state fills a list or panel that has nothing in it yet and offers the first step.

**You provide:** a `title` saying what is empty, an optional one-sentence `description` saying what adding one does, an optional Lucide `icon`, and an optional `action`.

- A dashed `border` box at `radius-corner-md` with 64px vertical padding, centered.
- Icon 32px at 50% `muted-foreground`; title in `title-small`; description in `body-medium` `muted-foreground`.
- The action is a `tonal` button, never filled: the page's filled button is elsewhere.
- Empty is not failed. A fetch that failed renders `LoadErrorState` with a retry, never this.

Source: `frontend/components/empty-state.tsx`.
