import assert from "node:assert/strict";
import { test } from "node:test";

import { NEEDS_YOU_STATUSES } from "./needs-you.ts";

test("the lane's statuses", () => {
  assert.deepEqual([...NEEDS_YOU_STATUSES], ["needs_decision", "needs_human"]);
});
