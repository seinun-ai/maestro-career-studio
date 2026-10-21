import assert from "node:assert/strict";
import { test } from "node:test";

import { morphName } from "./view-transition.ts";

test("a pair is named from the job id, one name per part", () => {
  const id = "3f2a1b4c-0000-4000-8000-000000000001";
  assert.equal(morphName(id, "monogram"), `job-monogram-${id}`);
  assert.equal(morphName(id, "title"), `job-title-${id}`);
  assert.notEqual(morphName(id, "title"), morphName("another", "title"));
});

test("only identifier characters reach the name", () => {
  assert.equal(morphName("a b/c.d", "title"), "job-title-abcd");
});
