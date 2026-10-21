A lead card is the Lead tier: the one thing that matters most on a page, such as Next up on Today or Ready to apply on a job page.

**You provide:** an `eyebrow` (a few words), the content as `children`, and optionally one `action` (a `label`, an optional `icon`, and either `href` or `onClick` with `pending`) and an `aside`.

- A `radius-corner-lg` section on `card` with `p-7` and `shadow-level1`: the one resting card that floats a little.
- The eyebrow is `label-medium` in `primary` and names the section (`aria-labelledby`).
- `action` is the view's one filled button (`default`, size `lg`), under the content. Nothing else on the page is filled.
- The aside sits on `surface-container-low` with `radius-corner-md` and `p-5`, beside the content (`flex: 1 1 420px` and `0 1 300px`), and wraps under it when the card is narrow.
- One per page, at the top.

Source: `frontend/components/ui/lead-card.tsx`.
