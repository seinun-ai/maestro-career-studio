A status dot is a status's own 6px dot, for places that list statuses without the chip, such as filters and analytics.

**You provide:** `StatusDot` takes an application `status`; `LaneDot` takes a proposal status (Needs you, Proposed, Queued, Approved, Applied, Skipped and the rest).

- The dot is the status's role color, the same one its chip uses: attention, primary, on-secondary-container (Queued; the neutral `secondary` role has no contrast on these surfaces), success or muted. It is hidden from assistive tech, so the status word must be beside it.
- Both come from `status-chip.tsx`, so a status never gets a second color.

Source: `frontend/components/status-chip.tsx`.
