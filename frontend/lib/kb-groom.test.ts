import assert from "node:assert/strict";
import { test } from "node:test";

import { combinedToast, groomState, otherIds, pairsOf, undoCombinePlan } from "./kb-groom.ts";
import type { GroomCluster, GroomReport } from "./types.ts";

const member = (id: string, text = id) =>
  ({ id, text, state: "approved", origin: "manual", provenance: null, usage_count: 0, best_score: 1 }) as GroomCluster["members"][number];
const cluster: GroomCluster = {
  score: 0.93, keeper_id: "a", members: [member("a"), member("b"), member("c")],
  pairs: [["a", "b", 0.93], ["b", "c", 0.85]],
};
const report = (over: Partial<GroomReport>): GroomReport => ({
  entity_id: "e", entity_title: "Orbit", compared_wording: true, active_points: 3, clusters: [cluster], ...over,
});

test("Combine sends every member but the selected keeper", () => {
  assert.deepEqual(otherIds(cluster, "a"), ["b", "c"]);
  assert.deepEqual(otherIds(cluster, "c"), ["a", "b"]);
});

test("Not the same sends every member, once", () => {
  assert.deepEqual(pairsOf(cluster), ["a", "b", "c"]);
});

test("the dialog's state: clusters, empty, or could not compare", () => {
  assert.equal(groomState(report({})), "clusters");
  assert.equal(groomState(report({ clusters: [] })), "empty");
  assert.equal(groomState(report({ clusters: [], compared_wording: false })), "failed");
});

test("the toast counts the folded bullets and names the keeper", () => {
  assert.equal(combinedToast(2, "Cleansed 2M rows"), "Combined 3 bullets into one. Cleansed 2M rows stays.");
  assert.equal(combinedToast(1, "Cleansed 2M rows"), "Combined 2 bullets into one. Cleansed 2M rows stays.");
});

test("Undo puts each loser back in its prior state, then its own combined claims back onto it", () => {
  const losers = [member("b"), { ...member("c"), state: "draft" as const }];
  const plan = undoCombinePlan(losers, [
    { point_id: "x", from_id: "b" }, { point_id: "y", from_id: "b" }, { point_id: "z", from_id: "c" },
  ]);
  assert.deepEqual(plan.restore, [{ id: "b", state: "approved" }, { id: "c", state: "draft" }]);
  assert.deepEqual(plan.recombine, [{ keeperId: "b", pointIds: ["x", "y"] }, { keeperId: "c", pointIds: ["z"] }]);
  assert.deepEqual(undoCombinePlan(losers, []).recombine, []);
});
