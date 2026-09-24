import assert from "node:assert/strict";
import { test } from "node:test";

import { NEEDS_YOU_STATUSES, needsYouBadge } from "./needs-you.ts";

test("the lane's statuses", () => {
  assert.deepEqual([...NEEDS_YOU_STATUSES], ["needs_decision", "needs_human"]);
});

test("hidden at zero and while unknown", () => {
  for (const n of [0, -1, 0.5, null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(needsYouBadge(n), null, String(n));
  }
});

test("one needs you, several need you", () => {
  assert.deepEqual(needsYouBadge(1), { text: "1", spoken: "1 needs you" });
  assert.deepEqual(needsYouBadge(3), { text: "3", spoken: "3 need you" });
});

test("past 99 the badge caps and the name keeps the real count", () => {
  assert.deepEqual(needsYouBadge(99), { text: "99", spoken: "99 need you" });
  assert.deepEqual(needsYouBadge(140), { text: "99+", spoken: "140 need you" });
});
