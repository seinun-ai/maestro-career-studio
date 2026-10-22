import assert from "node:assert/strict";
import { test } from "node:test";

import { assumedCurrencyLine, jobMetaLine, showsAssumedCurrency, showsOptLine, workModeUnlessSaid } from "./job-meta.ts";

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

test("a work mode the location already names drops out", () => {
  assert.equal(workModeUnlessSaid("Remote (United States)", "Remote"), null);
  assert.equal(workModeUnlessSaid("Denver, CO (Hybrid)", "Hybrid"), null);
  assert.equal(workModeUnlessSaid("Chicago, IL (on-site)", "On-site"), null, "case does not matter");
  assert.equal(workModeUnlessSaid("London, United Kingdom", "Hybrid"), "Hybrid");
  // A whole word only: a place that merely contains the letters keeps the mode.
  assert.equal(workModeUnlessSaid("Remoteville, OR", "Remote"), "Remote");
  assert.equal(workModeUnlessSaid(null, "Remote"), "Remote");
  assert.equal(workModeUnlessSaid("Remote", null), null);
});

test("OPT shows for a US job or a posting that says something about it", () => {
  assert.equal(showsOptLine("unstated", "US"), true);
  assert.equal(showsOptLine(null, "us"), true);
  // OPT is a US student permit: on a UK job an unstated line is noise.
  assert.equal(showsOptLine("unstated", "GB"), false);
  assert.equal(showsOptLine(null, null), false);
  // What the posting says always shows.
  assert.equal(showsOptLine("stem_opt_ok", "GB"), true);
  assert.equal(showsOptLine("no", null), true);
});
