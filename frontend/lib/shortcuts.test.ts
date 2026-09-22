import assert from "node:assert/strict";
import { test } from "node:test";

import { isSaveShortcut, modKeyFor, shortcutLabel } from "./shortcuts.ts";

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

test("Cmd+S and Ctrl+S save; with Shift or Alt they do not", () => {
  const key = (over: Partial<{ key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean }>) => ({
    key: "s",
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    ...over,
  });
  assert.equal(isSaveShortcut(key({ metaKey: true })), true);
  assert.equal(isSaveShortcut(key({ ctrlKey: true, key: "S" })), true);
  assert.equal(isSaveShortcut(key({ metaKey: true, shiftKey: true })), false);
  assert.equal(isSaveShortcut(key({ ctrlKey: true, altKey: true })), false);
  assert.equal(isSaveShortcut(key({})), false);
});
