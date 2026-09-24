import assert from "node:assert/strict";
import { test } from "node:test";

import { jobMetaLine } from "./job-meta.ts";

test("empty parts and Not stated drop out", () => {
  assert.equal(jobMetaLine(["Acme", null, "Not stated", "", "Senior"]), "Acme · Senior");
});

test("a repeated part shows once, whatever its case", () => {
  assert.equal(jobMetaLine(["Remote", "remote", "$150K"]), "Remote · $150K");
});
