import assert from "node:assert/strict";
import { test } from "node:test";

import { chipCount } from "./tracker-counts.ts";

const rows = [
  { filterKey: "draft", stage: "pdf_ready" },
  { filterKey: "draft", stage: "tailored" },
  { filterKey: "draft", stage: "pdf_ready" },
  { filterKey: "saved", stage: "gaps" },
  { filterKey: "needs_you", stage: "gaps" },
  { filterKey: "needs_you", stage: "scored" },
  { filterKey: "applied", stage: "applied" },
  { filterKey: "saved" }, // a backend without the stage
];
const none = { filter: "all", stage: null };

test("with nothing on, a stage chip counts every row on that stage", () => {
  assert.equal(chipCount(rows, none, { stage: "pdf_ready" }), 2);
  assert.equal(chipCount(rows, none, { stage: "gaps" }), 2);
  assert.equal(chipCount(rows, none, { stage: "tailored" }), 1);
});

test("a stage chip counts within the Status filter it ANDs with", () => {
  assert.equal(chipCount(rows, { filter: "saved", stage: null }, { stage: "gaps" }), 1);
  assert.equal(chipCount(rows, { filter: "applied", stage: null }, { stage: "pdf_ready" }), 0);
});

test("a stage chip that is on counts the rows it shows, not the other chip's", () => {
  assert.equal(chipCount(rows, { filter: "all", stage: "pdf_ready" }, { stage: "pdf_ready" }), 2);
  assert.equal(chipCount(rows, { filter: "all", stage: "pdf_ready" }, { stage: "gaps" }), 2);
});

test("Needs you replaces the Status filter and keeps the stage chip", () => {
  assert.equal(chipCount(rows, none, { filter: "needs_you" }), 2);
  assert.equal(chipCount(rows, { filter: "draft", stage: null }, { filter: "needs_you" }), 2);
  assert.equal(chipCount(rows, { filter: "all", stage: "gaps" }, { filter: "needs_you" }), 1);
});

test("a row without a stage counts for no stage chip", () => {
  assert.equal(chipCount([{ filterKey: "saved" }], none, { stage: "gaps" }), 0);
  assert.equal(chipCount([{ filterKey: "saved" }], none, { filter: "saved" }), 1);
});
