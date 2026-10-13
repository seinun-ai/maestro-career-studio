import assert from "node:assert/strict";
import { test } from "node:test";

import { groupByRole, isRoleUnset } from "./role-groups.ts";

type R = { slug: string; role_category: string; role_label: string | null; archived_at?: string | null };
const r = (slug: string, role_category: string, role_label: string | null = null, archived_at: string | null = null): R => ({
  slug,
  role_category,
  role_label,
  archived_at,
});
const labelOf = (x: R) => x.role_label ?? x.role_category.toUpperCase();
const shape = (groups: ReturnType<typeof groupByRole<R>>) => groups.map((g) => [g.label, g.resumes.map((x) => x.slug)]);

test("groups come in the order each role first appears, members in list order", () => {
  const groups = groupByRole([r("a", "ds"), r("b", "de"), r("c", "ds"), r("d", "ml")], labelOf);
  assert.deepEqual(shape(groups), [["DS", ["a", "c"]], ["DE", ["b"]], ["ML", ["d"]]]);
});

test("a free-text role merges across letter case and the first label wins", () => {
  const groups = groupByRole([r("a", "other", "Analytics Engineer"), r("b", "other", "analytics engineer")], labelOf);
  assert.deepEqual(shape(groups), [["Analytics Engineer", ["a", "b"]]]);
  assert.equal(groups[0].key, "l:analytics engineer");
});

test("a catalog role and a free-text role never share a group, and the keys do not collide", () => {
  const groups = groupByRole([r("a", "ds"), r("b", "ds", "Ds"), r("c", "other", "ds")], labelOf);
  assert.deepEqual(groups.map((g) => g.key), ["c:ds", "l:ds"]);
  assert.deepEqual(shape(groups), [["DS", ["a"]], ["Ds", ["b", "c"]]]);
});

test("resumes with no role go last, and the group is left out when none is unset", () => {
  const withUnset = groupByRole([r("a", "unknown"), r("b", "ds"), r("c", "unknown")], labelOf);
  assert.deepEqual(shape(withUnset), [["DS", ["b"]], [null, ["a", "c"]]]);
  assert.deepEqual(shape(groupByRole([r("a", "ds")], labelOf)), [["DS", ["a"]]]);
  assert.deepEqual(groupByRole([], labelOf), []);
});

test("an unknown category with a free-text label is a role, not unset", () => {
  assert.equal(isRoleUnset(r("a", "unknown")), true);
  assert.equal(isRoleUnset(r("a", "unknown", "Founding engineer")), false);
  assert.equal(isRoleUnset(r("a", "ds")), false);
  assert.deepEqual(shape(groupByRole([r("a", "unknown", "Founding engineer")], labelOf)), [["Founding engineer", ["a"]]]);
});

test("archived resumes stay in their group", () => {
  const groups = groupByRole([r("a", "ds"), r("b", "ds", null, "2026-01-01"), r("c", "unknown", null, "2026-01-01")], labelOf);
  assert.deepEqual(shape(groups), [["DS", ["a", "b"]], [null, ["c"]]]);
});
