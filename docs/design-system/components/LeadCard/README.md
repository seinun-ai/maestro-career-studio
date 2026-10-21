A lead card is the Lead tier: the one thing that matters most on a page, such as Next up on Today or Ready to apply on a job page.

**You provide:** an `eyebrow` (a few words), the content as `children`, and optionally one `action` (a `label`, an optional `icon`, `disabled`, and either `href` (with `external` for a page outside the app, and an `onClick` that may cancel it) or `onClick` with `pending`), `secondary`, `footer`, `media` and an `aside`.

- A `radius-corner-lg` section on `card` with `p-7` and `shadow-level1`: the one resting card that floats a little.
- The eyebrow is `label-medium` in `primary` and names the section (`aria-labelledby`).
- `action` is the view's one filled button (`default`, size `lg`), under the content. Nothing else on the page is filled. A disabled action stays focusable, and a disabled link refuses the press too.
- `secondary` sits beside the action: quieter controls you draw (outline at size `lg`, a link, a ⋯), never filled. `footer` goes under the button row, for the lead's own rows (the job page's Cover letter and Application questions).
- `media` is a picture before the content at its own width (the job page's tailored resume page). The aside sits on `surface-container-low` with `radius-corner-md` and `p-5`, after the content (`flex: 1 1 420px` and `0 1 300px`). Both wrap under the content when the card is narrow.
- One per page, at the top.

Source: `frontend/components/ui/lead-card.tsx`.
