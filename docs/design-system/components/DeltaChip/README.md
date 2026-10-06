A delta chip shows a signed change with its direction: "+6.2", "−1.4" or "0.0".

**You provide:** a numeric `value`; optionally a `prefix` ("up to") and a `unit` (default "points").

- 20px tall, `radius-full`, `surface-container`, `label-medium`, tabular numbers.
- The icon comes from the register: `increase` in `success`, `decrease` in `destructive`, `none` (a minus) in `muted-foreground` for no change. The sign is also in the text, so color only repeats it.
- The chip is one `role="img"` named "up to +6.2 points".

Source: `frontend/components/visual/delta-chip.tsx`.
