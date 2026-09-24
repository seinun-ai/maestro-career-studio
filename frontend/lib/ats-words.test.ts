import assert from "node:assert/strict";
import { test } from "node:test";

import { fixHintLabel, placementLabel, requirementLabel } from "./ats-words.ts";

test("every engine placement reads as words", () => {
  for (const key of ["dual", "experience_only", "skills_list_only", "undated_only", "extra_only", "credential_only"]) {
    const label = placementLabel(key);
    assert.ok(label && !label.includes("_"), key);
  }
  assert.equal(placementLabel("experience_only"), "Experience");
});

test("every engine fix hint reads as words", () => {
  for (const key of ["absent", "mirror_wording", "dual_place", "resurface_recent", "credential_only", "adjacent_available"]) {
    const label = fixHintLabel(key);
    assert.ok(label && !label.includes("_"), key);
  }
  assert.equal(fixHintLabel("mirror_wording"), "Use the job's words");
});

test("an unknown or missing key shows nothing, never the key", () => {
  assert.equal(placementLabel("new_engine_key"), null);
  assert.equal(fixHintLabel(null), null);
  assert.equal(placementLabel(undefined), null);
});

test("a requirement level reads capitalized, and an unknown one shows nothing", () => {
  assert.equal(requirementLabel("preferred"), "Preferred");
  assert.equal(requirementLabel("nice_to_have"), null);
});
