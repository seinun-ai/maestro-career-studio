import assert from "node:assert/strict";
import { test } from "node:test";

import { countryName, placeName } from "./place-name.ts";

test("a state or province code reads as its name", () => {
  assert.equal(placeName("CA"), "California");
  assert.equal(placeName("ON"), "Ontario");
});

test("a country-only key says so, and a city stays as written", () => {
  assert.equal(placeName("US"), "United States (no city)");
  assert.equal(placeName("Remote"), "Remote");
  assert.equal(placeName("San Francisco"), "San Francisco");
});

test("a country code reads as its name", () => {
  assert.equal(countryName("GB"), "United Kingdom");
  assert.equal(countryName("unknown"), "unknown");
});
