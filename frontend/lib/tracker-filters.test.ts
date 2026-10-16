import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveTrackerFilters, trackerHref } from "./tracker-filters.ts";

const FILTERS = ["all", "saved", "draft", "applied", "needs_you"];
const from = (entries: Record<string, string>) => (key: string) => entries[key] ?? null;
const nothing = from({});
const stored = from({ "cs-tracker-filter": "draft", "cs-tracker-stage": "gaps", "cs-tracker-source": "agent" });

test("with no filter in the URL, session memory restores all three", () => {
  assert.deepEqual(resolveTrackerFilters(nothing, stored, FILTERS), { filter: "draft", stage: "gaps", source: "agent" });
});

test("a URL with any one key is the whole state: the others take their defaults, not session memory", () => {
  assert.deepEqual(resolveTrackerFilters(from({ stage: "pdf_ready" }), stored, FILTERS), {
    filter: "all", stage: "pdf_ready", source: "all",
  });
  assert.deepEqual(resolveTrackerFilters(from({ source: "user" }), stored, FILTERS), {
    filter: "all", stage: null, source: "user",
  });
  assert.deepEqual(resolveTrackerFilters(from({ status: "applied" }), stored, FILTERS), {
    filter: "applied", stage: null, source: "all",
  });
});

test("unknown values fall back to their defaults", () => {
  const url = from({ status: "nope", stage: "applied", source: "everyone" });
  assert.deepEqual(resolveTrackerFilters(url, stored, FILTERS), { filter: "all", stage: null, source: "all" });
  const cleared = from({ "cs-tracker-stage": "" });
  assert.deepEqual(resolveTrackerFilters(nothing, cleared, FILTERS), { filter: "all", stage: null, source: "all" });
});

test("nothing anywhere is the plain list", () => {
  assert.deepEqual(resolveTrackerFilters(nothing, nothing, FILTERS), { filter: "all", stage: null, source: "all" });
});

test("the URL leaves defaults out and keeps the old key names", () => {
  assert.equal(trackerHref({ filter: "all", stage: null, source: "all" }), "/applications");
  assert.equal(
    trackerHref({ filter: "draft", stage: "tailored", source: "agent" }),
    "/applications?status=draft&stage=tailored&source=agent",
  );
});
