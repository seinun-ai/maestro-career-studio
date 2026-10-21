import assert from "node:assert/strict";
import { test } from "node:test";

import { TRACKER_VIEWS, VIEW_FILTERS, resolveTrackerFilters, trackerHref, viewOf } from "./tracker-filters.ts";

const FILTERS = ["all", "active", "interviews", "closed", "saved", "draft", "applied", "needs_you"];
const from = (entries: Record<string, string>) => (key: string) => entries[key] ?? null;
const nothing = from({});
const stored = from({ "cs-tracker-filter": "draft", "cs-tracker-stage": "gaps", "cs-tracker-source": "agent" });

test("with no filter in the URL, session memory restores all three", () => {
  assert.deepEqual(resolveTrackerFilters(nothing, stored, FILTERS), { filter: "draft", stage: "gaps", source: "agent" });
});

test("a URL with any one key is the whole state: the others take their defaults, not session memory", () => {
  assert.deepEqual(resolveTrackerFilters(from({ stage: "pdf_ready" }), stored, FILTERS), {
    filter: "active", stage: "pdf_ready", source: "all",
  });
  assert.deepEqual(resolveTrackerFilters(from({ source: "user" }), stored, FILTERS), {
    filter: "active", stage: null, source: "user",
  });
  assert.deepEqual(resolveTrackerFilters(from({ status: "applied" }), stored, FILTERS), {
    filter: "applied", stage: null, source: "all",
  });
});

test("unknown values fall back to their defaults", () => {
  const url = from({ status: "nope", stage: "applied", source: "everyone" });
  assert.deepEqual(resolveTrackerFilters(url, stored, FILTERS), { filter: "active", stage: null, source: "all" });
  const cleared = from({ "cs-tracker-stage": "" });
  assert.deepEqual(resolveTrackerFilters(nothing, cleared, FILTERS), { filter: "active", stage: null, source: "all" });
});

test("nothing anywhere is the plain list: every active job", () => {
  assert.deepEqual(resolveTrackerFilters(nothing, nothing, FILTERS), { filter: "active", stage: null, source: "all" });
});

test("the URL leaves defaults out and keeps the old key names", () => {
  assert.equal(trackerHref({ filter: "active", stage: null, source: "all" }), "/applications");
  // Everything, closed jobs too, is no longer the default, so it is written.
  assert.equal(trackerHref({ filter: "all", stage: null, source: "all" }), "/applications?status=all");
  assert.equal(
    trackerHref({ filter: "draft", stage: "tailored", source: "agent" }),
    "/applications?status=draft&stage=tailored&source=agent",
  );
});

test("each chip is one preset, and a state names at most one chip", () => {
  for (const view of TRACKER_VIEWS) assert.equal(viewOf(VIEW_FILTERS[view]), view);
  assert.equal(viewOf({ filter: "active", stage: null }), "active");
  assert.equal(viewOf({ filter: "active", stage: "pdf_ready" }), "ready");
  // Filters can set what no chip names.
  assert.equal(viewOf({ filter: "all", stage: null }), null);
  assert.equal(viewOf({ filter: "draft", stage: null }), null);
  assert.equal(viewOf({ filter: "applied", stage: "gaps" }), null);
});

test("a chip's preset survives the URL and session memory", () => {
  const ready = VIEW_FILTERS.ready;
  const href = trackerHref({ ...ready, source: "all" });
  assert.equal(href, "/applications?stage=pdf_ready");
  const params = new URL(href, "http://x").searchParams;
  assert.deepEqual(resolveTrackerFilters((k) => params.get(k), nothing, FILTERS), { ...ready, source: "all" });
});
