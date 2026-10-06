import assert from "node:assert/strict";
import { test } from "node:test";

import { emailWarning, phoneWarning, linkWarning } from "./field-checks.ts";

test("an email warns only when its shape is off", () => {
  assert.equal(emailWarning(""), null);
  assert.equal(emailWarning("sam@example.com"), null);
  assert.match(emailWarning("sam.example.com") ?? "", /email address/);
  assert.match(emailWarning("sam@example") ?? "", /email address/);
});

test("a phone warns under seven digits", () => {
  assert.equal(phoneWarning(""), null);
  assert.equal(phoneWarning("+1 (972) 555-0100"), null);
  assert.match(phoneWarning("555-01") ?? "", /digits/);
});

test("a link warns when it is not a web address", () => {
  assert.equal(linkWarning(""), null);
  assert.equal(linkWarning("linkedin.com/in/sam"), null);
  assert.equal(linkWarning("https://github.com/sam"), null);
  assert.match(linkWarning("sam rivera") ?? "", /web address/);
});
