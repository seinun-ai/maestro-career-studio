import assert from "node:assert/strict";
import { test } from "node:test";

import { describeEdits } from "./describe-edit.ts";

const doc = {
  summary: "Old summary",
  experience: [
    { company: "Acme", role: "Data Scientist", bullets: ["Built a churn model", "Led a team"] },
    { company: "Foo", role: "Analyst", enabled: false, bullets: [] },
  ],
  projects: [{ name: "Churn model", bullets: ["Shipped it"] }],
  education: [{ institution: "Stanford", degree: "MS Computer Science", bullets: [] }],
  skills: [{ category: "Languages", items: ["Python"] }],
  extra_sections: [
    { key: "publications", title: "Publications", type: "bullets", bullets: [] },
    { key: "talks", title: "Talks", type: "bullets", bullets: [] },
  ],
};

const one = (op: Record<string, unknown>, d: unknown = doc) =>
  describeEdits([op], d as never)[0];

test("names the entry and the bullet in the user's words", () => {
  assert.deepEqual(
    one({ kind: "replace_bullet", section: "experience", index: 0, bullet_index: 1, value: "Led a team of four" }),
    { action: "Rewrite bullet 2 of Data Scientist at Acme", detail: "Led a team of four" },
  );
  assert.equal(one({ kind: "remove_entry", section: "experience", index: 1 }).action, "Remove Analyst at Foo (hidden)");
  assert.equal(one({ kind: "toggle_entry", section: "experience", index: 1, enabled: true }).action, "Show Analyst at Foo on the PDF");
  assert.equal(one({ kind: "add_bullet", section: "projects", index: 0, text: "x" }).action, "Add a bullet to Churn model");
  assert.equal(one({ kind: "replace_entry", section: "education", index: 0, value: {} }).action, "Edit MS Computer Science at Stanford");
});

test("covers every op kind without printing a key or a path", () => {
  const ops = [
    { kind: "replace_summary", value: "New" },
    { kind: "replace_summary", value: null },
    { kind: "toggle_entry", section: "experience", index: 0, enabled: false },
    { kind: "replace_bullet", section: "experience", index: 0, bullet_index: 0, value: "v" },
    { kind: "replace_skills_group", category: "languages", items: ["Python", "SQL"] },
    { kind: "add_skill_item", category: "Cloud", item: "AWS" },
    { kind: "add_bullet", section: "experience", index: 0, text: "t" },
    { kind: "add_entry", section: "projects", value: { name: "New tool", bullets: [] } },
    { kind: "replace_entry", section: "projects", index: 0, value: { name: "Churn model" } },
    { kind: "remove_entry", section: "education", index: 0 },
    { kind: "remove_bullet", section: "projects", index: 0, bullet_index: 0 },
    { kind: "replace_contact", value: {} },
    { kind: "replace_certifications", items: ["AWS SA"] },
    { kind: "add_extra_section", value: { key: "awards", title: "Awards" } },
    { kind: "replace_extra_section", section_key: "talks", value: { key: "talks", title: "Talks" } },
    { kind: "remove_extra_section", section_key: "publications" },
    { kind: "move_extra_section", section_key: "awards", to_index: 0 },
    { kind: "brand_new_kind", section: "experience", index: 0 },
  ];
  for (const w of describeEdits(ops, doc as never)) {
    assert.doesNotMatch(w.action, /_|\[|\]|\bundefined\b|\bnull\b/, w.action);
  }
  const words = describeEdits(ops, doc as never).map((w) => w.action);
  assert.equal(words[4], "Replace the Languages skills");
  assert.equal(words[5], "Add AWS to a new Cloud skills group");
  assert.equal(words[13], "Add the Awards section");
  assert.equal(words[16], "Move the Awards section to the top");
  assert.equal(words[17], "Change Experience");
});

test("later ops index the document earlier ops left behind", () => {
  const words = describeEdits(
    [
      { kind: "remove_entry", section: "experience", index: 0 },
      { kind: "replace_bullet", section: "experience", index: 0, bullet_index: 0, value: "v" },
    ],
    doc as never,
  );
  assert.equal(words[0].action, "Remove Data Scientist at Acme");
  // Index 0 is now Foo, which has no bullet 1: no invented ordinal.
  assert.equal(words[1].action, "Rewrite a bullet in Experience");
});

test("without a document, names the section and nothing it cannot know", () => {
  const w = describeEdits([
    { kind: "remove_bullet", section: "experience", index: 3, bullet_index: 2 },
    { kind: "add_skill_item", category: "Cloud", item: "AWS" },
  ]);
  assert.equal(w[0].action, "Remove a bullet in Experience");
  assert.equal(w[1].action, "Add AWS to the Cloud skills");
});

test("an index past the end names no entry", () => {
  assert.equal(one({ kind: "remove_entry", section: "projects", index: 9 }).action, "Remove an entry from Projects");
});

test("does not mutate the document it describes", () => {
  const before = JSON.stringify(doc);
  describeEdits([{ kind: "remove_entry", section: "experience", index: 0 }, { kind: "add_bullet", section: "projects", index: 0, text: "x" }], doc as never);
  assert.equal(JSON.stringify(doc), before);
});
