A segmented bar splits a whole into counted parts, such as a lane's jobs by state, with a legend that carries the text.

**You provide:** a `name` for the legend and `parts`, each with `key`, `label`, `count` and a `tone`: a status's role (`primary`, `muted`, `success`, `warning`, `attention`, `tertiary`, `error`), a chart series (`chart-1` to `chart-6`) for parts that are not a status, such as a work mode, or `empty` for a part with nothing stated.

- An 8px row, `radius-full`, `surface-container` behind it, 2px between segments sized by each part's share; a zero-count part draws no segment (the legend keeps it) and the `empty` tone gets a `border` outline on its legend swatch.
- The bar is decoration and is hidden from assistive tech. The legend under it is a list named by `name`: a swatch in the part's tone, then "3 Applied". A legend of statuses keys each part with an 8px round dot (round means status); a bar with any series keys every part with a short 12 by 8px bar, the segment's own shape.
- Tones are roles, never shades; use the role the same state wears in StatusChip. A series tone follows the thing it names, never its rank (Analytics' Work mode: hybrid `chart-1`, on-site `chart-2`, remote `chart-3`).

Source: `frontend/components/visual/segmented-bar.tsx`.
