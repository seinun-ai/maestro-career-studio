A hint tip keeps the rest of a section's explanation one hover or focus away: an Info button beside a title or a label, the sentence in its tooltip.

**You provide:** a `label` for the button ("About notes"), the sentence as `children`, and optionally an `id` so a field can name the sentence in its own `aria-describedby`.

- A `ghost` extra-small icon button in `muted-foreground` with a 14px `Info`; the tooltip holds the sentence.
- The same sentence is the button's description, held in a hidden span, so a screen reader hears it without the tooltip.
- For an explanation that need not be seen before acting. A consequence that must be seen first stays a visible line ("Nothing goes on a resume until you approve it.", "You can't undo this.").
- One short sentence, like any hint; never a placeholder's job and never a label's.

Source: `frontend/components/hint-tip.tsx`. The gap page's "About these suggestions" is the same pattern.
