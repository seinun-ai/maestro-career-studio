import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_ROLE_SERIES, splitTopRoles } from "./analytics-series.ts";

test("ranks roles by summed weight and breaks ties by key ascending", () => {
  const rows = [
    { role: "b", n: 1 },
    { role: "a", n: 2 },
    { role: "b", n: 3 },
    { role: "c", n: 4 },
  ];
  const { shown, hidden } = splitTopRoles(
    rows,
    (row) => row.role,
    (row) => row.n,
    2,
  );
  assert.deepEqual(shown, ["b", "c"]);
  assert.deepEqual(hidden, ["a"]);
  assert.ok(shown.length <= 2);
});

test("the default cap is four roles and the rest are hidden", () => {
  const rows = ["a", "b", "c", "d", "e"].map((role, index) => ({
    role,
    n: 5 - index,
  }));
  const { shown, hidden } = splitTopRoles(
    rows,
    (row) => row.role,
    (row) => row.n,
  );
  assert.equal(MAX_ROLE_SERIES, 4);
  assert.deepEqual(shown, ["a", "b", "c", "d"]);
  assert.deepEqual(hidden, ["e"]);
  assert.ok(shown.length <= MAX_ROLE_SERIES);
});

test("hidden is empty when every role fits", () => {
  const rows = [
    { role: "a", n: 1 },
    { role: "b", n: 2 },
  ];
  const { shown, hidden } = splitTopRoles(
    rows,
    (row) => row.role,
    (row) => row.n,
    5,
  );
  assert.deepEqual(shown, ["b", "a"]);
  assert.deepEqual(hidden, []);
});
