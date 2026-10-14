import assert from "node:assert/strict";
import { test } from "node:test";

import { scorePill } from "./job-standing.ts";

const base = (target_id: string, composite: number) => ({
  phase: "base", target_id, composite, application_id: null, created_at: "2026-10-01T10:00:00Z",
});
const tailored = (composite: number, created_at: string, application_id = "app-1") => ({
  phase: "tailored", target_id: "app-1", composite, application_id, created_at,
});

test("a tailored score reads Resume match, tailored", () => {
  const pill = scorePill([base("a", 70), base("b", 82), tailored(91, "2026-10-02T10:00:00Z")], "app-1");
  assert.deepEqual(pill, { label: "Resume match", value: 91, targetId: "app-1", tailored: true });
});

test("the newest tailored score of the application wins", () => {
  const pill = scorePill([tailored(80, "2026-10-02T10:00:00Z"), tailored(88, "2026-10-03T10:00:00Z")], "app-1");
  assert.equal(pill?.value, 88);
});

test("only base scores read Best base resume, the highest", () => {
  const pill = scorePill([base("a", 70), base("b", 82)], null);
  assert.deepEqual(pill, { label: "Best base resume", value: 82, targetId: "b", tailored: false });
});

test("a tailored score of another application does not count", () => {
  const pill = scorePill([base("a", 70), tailored(99, "2026-10-02T10:00:00Z", "other")], "app-1");
  assert.equal(pill?.label, "Best base resume");
});

test("neither score, no pill", () => {
  assert.equal(scorePill([], null), null);
  assert.equal(scorePill([], "app-1"), null);
});
