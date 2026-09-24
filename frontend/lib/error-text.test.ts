import assert from "node:assert/strict";
import { test } from "node:test";

import { couldnt, errorDetail, isPlainSentence } from "./error-text.ts";

test("a plain sentence passes; code, JSON and fragments do not", () => {
  assert.equal(isPlainSentence("This resume no longer exists."), true);
  assert.equal(isPlainSentence("Maestro CS isn't responding. Check that it's running, then try again."), true);
  assert.equal(isPlainSentence("slug must be lowercase alphanumeric with underscores"), false);
  assert.equal(isPlainSentence('[{"loc":["body","title"],"msg":"field required"}]'), false);
  assert.equal(isPlainSentence("experience.2.bullets.0: String must contain at least 1 character(s)"), false);
  assert.equal(isPlainSentence("Application not found"), false);
  assert.equal(isPlainSentence("Upstream fetch failed (http://127.0.0.1:8001): fetch failed"), false);
  assert.equal(isPlainSentence(`${"A".repeat(240)}.`), false);
});

test("couldnt names what failed, then the plain detail or Try again", () => {
  assert.equal(
    couldnt("save the resume", new Error("A section with this name already exists.")),
    "Couldn't save the resume. A section with this name already exists.",
  );
  assert.equal(couldnt("save the resume", new Error("Request failed: 500")), "Couldn't save the resume. Try again.");
  assert.equal(couldnt("save the resume", "boom"), "Couldn't save the resume. Try again.");
});

test("errorDetail hides what is not for the user", () => {
  assert.equal(errorDetail(new Error("Target entity not found")), undefined);
  assert.equal(errorDetail(new Error("  This job was deleted.  ")), "This job was deleted.");
  assert.equal(errorDetail(null), undefined);
});
