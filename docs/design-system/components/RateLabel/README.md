A rate label reads a share honestly (owner decision D7): a percent with its likely range from 20 in its denominator, the counts below.

**You provide:** the `value`, a `RateCount` from the server (`count`, `of`, and `rate`, `low`, `high`, null below 20), and optionally the denominator's noun as a pair, one and many (`["reply", "replies"]`).

- From 20 in `of`: "19%" with its Wilson 95% range in `body-small` `muted-foreground`, "(11–30%)".
- Below 20: "5 of 12", or "5 of 12 replies" with a noun, even when the server sends a rate (`MIN_RATE_N` in `lib/rates.ts` mirrors `services/rates.py`).
- With nothing to count (`of` is 0): "—".
- Tabular numbers.
- Every share on Analytics renders through it, so no other file reads `rate`, `low` or `high`. Where the words go into a cell and its title (Skills by role), call `rateWords` from `lib/rates.ts` directly; a cell below 20 sits on a plain fill, so its colour claims no share.

Source: `frontend/components/analytics/rate-label.tsx`, `frontend/lib/rates.ts`.
