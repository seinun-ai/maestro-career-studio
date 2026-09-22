import assert from "node:assert/strict";
import { test } from "node:test";

import {
  actualSizeWidthPx,
  nextPreviewPct,
  parseZoom,
  PREVIEW_PCT,
  saveStatus,
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
