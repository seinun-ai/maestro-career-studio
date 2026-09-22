import assert from "node:assert/strict";
import { test } from "node:test";

import {
  diffFrom,
  FORMATTING_DEFAULTS,
  type FormattingBaseline,
  overlayBaseline,
  type ResumeFormatting,
  SECTION_ORDER_FALLBACK,
  type SectionKey,
  shownSectionOrder,
  unloadedLayer,
} from "./formatting.ts";

// An explicit, non-fallback order (Harshibar-like: certifications standalone).
const L: SectionKey[] = ["summary", "experience", "education", "skills", "projects", "certifications"];
const withL: ResumeFormatting = { ...FORMATTING_DEFAULTS, section_order: L };

test("a null section order shows the fallback list; an explicit one shows itself", () => {
  assert.deepEqual(shownSectionOrder(null), SECTION_ORDER_FALLBACK);
  assert.deepEqual(shownSectionOrder(undefined), SECTION_ORDER_FALLBACK);
  assert.deepEqual(shownSectionOrder(L), L);
});

test("moving a section down and back up stores nothing over an inherited order", () => {
  assert.equal(
    diffFrom(FORMATTING_DEFAULTS, { ...FORMATTING_DEFAULTS, section_order: [...SECTION_ORDER_FALLBACK] }),
    null,
  );
});

test("a moved list is stored as an override", () => {
  const moved: SectionKey[] = ["summary", "projects", "experience", "extra_sections", "skills", "education"];
  assert.deepEqual(diffFrom(FORMATTING_DEFAULTS, { ...FORMATTING_DEFAULTS, section_order: moved }), {
    section_order: moved,
  });
});

test("returning to an explicit baseline order stores nothing", () => {
  assert.equal(diffFrom(withL, { ...withL, section_order: [...L] }), null);
});

test("the fallback order over an explicit baseline is a genuine override", () => {
  assert.deepEqual(diffFrom(withL, { ...withL, section_order: [...SECTION_ORDER_FALLBACK] }), {
    section_order: SECTION_ORDER_FALLBACK,
  });
});

test("a null section order over a null baseline stores nothing", () => {
  assert.equal(diffFrom(FORMATTING_DEFAULTS, { ...FORMATTING_DEFAULTS, section_order: null }), null);
});

test("a non-order knob still diffs", () => {
  assert.deepEqual(diffFrom(FORMATTING_DEFAULTS, { ...FORMATTING_DEFAULTS, font_size: 12 }), {
    font_size: 12,
  });
});

// --- Baseline readiness: a knob is diffed only against a COMPLETE baseline ---

const templateLayer: FormattingBaseline = {
  status: "ready",
  values: { ...FORMATTING_DEFAULTS, font_size: 11 },
  supportedKeys: ["font_size"],
};
const pending = { data: undefined, isError: false, isFetching: true, refetch: () => {} };

test("a layer with no data is loading until its query fails, then an error with a retry", () => {
  assert.deepEqual(unloadedLayer(pending, "the template defaults"), {
    status: "loading",
    what: "the template defaults",
  });
  let refetched = 0;
  const failed = unloadedLayer(
    { isError: true, isFetching: false, refetch: () => refetched++ },
    "the template defaults",
  );
  assert.equal(failed.status, "error");
  if (failed.status !== "error") return;
  assert.equal(failed.retrying, false);
  failed.retry();
  assert.equal(refetched, 1);
});

test("the base layer in flight keeps the baseline loading, so no edit is diffed against the template alone", () => {
  assert.equal(overlayBaseline(templateLayer, pending, "the base resume's formatting").status, "loading");
});

test("a failed layer is an error, whichever layer failed and whatever the other is doing", () => {
  const failed = { ...pending, isError: true, isFetching: false };
  assert.equal(overlayBaseline(templateLayer, failed, "base").status, "error");
  assert.equal(overlayBaseline({ status: "loading", what: "t" }, failed, "base").status, "error");
  const templateFailed = unloadedLayer({ ...failed }, "the template defaults");
  const both = overlayBaseline(templateFailed, { ...pending, data: { formatting: null } }, "base");
  assert.equal(both.status, "error");
  if (both.status === "error") assert.equal(both.what, "the template defaults");
});

test("a stored override equal to the template layer survives once the base layer is in", () => {
  // The application stores font_size 11 over a base of 10 (template: 11).
  const base = { ...pending, isFetching: false, data: { formatting: { font_size: 10 } } };
  const full = overlayBaseline(templateLayer, base, "base");
  assert.equal(full.status, "ready");
  if (full.status !== "ready") return;
  assert.equal(full.values.font_size, 10);
  assert.deepEqual(full.supportedKeys, ["font_size"]);
  // A later knob edit keeps the explicit 11; against the template layer alone it vanished.
  const edited = { ...full.values, font_size: 11 as const, justify: true };
  assert.deepEqual(diffFrom(full.values, edited), { font_size: 11, justify: true });
  assert.deepEqual(diffFrom(templateLayer.values, edited), { justify: true });
});

test("data already held stays ready through a failed background refetch", () => {
  const stale = { data: { formatting: null }, isError: true, isFetching: false, refetch: () => {} };
  assert.equal(overlayBaseline(templateLayer, stale, "base").status, "ready");
});
