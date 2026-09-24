import assert from "node:assert/strict";
import { test } from "node:test";

import {
  datesUnreadable,
  fixHintLabel,
  placementLabel,
  requirementLabel,
  undatedEvidence,
} from "./ats-words.ts";

test("every engine placement reads as words", () => {
  for (const key of ["dual", "experience_only", "skills_list_only", "undated_only", "extra_only", "credential_only"]) {
    const label = placementLabel(key);
    assert.ok(label && !label.includes("_"), key);
  }
  assert.equal(placementLabel("experience_only"), "Experience");
});

test("every engine fix hint reads as words", () => {
  for (const key of ["absent", "mirror_wording", "dual_place", "resurface_recent", "credential_only", "adjacent_available", "extra_only"]) {
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

test("a skill the resume lacks says so, and never tells you to add it", () => {
  assert.equal(fixHintLabel("absent"), "Not on your resume");
});

test("unreadable job dates are named, with a format that works", () => {
  // backend/app/services/ats/layers.py l5_format's flag, as the engine writes it.
  assert.equal(datesUnreadable(["Some job dates can't be read. Write them like Jul 2022."]), true);
  assert.equal(datesUnreadable(["Section missing or empty: summary"]), false);
  assert.equal(datesUnreadable(undefined), false);
});

test("a skills-list skill found in undated entries says why they don't count", () => {
  // A skills-list hit outranks undated evidence (ats/layers.py _select_placement), so the skill
  // reads "no example" while the engine lists the entries it was found in.
  assert.equal(undatedEvidence("skills_list_only", ["Northwind — Data Scientist"]), true);
  assert.equal(undatedEvidence("skills_list_only", []), false);
  assert.equal(undatedEvidence("dual", ["Northwind — Data Scientist"]), false);
});
