import assert from "node:assert/strict";
import { test } from "node:test";

import { lineDiff } from "./word-diff.ts";

const marks = (segments: { text: string; changed: boolean }[]) => segments.filter((s) => s.changed).map((s) => s.text);
const join = (segments: { text: string }[]) => segments.map((s) => s.text).join("");

test("each side joins back to its own text exactly", () => {
  const old = "Built Power BI and Excel KPI dashboards (six apps).";
  const now = "Built Power BI KPI dashboards for six enterprise apps.";
  const { before, after } = lineDiff(old, now);
  assert.equal(join(before), old);
  assert.equal(join(after), now);
});

test("a reworded bullet marks the words that went and the words that came", () => {
  const { before, after } = lineDiff(
    "Built Power BI and Excel KPI dashboards",
    "Built Power BI KPI dashboards for six apps",
  );
  assert.deepEqual(marks(before), ["and Excel"]);
  assert.deepEqual(marks(after), ["for six apps"]);
});

test("items added to a skills group leave the last old item unmarked", () => {
  const { before, after } = lineDiff(
    "Data & Cloud: AWS (S3, SageMaker), Databricks",
    "Data & Cloud: AWS (S3, SageMaker), Databricks, Power Automate, Data governance",
  );
  assert.deepEqual(marks(before), []);
  assert.deepEqual(marks(after), [", Power Automate, Data governance"]);
});

test("words in any script are words", () => {
  const { before, after } = lineDiff("Gestión de datos en São Paulo", "Gestión de proyectos en São Paulo");
  assert.deepEqual(marks(before), ["datos"]);
  assert.deepEqual(marks(after), ["proyectos"]);
});

test("a mark ends at its words, never at a space", () => {
  for (const side of Object.values(lineDiff("Led a team of four on AWS", "Led two teams on Azure"))) {
    for (const run of side.filter((s) => s.changed)) assert.equal(run.text, run.text.trim(), JSON.stringify(run));
  }
});

test("one empty side marks the other whole", () => {
  assert.deepEqual(lineDiff("", "Led the migration"), { before: [], after: [{ text: "Led the migration", changed: true }] });
  assert.deepEqual(lineDiff("Led the migration", ""), { before: [{ text: "Led the migration", changed: true }], after: [] });
});
