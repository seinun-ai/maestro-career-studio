import assert from "node:assert/strict";
import { test } from "node:test";

import { skillName } from "./skill-name.ts";

test("a known skill takes its usual form in any case", () => {
  assert.equal(skillName("pytorch"), "PyTorch");
  assert.equal(skillName("Machine Learning"), "Machine learning");
  assert.equal(skillName("machine learning"), "Machine learning");
  assert.equal(skillName("mlflow"), "MLflow");
});

test("acronyms go upper case and the first letter is capitalized", () => {
  assert.equal(skillName("a/b testing"), "A/B testing");
  assert.equal(skillName("power bi"), "Power BI");
  assert.equal(skillName("sql"), "SQL");
  assert.equal(skillName("python"), "Python");
});

test("a name someone already cased keeps its casing", () => {
  assert.equal(skillName("Causal inference"), "Causal inference");
  assert.equal(skillName("Snowflake"), "Snowflake");
});
