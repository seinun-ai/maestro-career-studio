import assert from "node:assert/strict";
import { test } from "node:test";

import { replaceEqualDeep } from "@tanstack/query-core";

import {
  actualSizeWidthPx,
  adoptServerKey,
  clampPreviewPct,
  emptyPreviewMessage,
  jsonDraftDiffers,
  keepIfEdited,
  nextPreviewPct,
  parsePreviewPct,
  parseZoom,
  PREVIEW_PCT,
  saveStatus,
  serverKey,
} from "./studio.ts";

const idle = { dirty: false, saving: false, rendering: false, rescoring: false };

test("a clean studio says everything is saved", () => {
  assert.deepEqual(saveStatus(idle), { label: "All changes saved", tone: "clean" });
});

test("unsaved edits are flagged", () => {
  assert.deepEqual(saveStatus({ ...idle, dirty: true }), {
    label: "Unsaved changes",
    tone: "dirty",
  });
});

test("a save in flight outranks the dirty flag it is clearing", () => {
  assert.deepEqual(saveStatus({ ...idle, dirty: true, saving: true }), {
    label: "Saving…",
    tone: "busy",
  });
});

test("edits made while a render or re-score runs read as unsaved", () => {
  assert.equal(saveStatus({ ...idle, dirty: true, rendering: true }).label, "Unsaved changes");
  assert.equal(saveStatus({ ...idle, dirty: true, rescoring: true }).label, "Unsaved changes");
});

test("render then re-score report in chain order", () => {
  assert.equal(saveStatus({ ...idle, rendering: true, rescoring: true }).label, "Rendering PDF…");
  assert.equal(saveStatus({ ...idle, rescoring: true }).label, "Re-scoring…");
});

test("an empty preview names Save only when there is something to save", () => {
  assert.equal(emptyPreviewMessage(true), "No PDF yet. Save to render one.");
  assert.equal(
    emptyPreviewMessage(false),
    "No PDF yet. Generate one from More resume actions (⋯).",
  );
});

test("ArrowLeft widens the preview, ArrowRight narrows it, within limits", () => {
  assert.equal(nextPreviewPct(45, "ArrowLeft"), 50);
  assert.equal(nextPreviewPct(45, "ArrowRight"), 40);
  assert.equal(nextPreviewPct(PREVIEW_PCT.max, "ArrowLeft"), PREVIEW_PCT.max);
  assert.equal(nextPreviewPct(PREVIEW_PCT.min, "ArrowRight"), PREVIEW_PCT.min);
});

test("arrow keys snap a dragged, fractional width to the step grid", () => {
  assert.equal(nextPreviewPct(47.38, "ArrowLeft"), 50);
  assert.equal(nextPreviewPct(47.38, "ArrowRight"), 45);
});

test("Home and End jump to the limits; other keys do nothing", () => {
  assert.equal(nextPreviewPct(45, "Home"), PREVIEW_PCT.max);
  assert.equal(nextPreviewPct(45, "End"), PREVIEW_PCT.min);
  assert.equal(nextPreviewPct(45, "Enter"), null);
});

test("an unknown or missing zoom falls back to fit width", () => {
  assert.equal(parseZoom(null), "width");
  assert.equal(parseZoom("bogus"), "width");
  assert.equal(parseZoom("page"), "page");
  assert.equal(parseZoom("actual"), "actual");
});

test("a 150-DPI Letter page is 816 CSS px at actual size", () => {
  assert.equal(actualSizeWidthPx(1275), 816);
});

test("serverKey ignores object key order at every depth", () => {
  assert.equal(
    serverKey({ a: 1, b: { c: 1, d: [{ e: 1, f: 2 }] } }),
    serverKey({ b: { d: [{ f: 2, e: 1 }], c: 1 }, a: 1 }),
  );
});

test("serverKey keeps array order", () => {
  assert.notEqual(serverKey([1, 2]), serverKey([2, 1]));
  assert.notEqual(serverKey({ xs: [{ a: 1 }, { a: 2 }] }), serverKey({ xs: [{ a: 2 }, { a: 1 }] }));
});

test("serverKey of a missing value is the empty key", () => {
  assert.equal(serverKey(null), "");
  assert.equal(serverKey(undefined), "");
});

test("serverKey matches a save response to its structurally shared refetch", () => {
  // The query cache keeps the OLD object (and its key order) for an unchanged
  // subtree, while the PATCH response arrives in schema order.
  const old = {
    contact: { name: "Ada", email: "ada@example.com" },
    experience: [{ title: "Engineer", company: "Acme" }],
    summary: "old",
  };
  const resp = {
    contact: { email: "ada@example.com", name: "Ada" },
    summary: "new",
    experience: [{ company: "Acme", title: "Engineer" }],
  };
  const shared = replaceEqualDeep(old, resp);
  assert.equal(shared.contact, old.contact);
  assert.notEqual(JSON.stringify(shared), JSON.stringify(resp));
  assert.equal(serverKey(shared), serverKey(resp));
});

const adoptIdle = { live: "A", adopted: "A", own: [] as string[], dirty: false, forced: null };

test("a formatting-only save arms nothing: a later foreign key over unsaved edits shows the banner", () => {
  // The save returned the key already adopted, so nothing was queued as ours;
  // its refetch changes nothing.
  const refetch = adoptServerKey({ ...adoptIdle, dirty: true });
  assert.deepEqual(refetch, { action: "none", own: [] });
  // A chat/MCP write lands while the user has unsaved edits.
  assert.deepEqual(adoptServerKey({ ...adoptIdle, live: "foreign", own: refetch.own, dirty: true }), {
    action: "banner",
    own: [],
  });
});

test("our own save's key moves the baseline in place and prunes the queue through it", () => {
  assert.deepEqual(
    adoptServerKey({ ...adoptIdle, live: "k2", own: ["k1", "k2", "k3"], dirty: true }),
    { action: "in-place", own: ["k3"] },
  );
});

test("two saves in one refetch window: the older lands first, the newer stays queued", () => {
  const first = adoptServerKey({ ...adoptIdle, live: "k1", own: ["k1", "k2"], dirty: true });
  assert.deepEqual(first, { action: "in-place", own: ["k2"] });
  assert.deepEqual(
    adoptServerKey({ ...adoptIdle, live: "k2", adopted: "k1", own: first.own, dirty: true }),
    { action: "in-place", own: [] },
  );
});

test("a foreign key over a clean editor remounts and clears the queue", () => {
  assert.deepEqual(adoptServerKey({ ...adoptIdle, live: "foreign", own: ["k1"] }), {
    action: "remount",
    own: [],
  });
});

test("a Rebuild the user confirmed remounts even over unsaved edits", () => {
  assert.deepEqual(
    adoptServerKey({ ...adoptIdle, live: "rebuilt", dirty: true, forced: "rebuilt" }),
    { action: "remount", own: [] },
  );
});

test("no server copy, or the adopted one, changes nothing", () => {
  assert.deepEqual(adoptServerKey({ ...adoptIdle, live: "", own: ["k1"], dirty: true }), {
    action: "none",
    own: ["k1"],
  });
  assert.deepEqual(adoptServerKey({ ...adoptIdle, own: ["k1"] }), { action: "none", own: ["k1"] });
});

test("keepIfEdited takes the saved copy only when nothing changed since the send", () => {
  const sent = { summary: "sent" };
  const saved = { summary: "normalized" };
  assert.equal(keepIfEdited({ summary: "sent" }, sent, saved), saved);
  const edited = { summary: "typed during the save" };
  assert.equal(keepIfEdited(edited, sent, saved), edited);
  assert.equal(keepIfEdited(null, null, saved), saved);
});

test("jsonDraftDiffers ignores whitespace and key order, not values or broken JSON", () => {
  const value = { contact: { name: "Ada", email: "ada@example.com" } };
  assert.equal(jsonDraftDiffers(JSON.stringify(value), value), false);
  assert.equal(jsonDraftDiffers(JSON.stringify(value, null, 2), value), false);
  assert.equal(
    jsonDraftDiffers('{"contact":{"email":"ada@example.com","name":"Ada"}}', value),
    false,
  );
  assert.equal(jsonDraftDiffers('{"contact":{"name":"Bea","email":"ada@example.com"}}', value), true);
  assert.equal(jsonDraftDiffers('{"contact":{"name":"Ada",', value), true);
});

test("clampPreviewPct clamps to the limits and rounds to 0.1", () => {
  assert.equal(clampPreviewPct(10), PREVIEW_PCT.min);
  assert.equal(clampPreviewPct(90), PREVIEW_PCT.max);
  assert.equal(clampPreviewPct(47.38), 47.4);
  assert.equal(clampPreviewPct(50), 50);
});

test("parsePreviewPct falls back to the default when absent, garbled or out of range", () => {
  for (const raw of [null, "", "abc", "24", "71"]) {
    assert.equal(parsePreviewPct(raw), PREVIEW_PCT.default, String(raw));
  }
  assert.equal(parsePreviewPct("50"), 50);
  assert.equal(parsePreviewPct("47.5"), 47.5);
});
