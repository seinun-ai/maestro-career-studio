Buttons run an action; the variant says how much it matters, and a view has exactly one filled button.

**You provide:** the label (sentence case, starts with a verb, a canonical term from the glossary), a `variant`, a `size`, and optionally one leading Lucide icon. An icon-only button needs an `aria-label`.

| Variant | Colors | Use for |
| --- | --- | --- |
| `default` | `primary` / `primary-foreground` | The one main action in a view or a dialog (Save job, Start the questions) |
| `tonal` | `secondary-container` / `on-secondary-container` | A create or secondary action (Add item, See all skill gaps); also "selected in a set" |
| `fab` | `primary-container` / `on-primary-container` | Add job in the sidebar, and nothing else |
| `outline` | `border` on `background` | Neutral actions beside a filled one, a retry (Try again) |
| `ghost` | no container | Row and toolbar actions |
| `destructive` | `destructive` text on a 10% tint | Delete, remove |
| `link` | `primary` text | An action that reads as a link inside prose |

| Size | Height | Label style |
| --- | --- | --- |
| `xs` | 24px | `label-medium` |
| `sm` | 28px | `label-medium` |
| `default` | 32px | `label-large` |
| `lg` | 36px (the FAB is 40px) | `label-large` |

- Corners are `radius-corner-sm`; the FAB is `radius-corner-lg`.
- Hover on `tonal` and `fab` is the pre-mixed 8% state layer (`secondary-container-hover`, `primary-container-hover`); never pick an opacity at the call site.
- `pending` marks a button whose own request is running: a spinner replaces the leading icon, `aria-busy` is set, presses are ignored and focus stays (a natively disabled button drops it to the page). Name the work in the label where it is worth naming ("Saving…", "Updating scores…", "Approving…", "Writing…"); otherwise keep the label and let the spinner say it. `disabled` stays for a button that cannot act yet, with the reason tied by `aria-describedby`.
- Focus is a solid `ring` border with a 3px halo. Pressing scales the button to 0.97.
- `tonal` is the one low-emphasis filled button. There is no grey `secondary` variant; Badge keeps its own `secondary` for plain metadata.
- `tonal` rests on `background`, `card` or a `surface-container-*` panel. On a `secondary-container` surface (a current row, a selected chip) it would vanish, so use `outline` there.
- Do not put two filled buttons in one view. A modal's confirm is filled because the modal is a view of its own.

Source: `frontend/components/ui/button.tsx`. Changed from source: `sm` label 12.8px to 12px, type through the scale.
