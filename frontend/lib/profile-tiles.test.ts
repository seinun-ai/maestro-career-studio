import assert from "node:assert/strict";
import { test } from "node:test";

import { PROFILE_FOLDS, PROFILE_TILES, cardId, sectionForAnchor } from "./profile-tiles.ts";

test("every anchor the Autofill tab and About you rendered still opens its home", () => {
  const cases: [string, ReturnType<typeof sectionForAnchor>][] = [
    ["autofill-personal", { kind: "tile", id: "contact" }],
    ["autofill-work_auth", { kind: "tile", id: "permits" }],
    ["autofill-preferences", { kind: "tile", id: "start" }],
    ["autofill-eeo", { kind: "fold", id: "diversity" }],
    ["autofill-eligibility", { kind: "fold", id: "eligibility" }],
    ["persona", { kind: "tile", id: "persona" }],
    ["market", { kind: "tile", id: "where" }],
    ["job-preferences", { kind: "tile", id: "jobs" }],
    // An id inside a card, by prefix: the knock-out card's years link.
    ["job-preferences-years", { kind: "tile", id: "jobs" }],
    ["af-eeo-gender", { kind: "fold", id: "diversity" }],
  ];
  for (const [anchor, want] of cases) assert.deepEqual(sectionForAnchor(anchor), want, anchor);
});

test("the tiles themselves, the skip link and an unknown id open nothing", () => {
  assert.equal(sectionForAnchor("autofill"), null);
  assert.equal(sectionForAnchor("main-content"), null);
  assert.equal(sectionForAnchor(""), null);
  assert.equal(sectionForAnchor("not-autofill-personal"), null, "a prefix, not a substring");
});

test("no two sections claim one card id", () => {
  const ids = [...PROFILE_TILES, ...PROFILE_FOLDS].map(cardId);
  assert.equal(new Set(ids).size, ids.length);
});
