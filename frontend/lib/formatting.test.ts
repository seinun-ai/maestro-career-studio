import assert from "node:assert/strict";
import { test } from "node:test";

import {
  diffFrom,
  FORMATTING_DEFAULTS,
  type ResumeFormatting,
  SECTION_ORDER_FALLBACK,
  type SectionKey,
  shownSectionOrder,
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
