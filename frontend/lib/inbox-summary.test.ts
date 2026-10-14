import assert from "node:assert/strict";
import { test } from "node:test";

import { summaryParts } from "./inbox-summary.ts";

const none = { new: 0, queued: 0, needs_you: 0, applied_this_week: 0 };

test("the summary line names what needs you, what is queued and what went out this week", () => {
  assert.deepEqual(summaryParts({ ...none, needs_you: 2, queued: 3, applied_this_week: 5 }), [
    { key: "needs_you", text: "2 need you", anchor: "inbox-needs-you" },
    { key: "queued", text: "3 queued", anchor: "inbox-queued" },
    { key: "applied_this_week", text: "5 applied this week", anchor: "inbox-history" },
  ]);
});

test("a count of one reads as one", () => {
  assert.equal(summaryParts({ ...none, needs_you: 1 })[0].text, "1 needs you");
});

test("new shows first, only when something is new", () => {
  const parts = summaryParts({ ...none, new: 4, queued: 1 });
  assert.deepEqual(parts.map((p) => p.text), ["4 new", "1 queued"]);
  assert.equal(parts[0].anchor, "inbox-to-review");
});

test("zero parts are left out, and all zero is nothing", () => {
  assert.deepEqual(summaryParts({ ...none, queued: 3 }).map((p) => p.key), ["queued"]);
  assert.deepEqual(summaryParts(none), []);
});
