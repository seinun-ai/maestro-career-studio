import assert from "node:assert/strict";
import { test } from "node:test";

import {
  contactAdditions,
  hasFillableContactDetails,
  parseContactLocation,
  resumeContactCandidates,
} from "./contact-from-history.ts";

test("a location reads as city and state, with a country when it has three parts", () => {
  assert.deepEqual(parseContactLocation("Austin, TX"), { city: "Austin", state: "TX" });
  assert.deepEqual(parseContactLocation("Austin, TX, USA"), { city: "Austin", state: "TX", country: "USA" });
  assert.equal(parseContactLocation("Berlin"), null);
  assert.equal(parseContactLocation("Berlin, Germany"), null, "a second part that is not a state is not read");
  assert.equal(parseContactLocation(null), null);
});

test("the name splits into first and last, and blank answers are left out", () => {
  assert.deepEqual(resumeContactCandidates({ name: "Ada  King Lovelace", email: " ada@example.com ", phone: "" }), [
    ["first_name", "Ada"],
    ["last_name", "King Lovelace"],
    ["email", "ada@example.com"],
  ]);
  assert.equal(hasFillableContactDetails({}), false);
  assert.equal(hasFillableContactDetails(undefined), false);
});

test("a fill adds only to blank fields, never over an answer you gave", () => {
  const contact = { name: "Ada Lovelace", email: "ada@example.com", phone: "+44 20 0000 0000" };
  assert.deepEqual(contactAdditions({ email: "mine@example.com", phone: "  " }, contact), {
    first_name: "Ada",
    last_name: "Lovelace",
    phone: "+44 20 0000 0000",
  });
  assert.deepEqual(contactAdditions({ first_name: "A", last_name: "L", email: "e", phone: "p" }, contact), {});
});
