import assert from "node:assert/strict";
import { test } from "node:test";

import { knockoutBanner, knockoutLine, knockoutWords } from "./knockout-line.ts";

test("the banner shows only when the scan blocks: a conflict or a missing profile answer", () => {
  assert.equal(knockoutBanner("conflict"), true);
  assert.equal(knockoutBanner("incomplete_profile"), true);
  assert.equal(knockoutBanner("clear"), false);
  assert.equal(knockoutBanner("unstated"), false);
});

test("a scan that blocks nothing is one line, never a card", () => {
  assert.deepEqual(knockoutLine("clear", false), { kind: "clear", label: "No knock-outs" });
  assert.deepEqual(knockoutLine("unstated", false), { kind: "unstated", label: "No requirements listed" });
  assert.deepEqual(knockoutLine("unstated", true), { kind: "not_run", label: "Checks not run yet" });
});

test("a scan that blocks has no line", () => {
  assert.equal(knockoutLine("conflict", false), null);
  assert.equal(knockoutLine("incomplete_profile", true), null);
});

test("the scan in a few words: the quiet line's label, or what the banner is about", () => {
  assert.equal(knockoutWords("clear", false), "No knock-outs");
  assert.equal(knockoutWords("conflict", false), "A knock-out");
  assert.equal(knockoutWords("incomplete_profile", true), "An answer missing from your profile");
  assert.equal(knockoutWords("unstated", false), "No requirements listed");
  assert.equal(knockoutWords("unstated", true), "Checks not run yet");
  assert.equal(knockoutWords(null, false), "Requirements not checked");
});
