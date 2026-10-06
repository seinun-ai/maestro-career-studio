import assert from "node:assert/strict";
import { test } from "node:test";

import { easeOutCubic, valueAt } from "./count-up.ts";

test("the ease starts at 0, ends at 1 and never overshoots", () => {
  assert.equal(easeOutCubic(0), 0);
  assert.equal(easeOutCubic(1), 1);
  for (let t = 0; t <= 1; t += 0.05) assert.ok(easeOutCubic(t) <= 1);
});

test("valueAt interpolates and clamps time", () => {
  assert.equal(valueAt(10, 20, 0), 10);
  assert.equal(valueAt(10, 20, 1), 20);
  assert.equal(valueAt(10, 20, 2), 20);
  assert.ok(valueAt(10, 20, 0.5) > 15);
});
