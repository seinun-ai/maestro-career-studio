import assert from "node:assert/strict";
import { test } from "node:test";

import { humanizeSlug } from "./humanize-slug.ts";

test("cases the catalog's acronyms the way its labels do", () => {
  assert.equal(humanizeSlug("ai_ml_engineer"), "AI/ML Engineer");
  assert.equal(humanizeSlug("mlops_engineer"), "MLOps Engineer");
  assert.equal(humanizeSlug("bi_developer"), "BI Developer");
  assert.equal(humanizeSlug("qa_engineer"), "QA Engineer");
  assert.equal(humanizeSlug("it_support"), "IT Support");
});

test("title-cases every other word", () => {
  assert.equal(humanizeSlug("data_scientist"), "Data Scientist");
  assert.equal(humanizeSlug("other"), "Other");
  assert.equal(humanizeSlug("ds_base"), "Ds Base");
});

test("an acronym inside a word is left alone", () => {
  // A token is a whole word between underscores: "email" is not "ai".
  assert.equal(humanizeSlug("email_marketer"), "Email Marketer");
  assert.equal(humanizeSlug("maintainer"), "Maintainer");
});

test("never returns a blank label", () => {
  assert.equal(humanizeSlug(null), "Unknown");
  assert.equal(humanizeSlug(undefined), "Unknown");
  assert.equal(humanizeSlug(""), "Unknown");
  assert.equal(humanizeSlug("__"), "Unknown");
});
