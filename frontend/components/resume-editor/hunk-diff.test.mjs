// A change in Review changes drawn as a diff (components/resume-editor/hunk-diff.tsx; the runs are
// lib/word-diff.ts `lineDiff`, node-tested in lib/word-diff.test.ts).
// pytest runs it: backend/tests/test_frontend_resume_review.py.
import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement } from "../render-harness.mjs";

const { HunkDiff, DIFF_LINE, DIFF_WORD } = load("components/resume-editor/hunk-diff.tsx");

const render = (before, after) => renderElement(React.createElement(HunkDiff, { before, after, className: "text-body-small" }));
/** The words drawn on a kind's full container, in order. */
const marked = (html, kind) => [...html.matchAll(new RegExp(`<span class="rounded-corner-2xs ${DIFF_WORD[kind]}">([^<]*)</span>`, "g"))].map((m) => m[1]);

test("a reworded line marks only the words that changed, each on its own side", () => {
  const html = render("Built Power BI and Excel KPI dashboards", "Built Power BI KPI dashboards for six apps");
  assert.deepEqual(marked(html, "removed"), ["and Excel"]);
  assert.deepEqual(marked(html, "added"), ["for six apps"]);
  // The old line on its red wash in <del>, the new on its green in <ins>, said in words too.
  assert.ok(html.indexOf("<del") < html.indexOf("<ins"));
  assert.match(html, new RegExp(`<p class="rounded-corner-xs px-1.5 py-0.5 ${DIFF_LINE.removed} text-body-small"><del class="no-underline"><span class="sr-only">Before: </span>`));
  assert.match(html, new RegExp(`<p class="rounded-corner-xs px-1.5 py-0.5 ${DIFF_LINE.added} text-body-small"><ins class="no-underline"><span class="sr-only">Now: </span>`));
});

test("items added to a skills group are the only marked words", () => {
  const html = render("Data & Cloud: AWS, Snowflake", "Data & Cloud: AWS, Snowflake, Power Automate");
  assert.deepEqual(marked(html, "removed"), []);
  assert.deepEqual(marked(html, "added"), [", Power Automate"]);
});

test("an entry added or removed whole is one marked line, with no other side", () => {
  const added = render("", "Led the migration to AWS");
  assert.deepEqual(marked(added, "added"), ["Led the migration to AWS"]);
  assert.ok(!added.includes("<del") && !added.includes("Before: "));
  const removed = render("Led the migration to AWS", "");
  assert.deepEqual(marked(removed, "removed"), ["Led the migration to AWS"]);
  assert.ok(!removed.includes("<ins") && !removed.includes("Now: "));
});
