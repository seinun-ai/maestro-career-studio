import assert from "node:assert/strict";
import { test } from "node:test";

import { capNearLimit, inboxCounts } from "./inbox-summary.ts";

const none = { new: 0, ready: 0, to_review: 0, queued: 0, needs_you: 0, applied_this_week: 0 };

test("the header counts what waits for review, what is queued and what went out this week, in that order", () => {
  assert.deepEqual(inboxCounts({ ...none, needs_you: 2, to_review: 4, queued: 3, applied_this_week: 5 }), [
    { key: "to_review", value: 4, label: "to review", anchor: "inbox-to-review" },
    { key: "queued", value: 3, label: "queued", anchor: "inbox-queued" },
    { key: "applied_this_week", value: 5, label: "applied this week", anchor: "inbox-history" },
  ]);
});

test("a zero is kept: the header holds its shape", () => {
  assert.deepEqual(inboxCounts(none).map((c) => c.value), [0, 0, 0]);
});

test("the daily limit shows only at 80 percent used or more", () => {
  assert.equal(capNearLimit(0, 10), false);
  assert.equal(capNearLimit(7, 10), false);
  assert.equal(capNearLimit(8, 10), true);
  assert.equal(capNearLimit(10, 10), true);
  assert.equal(capNearLimit(12, 10), true);
  assert.equal(capNearLimit(3, 4), false);
  assert.equal(capNearLimit(4, 5), true);
});

test("a limit of none left is always worth saying", () => {
  assert.equal(capNearLimit(0, 0), true);
});
