Every page opens with one PageHeader inside one PageShell: the title, a one-clause subtitle, and the page's actions on the right.

**You provide:** `title`, an optional `subtitle` (prose or nodes such as a save-status line), optional `actions`, and an optional `leading` back button.

- Title is an `<h1>` in `title-large` at weight 500; subtitle is `body-medium` `muted-foreground`.
- Actions sit right while they share the title's line and drop under the title, left-aligned, when they wrap.
- At most one filled button among the actions; the rest are `outline` or `ghost`.
- The page owns `<main>`; `PageShell` gives it the 72rem measure, 24px padding and 24px between sections.
- A page title is the page's canonical name (Jobs, Career history, Agent inbox), never a variant.

Source: `frontend/components/page-shell.tsx`.
