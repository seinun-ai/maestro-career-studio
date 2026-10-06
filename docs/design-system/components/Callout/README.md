A callout states one thing about the whole page or section: a note, a pass, a caution or a blocker.

**You provide:** a short title, one or two sentences, a Lucide icon, and the kind. A callout may hold one text-style action.

| Kind | Look | Use for |
| --- | --- | --- |
| Note | `primary` at 25% border, 4% fill, `foreground` text | A neutral pointer (Drafts to review) |
| Pass | `success-container` / `on-success-container` | A check that passed (Stated requirements clear) |
| Caution | `warning-container` / `on-warning-container` | Something to look at (No numbers anywhere) |
| Blocker | `destructive` at 50% border, 5% fill, `destructive` title, `foreground` body | A must-fix gate |

- `radius-corner-md`, 16px side padding, title in `title-small`, body in `body-small`, wrapped at 65 characters.
- The icon and the title say the kind; color only repeats it.
- A callout is not a toast: it stays while the condition holds.
- Do not stack more than two; fold the rest into the list below.

Source: callouts in `frontend/components/**` (`border-primary/25 bg-primary/[0.04]`, the amber and emerald tinted boxes, the fatal gate). Changed from source: amber and emerald tints become role containers.
