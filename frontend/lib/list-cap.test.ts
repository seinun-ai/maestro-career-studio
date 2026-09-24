import assert from "node:assert/strict";
import { test } from "node:test";

import { isListCapped, listCapSentence } from "./list-cap.ts";

test("without a total, a full page reads as capped", () => {
  assert.equal(isListCapped({ loaded: 500, limit: 500, noun: "applications" }), true);
  assert.equal(isListCapped({ loaded: 499, limit: 500, noun: "applications" }), false);
  assert.equal(isListCapped({ loaded: 0, limit: 500, noun: "applications" }), false);
});

test("a server total makes the check exact", () => {
  assert.equal(isListCapped({ loaded: 500, limit: 500, noun: "proposals", total: 500 }), false);
  assert.equal(isListCapped({ loaded: 500, limit: 500, noun: "proposals", total: 812 }), true);
  assert.equal(isListCapped({ loaded: 12, limit: 500, noun: "proposals", total: 12 }), false);
  assert.equal(isListCapped({ loaded: 12, limit: 500, noun: "proposals", total: null }), false);
});

test("the sentence names what is loaded, not what is shown", () => {
  assert.equal(
    listCapSentence({ loaded: 500, limit: 500, noun: "applications" }),
    "Only your 500 most recent applications are loaded, so older ones don't appear in this list.",
  );
  assert.equal(
    listCapSentence({ loaded: 500, limit: 500, noun: "proposals", total: 1234 }),
    "Only the 500 most recent of your 1,234 proposals are loaded, so older ones don't appear in this list.",
  );
  assert.equal(listCapSentence({ loaded: 20, limit: 500, noun: "applications" }), null);
});

test("a list that comes oldest first says the newer ones are missing", () => {
  assert.equal(
    listCapSentence({ loaded: 500, limit: 500, noun: "draft bullets", order: "oldest" }),
    "Only your 500 oldest draft bullets are loaded, so newer ones don't appear in this list.",
  );
  assert.equal(
    listCapSentence({ loaded: 500, limit: 500, noun: "drafts", total: 640, order: "oldest" }),
    "Only the 500 oldest of your 640 drafts are loaded, so newer ones don't appear in this list.",
  );
});
