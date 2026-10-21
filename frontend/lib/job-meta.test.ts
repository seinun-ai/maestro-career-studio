import assert from "node:assert/strict";
import { test } from "node:test";

import { assumedCurrencyLine, jobMetaLine } from "./job-meta.ts";

test("empty parts and Not stated drop out", () => {
  assert.equal(jobMetaLine(["Acme", null, "Not stated", "", "Senior"]), "Acme · Senior");
});

test("a repeated part shows once, whatever its case", () => {
  assert.equal(jobMetaLine(["Remote", "remote", "$150K"]), "Remote · $150K");
});

test("a currency the post did not state says what it was read as, and why", () => {
  assert.equal(assumedCurrencyLine("CAD", "Canada"), "Pay read as Canadian dollars, job is in Canada");
  assert.equal(assumedCurrencyLine("EUR", null), "Pay read as euros, your home currency");
  // A code Intl does not know reads as written, never as a guess.
  assert.equal(assumedCurrencyLine("XYZ", "Narnia"), "Pay read as XYZ, job is in Narnia");
});
