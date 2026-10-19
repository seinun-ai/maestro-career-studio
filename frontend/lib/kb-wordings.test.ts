import assert from "node:assert/strict";
import { test } from "node:test";

import { splitRequest, visibleClaims, wordingActions, wordingsChip } from "./kb-wordings.ts";
import type { KBPointOut, KBWordingOut } from "./types.ts";

const w = (over: Partial<KBWordingOut>): KBWordingOut => ({
  kind: "resume", text: "x", resume_keys: ["hybrid"], section: "experience", point_id: null,
  adoptable: true, splittable: true, ...over,
});

test("the chip counts wordings and is absent at zero", () => {
  assert.equal(wordingsChip([]), null);
  assert.equal(wordingsChip([w({})]), "1 wording");
  assert.equal(wordingsChip([w({}), w({ kind: "merged", text: "y" })]), "2 wordings");
});

test("each kind gets its actions: adopt and split, adopt only, or the hint", () => {
  assert.deepEqual(wordingActions(w({ kind: "resume" })), { adopt: true, split: true, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "merged", point_id: "p2" })), { adopt: true, split: true, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "import", adoptable: true, splittable: false })), { adopt: true, split: false, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "placed", adoptable: false, splittable: false })), {
    adopt: false, split: false, hint: "Add to a resume to update it",
  });
});

test("a Not used bullet offers no split; adopting still works", () => {
  assert.deepEqual(wordingActions(w({ kind: "resume" }), { retired: true }), { adopt: true, split: false, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "merged", point_id: "p2" }), { retired: false }), { adopt: true, split: true, hint: null });
});

test("split sends the right request per kind", () => {
  assert.deepEqual(splitRequest("p1", w({ kind: "resume", text: "T", resume_keys: ["hybrid"] })), {
    kind: "split-wording", pointId: "p1", text: "T", resumeKey: null,
  });
  assert.deepEqual(splitRequest("p1", w({ kind: "merged", point_id: "p2" })), {
    kind: "unmerge", pointId: "p2",
  });
  assert.equal(splitRequest("p1", w({ kind: "placed", splittable: false })), null);
  // A merged row without a point to bring back splits its words off like a resume wording.
  assert.deepEqual(splitRequest("p1", w({ kind: "merged", text: "M", point_id: null })), {
    kind: "split-wording", pointId: "p1", text: "M", resumeKey: null,
  });
});

test("a combined bullet is hidden from the list; it shows under its keeper", () => {
  const points = [
    { id: "a", state: "approved", merged_into_point_id: null },
    { id: "b", state: "retired", merged_into_point_id: "a" },
    { id: "c", state: "retired", merged_into_point_id: null },
  ] as unknown as KBPointOut[];
  assert.deepEqual(visibleClaims(points).map((p) => p.id), ["a", "c"]);
});
