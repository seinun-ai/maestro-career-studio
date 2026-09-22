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
  const key = (over: Partial<{ key: string; code: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean }>) => ({
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

test("a non-Latin layout saves by the S key's position", () => {
  const cyrillic = { key: "ы", code: "KeyS", altKey: false, shiftKey: false };
  assert.equal(isSaveShortcut({ ...cyrillic, metaKey: true, ctrlKey: false }), true);
  assert.equal(isSaveShortcut({ ...cyrillic, metaKey: false, ctrlKey: true }), true);
  assert.equal(isSaveShortcut({ ...cyrillic, metaKey: false, ctrlKey: false }), false);
});

test("a Latin layout that moves S keeps the letter, not the position", () => {
  // Colemak types "r" and Dvorak "o" on the KeyS position: Cmd+R must still
  // reload and Cmd+O still open, never save.
  const base = { code: "KeyS", metaKey: true, ctrlKey: false, altKey: false, shiftKey: false };
  assert.equal(isSaveShortcut({ ...base, key: "r" }), false);
  assert.equal(isSaveShortcut({ ...base, key: "o" }), false);
});
