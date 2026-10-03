A card groups one subject: a setting, a chart, a resume.

**You provide:** a title, an optional one-sentence description, the content, and optionally a header action or a footer with the card's buttons.

- `card` on the page, `radius-corner-md`, 16px padding, 16px between its parts, and a 5% `foreground` ring that only sharpens the edge. The page and the card differ in tone, so the tone does the separating.
- Title in `title-medium`, description in `body-medium` `muted-foreground`.
- The footer is `surface-container-low` above a `border` hairline, with actions right-aligned.
- No shadow at rest. A card never nests in a card; use a `surface-container-low` panel inside.
- Every settings card renders through `SettingCard`, which adds the save model and spacing rhythm.

Source: `frontend/components/ui/card.tsx`. Changed from source: footer `bg-muted/50` to `surface-container-low`.
