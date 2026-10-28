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

test("acronyms from fields beyond tech go upper case too", () => {
  assert.equal(skillName("sap"), "SAP");
  assert.equal(skillName("sap s/4hana"), "SAP S/4HANA");
  assert.equal(skillName("hr analytics"), "HR analytics");
  assert.equal(skillName("gaap"), "GAAP");
  assert.equal(skillName("seo"), "SEO");
  assert.equal(skillName("hipaa compliance"), "HIPAA compliance");
  assert.equal(skillName("ehr systems"), "EHR systems");
  assert.equal(skillName("cad"), "CAD");
  assert.equal(skillName("s&op"), "S&OP");
});
