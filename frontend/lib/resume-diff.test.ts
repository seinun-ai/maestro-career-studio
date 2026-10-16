import assert from "node:assert/strict";
import { test } from "node:test";

import { diffIsCurrent, hunkIds, hunkPlace } from "./resume-diff.ts";
import type { ResumeDiffHunk } from "./types.ts";

const hunk = (over: Partial<ResumeDiffHunk>): ResumeDiffHunk => ({
  kind: "bullet_added",
  section: "experience",
  index: 0,
  before: null,
  after: "Built a pipeline",
  provenance: "llm",
  ...over,
});

test("a change's place names its section, the item a bullet belongs to, and what happened", () => {
  const draft = { experience: [{ company: "Seinun LLC", role: "Data scientist" }], projects: [{ name: "Maestro" }] };
  assert.equal(hunkPlace(hunk({}), draft), "Experience · Seinun LLC · Bullet added");
  assert.equal(hunkPlace(hunk({ section: "projects", kind: "bullet_edited" }), draft), "Projects · Maestro · Bullet reworded");
  // No item for a summary, an entry hunk (its text names it) or a certification (a flat list).
  assert.equal(hunkPlace(hunk({ kind: "summary_changed", section: "summary", index: null }), draft), "Summary · Summary rewritten");
  assert.equal(hunkPlace(hunk({ kind: "entry_added" }), draft), "Experience · Item added");
  assert.equal(hunkPlace(hunk({ section: "certifications" }), draft), "Certifications · Bullet added");
  // An index past the list, or no draft: the section and the kind only.
  assert.equal(hunkPlace(hunk({ index: 5 }), draft), "Experience · Bullet added");
  assert.equal(hunkPlace(hunk({}), null), "Experience · Bullet added");
});

test("a change's id ignores its position, so the rows after a reverted one keep theirs", () => {
  const a = hunk({ after: "One" });
  const b = hunk({ after: "Two" });
  const c = hunk({ kind: "summary_changed", section: "summary", index: null, before: "Old", after: "New" });
  const [, idB, idC] = hunkIds([a, b, c]);
  assert.deepEqual(hunkIds([b, c]), [idB, idC]);
  assert.equal(new Set(hunkIds([a, b, c])).size, 3);
  // The same change twice: two ids, by their order among themselves.
  const twice = hunkIds([a, a]);
  assert.notEqual(twice[0], twice[1]);
  assert.equal(twice[1], `${twice[0]}#1`);
});

test("a revert waits for a diff fetched after the draft it edits", () => {
  assert.equal(diffIsCurrent(2000, 1000), true);
  assert.equal(diffIsCurrent(1000, 1000), true);
  assert.equal(diffIsCurrent(999, 1000), false);
  assert.equal(diffIsCurrent(0, 0), false);
});
