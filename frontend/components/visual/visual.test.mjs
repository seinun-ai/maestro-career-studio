// The day strip and the working dots say what they show. pytest runs it: backend/tests/test_frontend_motion.py.
import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement } from "../render-harness.mjs";

const { DayStrip } = load("components/visual/day-strip.tsx");
const { WorkingDots } = load("components/visual/working-dots.tsx");

test("the day strip's left end is the day of its oldest dot", () => {
  const today = new Date(2026, 9, 21);
  const html = renderElement(React.createElement(DayStrip, {
    runs: [{ finished_at: new Date(2026, 9, 8, 12).toISOString(), outcome: "ok" }], today,
  }));
  // 14 dots: today and the 13 days before it, the oldest (8 Oct) holding the one report.
  assert.equal([...html.matchAll(/size-3\.5 shrink-0 rounded-full/g)].length, 14);
  assert.match(html, /aria-label="Last 14 days: a report on 1 day, all done"/);
  assert.match(html, /<span>13 days ago<\/span><span>today<\/span>/);
  assert.doesNotMatch(html, /14 days ago/);
});

test("the working dots' live region is in the page before its words arrive", () => {
  const html = renderElement(React.createElement(WorkingDots, { label: "Writing your cover letter" }));
  // The region mounts empty and takes its words after (an effect): a status that arrives with its words
  // already inside is often not announced.
  assert.match(html, /<span role="status" class="sr-only"><\/span>/);
  // The words show at once, for the eye only; the region speaks them.
  assert.match(html, /<span aria-hidden="true">Writing your cover letter<\/span>/);
});
