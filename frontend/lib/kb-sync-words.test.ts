import assert from "node:assert/strict";
import { test } from "node:test";

import { syncActionableCount, syncBreakdownLines, syncPillLabel, syncResultSentence } from "./kb-sync-words.ts";
import type { SyncResult, SyncStatus } from "./types.ts";

const result = (over: Partial<SyncResult>): SyncResult => ({
  created: 0,
  items_added: 0,
  drifted: 0,
  skipped: [],
  skills: [],
  skills_added: [],
  last_kb_synced_at: null,
  ...over,
});

test("an add of items and skills never says it added 0 bullets", () => {
  const words = syncResultSentence(result({ items_added: 2, skills_added: ["Go", "SQL", "AWS"] }));
  assert.equal(words, "Added 2 items and 3 skills to your career history.");
  assert.doesNotMatch(words, /0 /);
});

test("every count the server returns is said, in agreement", () => {
  assert.equal(
    syncResultSentence(result({ created: 6, items_added: 1, skills_added: ["Go"], drifted: 2 })),
    "Added 6 draft bullets, 1 item and 1 skill to your career history. Noted 2 wording changes.",
  );
  assert.equal(syncResultSentence(result({ drifted: 1 })), "Noted 1 wording change.");
  assert.equal(
    syncResultSentence(result({})),
    "Nothing new to add. Your career history already has all of this.",
  );
});

const status = (items: [string, string][], counts: Partial<SyncStatus["counts"]>): SyncStatus => ({
  items: items.map(([tier, section]) => ({ tier, section, text: "x" }) as SyncStatus["items"][number]),
  skills_new: [],
  counts: { in_sync: 0, drift: 0, recorded_drift: 0, new: 0, skills_new: 0, ...counts },
  last_kb_synced_at: null,
});

test("the breakdown names each section and adds up to the pill's number", () => {
  const s = status(
    [
      ...Array.from({ length: 6 }, () => ["new", "experience"] as [string, string]),
      ...Array.from({ length: 3 }, () => ["new", "projects"] as [string, string]),
      ["drift", "experience"],
    ],
    { new: 9, drift: 1, skills_new: 5, recorded_drift: 4 },
  );
  assert.deepEqual(syncBreakdownLines(s), [
    "6 experience bullets",
    "3 project bullets",
    "5 skills",
    "1 reworded bullet (we'll note the change)",
  ]);
  assert.equal(syncActionableCount(s), 15);
});

test("the pill says the number as words: what gets added, and where", () => {
  assert.equal(syncPillLabel(14), "Add 14 things to career history");
  assert.equal(syncPillLabel(1), "Add 1 thing to career history");
});
