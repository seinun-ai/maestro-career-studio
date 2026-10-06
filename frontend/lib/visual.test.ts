import assert from "node:assert/strict";
import { test } from "node:test";

import { clampPct, formatDelta, meterLabel, segmentShares, sparkPath } from "./visual.ts";

test("clampPct keeps a share between 0 and 100", () => {
  assert.equal(clampPct(50), 50);
  assert.equal(clampPct(150), 100);
  assert.equal(clampPct(-3), 0);
  assert.equal(clampPct(3, 12), 25);
  assert.equal(clampPct(Number.NaN), 0);
  assert.equal(clampPct(1, 0), 0);
});

test("formatDelta signs a change and calls zero flat", () => {
  assert.deepEqual(formatDelta(6.24), { text: "+6.2", sign: "up" });
  assert.deepEqual(formatDelta(-1.36), { text: "−1.4", sign: "down" });
  assert.deepEqual(formatDelta(0.04), { text: "0.0", sign: "flat" });
});

test("meterLabel reads as a sentence", () => {
  assert.equal(meterLabel("Evidence", 3, 5, "Specific, no result"), "Evidence 3 of 5: Specific, no result");
});

test("segmentShares splits a whole and survives an empty one", () => {
  assert.deepEqual(segmentShares([{ key: "a", count: 3 }, { key: "b", count: 1 }]).map((s) => s.share), [75, 25]);
  assert.deepEqual(segmentShares([{ key: "a", count: 0 }]).map((s) => s.share), [0]);
});

test("sparkPath spans the box and handles flat and short series", () => {
  assert.equal(sparkPath([], 100, 20), "");
  assert.match(sparkPath([1, 1, 1], 100, 20), /^M0 10/);
  const d = sparkPath([0, 5, 10], 100, 20);
  assert.ok(d.startsWith("M0 20") && d.endsWith("100 0"));
});
