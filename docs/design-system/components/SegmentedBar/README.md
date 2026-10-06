A segmented bar splits a whole into counted parts, such as a lane's jobs by state, with a legend that carries the text.

**You provide:** a `name` for the legend and `parts`, each with `key`, `label`, `count` and a `tone` (`primary`, `muted`, `success`, `warning`, `attention`, `tertiary`, `error` or `empty`).

- An 8px row, `radius-full`, `surface-container` behind it, 2px between segments sized by each part's share; a zero-count part draws no segment (the legend keeps it) and the `empty` tone gets a `border` outline on its legend swatch.
- The bar is decoration and is hidden from assistive tech. The legend under it is a list named by `name`: an 8px swatch in the part's role, then "3 Applied".
- Tones are roles, never shades; use the role the same state wears in StatusChip.

Source: `frontend/components/visual/segmented-bar.tsx`.
