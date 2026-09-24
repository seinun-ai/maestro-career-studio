import assert from "node:assert/strict";
import { test } from "node:test";

import { gapCounts } from "./gap-counts.ts";

test("answered, skipped and open add up to the gaps listed", () => {
  const counts = gapCounts(
    ["a", "b", "c", "d"],
    [
      { gap_id: "a", action: "add_keyword" },
      { gap_id: "b", action: "skip" },
      { gap_id: "c", action: "cannot_confirm" },
    ],
  );
  assert.deepEqual(counts, { answered: 1, skipped: 2, open: 1, total: 4 });
});

test("a resolution for a gap no longer listed counts for nothing", () => {
  assert.deepEqual(gapCounts(["a"], [{ gap_id: "gone", action: "user_input" }]), {
    answered: 0,
    skipped: 0,
    open: 1,
    total: 1,
  });
});
