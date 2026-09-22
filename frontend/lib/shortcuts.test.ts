import assert from "node:assert/strict";
import { test } from "node:test";

import { modKeyFor, shortcutLabel } from "./shortcuts.ts";

test("Apple platforms get Command, everything else Control", () => {
  assert.equal(modKeyFor("MacIntel"), "⌘");
  assert.equal(modKeyFor("iPhone"), "⌘");
  assert.equal(modKeyFor("Win32"), "Ctrl");
  assert.equal(modKeyFor("Linux x86_64"), "Ctrl");
});

test("labels use each platform's own spelling", () => {
  assert.equal(shortcutLabel("⌘", "s"), "⌘S");
  assert.equal(shortcutLabel("Ctrl", "b"), "Ctrl+B");
});
