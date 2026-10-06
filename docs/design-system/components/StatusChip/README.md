StatusChip is the only place an application's or a proposal's state is named and colored.

**You provide:** the status value. The chip supplies the label, the color role and the dot. `StatusChip` with `onSelect` is a menu that changes an application's status; `SavedJobChip` shows a saved job's agent state and is static.

| Application status | Label | Role |
| --- | --- | --- |
| no application yet | Saved | dashed `border`, `muted-foreground` |
| `draft` | Draft | `muted` / `muted-foreground` |
| `applied` | Applied | `primary-container` / `on-primary-container` |
| `interviewing` | Interviewing | `warning-container` / `on-warning-container` |
| `offered` | Offer | `tertiary-container` / `on-tertiary-container` |
| `accepted` | Offer accepted | `success-container` / `on-success-container` |
| `rejected` | Rejected | `error-container` / `on-error-container` |
| `withdrawn` | Withdrawn | `muted`, struck through |

| Proposal status | Label | Role |
| --- | --- | --- |
| `pending_review` | Proposed | `primary-container` / `on-primary-container` |
| `needs_decision`, `needs_human` | Needs you | `attention-container` / `on-attention-container` |
| `accepted` | Queued | `secondary-container` / `on-secondary-container` |
| `approved` | Approved | `success-container` / `on-success-container` |
| `submitted` | Applied | `success-container` / `on-success-container` |
| `submission_uncertain` | Check if sent | `attention-container` / `on-attention-container` |
| `rejected` | Skipped | `muted` / `muted-foreground` |
| `expired` | Expired | `muted` / `muted-foreground` |

- 24px tall, `radius-full`, `label-medium`. An application chip's 6px dot is the role itself (`bg-warning`, `bg-success`); a proposal chip's dot is its own text color at 40%.
- Every status also has a dot role for `StatusDot` and `LaneDot` (see StatusDot): Needs you and Check if sent `attention`, Proposed `primary`, Queued `on-secondary-container`, Approved and Applied `success`, Skipped and Expired `muted-foreground`.
- The label always carries the meaning; the color only repeats it.
- Needs you is `attention` (orange), never `warning`: Interviewing sits in the same column.
- An interactive chip shows a chevron, lifts with a shadow on hover and takes the solid `ring` outline on focus.
- Never write a status color at a call site, and never add a second label map.

Source: `frontend/components/status-chip.tsx`. The colors match the source. Changed from source: `label-medium` through the type scale and `shadow-level1` on hover.
