import assert from "node:assert/strict";
import { test } from "node:test";

import { assumedCurrencyLine, jobMetaLine, showsAssumedCurrency } from "./job-meta.ts";

test("empty parts and Not stated drop out", () => {
  assert.equal(jobMetaLine(["Acme", null, "Not stated", "", "Senior"]), "Acme · Senior");
});

test("a repeated part shows once, whatever its case", () => {
  assert.equal(jobMetaLine(["Remote", "remote", "$150K"]), "Remote · $150K");
});

test("a currency the post did not state says what it was read as, and why", () => {
  assert.equal(assumedCurrencyLine("CAD", "Canada"), "Pay read as Canadian dollars, job is in Canada");
  // A code Intl does not know reads as written, never as a guess.
  assert.equal(assumedCurrencyLine("XYZ", "Narnia"), "Pay read as XYZ, job is in Narnia");
});

test("the read-as line shows only for a job in another country than where you live", () => {
  assert.equal(showsAssumedCurrency("CA", "US"), true);
  assert.equal(showsAssumedCurrency("ca", "CA"), false, "case does not matter");
  // No job country: the pay was read as your own currency, nothing to explain.
  assert.equal(showsAssumedCurrency(null, "US"), false);
  assert.equal(showsAssumedCurrency(undefined, "US"), false);
  // A home market with no country: any named job country is elsewhere.
  assert.equal(showsAssumedCurrency("DE", null), true);
  // Where you live not loaded yet: nothing, so the line never flashes in and out.
  assert.equal(showsAssumedCurrency("DE", undefined), false);
});
