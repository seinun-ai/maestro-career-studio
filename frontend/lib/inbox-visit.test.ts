import assert from "node:assert/strict";
import { test } from "node:test";

import { createVisitClock } from "./inbox-visit.ts";

const KEY = "cs-inbox-last-visit";
const NOW = Date.parse("2026-10-05T12:00:00.000Z");

const cases = [
  ["a saved visit", "2026-10-03T09:30:00.000Z", false, false, "2026-10-03T09:30:00.000Z"],
  ["missing storage", null, false, false, "2026-10-04T12:00:00.000Z"],
  ["an invalid date", "not a date", false, false, "2026-10-04T12:00:00.000Z"],
  ["an empty date", "", false, false, "2026-10-04T12:00:00.000Z"],
  ["a whitespace date", "   ", false, false, "2026-10-04T12:00:00.000Z"],
  ["a blocked read and write", "2026-10-03T09:30:00.000Z", true, true, "2026-10-04T12:00:00.000Z"],
  ["a blocked read", "2026-10-03T09:30:00.000Z", true, false, "2026-10-04T12:00:00.000Z"],
  ["a blocked write", "2026-10-03T09:30:00.000Z", false, true, "2026-10-03T09:30:00.000Z"],
] as const;

function makeStorage(initial: string | null, readFails: boolean, writeFails: boolean) {
  const counts = { reads: 0, writes: 0, value: initial };
  return {
    counts,
    storage: {
      getItem(key: string) {
        assert.equal(key, KEY);
        counts.reads++;
        if (readFails) throw new Error("read blocked");
        return counts.value;
      },
      setItem(key: string, value: string) {
        assert.equal(key, KEY);
        counts.writes++;
        if (writeFails) throw new Error("write blocked");
        counts.value = value;
      },
    },
  };
}

for (const [name, initial, readFails, writeFails, expected] of cases) {
  test("resolves " + name + " and reuses it without storage access", () => {
    const { counts, storage } = makeStorage(initial, readFails, writeFails);
    const clock = createVisitClock();

    assert.equal(clock.resolve(storage, NOW), expected);
    assert.equal(counts.reads, 1);
    assert.equal(counts.writes, 1);
    if (!writeFails) assert.equal(counts.value, new Date(NOW).toISOString());

    assert.equal(clock.resolve(storage, NOW + 60 * 60 * 1000), expected);
    assert.equal(counts.reads, 1);
    assert.equal(counts.writes, 1);
  });
}

test("a new clock reads the stored visit again after reload", () => {
  const { counts, storage } = makeStorage("2026-10-03T09:30:00.000Z", false, false);
  const beforeReload = createVisitClock();
  assert.equal(beforeReload.resolve(storage, NOW), "2026-10-03T09:30:00.000Z");

  const afterReload = createVisitClock();
  assert.equal(afterReload.resolve(storage, NOW + 60 * 60 * 1000), new Date(NOW).toISOString());
  assert.equal(counts.reads, 2);
  assert.equal(counts.writes, 2);
});
