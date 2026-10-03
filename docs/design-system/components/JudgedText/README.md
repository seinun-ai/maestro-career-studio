Judged text is the resume wording a check is rating; it is shown exactly as written, as a quote.

**You provide:** the text, and `clamp` when the row should cut it to three lines with a Show all toggle. For a rewrite, pass the old and new wording to `DiffText`.

- The quote is upright `body-medium` in `foreground`, wrapped at 65 characters, behind a 2px `border` rule with 12px padding. It is never italic, grey or cut to one line.
- A clamped quote shows a visible Show all / Show less toggle with `aria-expanded`.
- The row around it: metadata in `body-small` `muted-foreground`, the bullet's question in `body-medium`, one text-style action and a "more" button. The row's edge is a plain `border`.
- In a diff, removed words are `error-container` / `on-error-container` struck through, added words are `success-container` / `on-success-container`.
- An edit is described, never printed raw.

Source: `frontend/components/resume-health/judged-text.tsx`, `finding-cards.tsx`. Changed from source: diff tints become role containers; the row edge loses its violet tint.
