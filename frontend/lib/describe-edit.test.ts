import assert from "node:assert/strict";
import { test } from "node:test";

import {
  describeEdits,
  describeFieldPath,
  diffChangeWords,
  fieldsNeedFixing,
  jsonErrorWords,
  schemaIssuesWords,
  versionSummaryWords,
} from "./describe-edit.ts";

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
  assert.equal(words[5], "Add AWS to a new Cloud skill group");
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

test("an index past the end names no item", () => {
  assert.equal(one({ kind: "remove_entry", section: "projects", index: 9 }).action, "Remove an item from Projects");
});

test("does not mutate the document it describes", () => {
  const before = JSON.stringify(doc);
  describeEdits([{ kind: "remove_entry", section: "experience", index: 0 }, { kind: "add_bullet", section: "projects", index: 0, text: "x" }], doc as never);
  assert.equal(JSON.stringify(doc), before);
});

test("a failed field reads as a place, never a path", () => {
  assert.equal(describeFieldPath(["experience", 2, "bullets", 0]), "Experience, item 3, bullet 1");
  assert.equal(describeFieldPath(["contact", "email"]), "Contact, Email");
  assert.equal(describeFieldPath(["skills", 0, "items", 4]), "Skills, group 1, skill 5");
  assert.equal(describeFieldPath(["extra_sections", 1, "entries", 0, "start_date"]), "Other sections, section 2, item 1, Start date");
  assert.equal(describeFieldPath([]), "The resume");
  const all = fieldsNeedFixing([["experience", 2, "bullets", 0], ["experience", 2, "bullets", 0], ["contact", "name"]]);
  assert.equal(all, "Some fields need fixing: Experience, item 3, bullet 1. Contact, Name.");
  assert.doesNotMatch(all, /_|\.\d|\[/);
  const many = fieldsNeedFixing([["contact", "name"], ["summary"], ["projects", 0, "name"], ["education", 1, "institution"]]);
  assert.equal(many, "Some fields need fixing: Contact, Name. Summary. Projects, item 1, Name. And 1 more.");
});

test("a field reads as the label its editor shows", () => {
  assert.equal(describeFieldPath(["education", 0, "institution"]), "Education, item 1, School");
  assert.equal(describeFieldPath(["skills", 1, "category"]), "Skills, group 2, Group name");
  assert.equal(describeFieldPath(["projects", 0, "tech"]), "Projects, item 1, Tools used");
  assert.equal(describeFieldPath(["education", 0, "gpa"]), "Education, item 1, GPA");
  assert.equal(describeFieldPath(["contact", "linkedin"]), "Contact, LinkedIn");
  assert.equal(describeFieldPath(["contact", "github"]), "Contact, GitHub");
  assert.equal(describeFieldPath(["experience", 0, "role"]), "Experience, item 1, Role");
  assert.equal(describeFieldPath(["experience", 0, "company"]), "Experience, item 1, Company");
});

test("the code view names the field and the problem, never a path or the library's words", () => {
  assert.equal(
    schemaIssuesWords([{ path: ["contact", "email"], code: "invalid_type", expected: "string", message: "Invalid input: expected string, received number" }]),
    "Couldn't apply: Contact, Email must be text. Fix it and choose Apply again.",
  );
  const two = schemaIssuesWords([
    { path: ["experience", 0, "company"], code: "invalid_type", expected: "string", message: "Invalid input: expected string, received undefined" },
    { path: ["contact", "name"], code: "too_small", origin: "string", message: "Enter your name" },
  ]);
  assert.equal(two, "Couldn't apply: Experience, item 1, Company is missing. Contact, Name: Enter your name. Fix them and choose Apply again.");
  assert.doesNotMatch(two, /Invalid input|\.\d|_/);
  assert.match(
    schemaIssuesWords([{ path: ["extra_sections", 0, "type"], code: "invalid_union", message: "Invalid input" }]),
    /Other sections, section 1, Layout isn't one of the allowed choices/,
  );
});

test("code the parser can't read is named by its line", () => {
  const text = '{\n "a": 1\n "b": 2}';
  let error: unknown;
  try {
    JSON.parse(text);
  } catch (e) {
    error = e;
  }
  assert.equal(jsonErrorWords(text, error), "Couldn't read the code at line 3. Check for a missing comma or quote.");
  assert.equal(
    jsonErrorWords(text, new SyntaxError("Unexpected token at position 11")),
    "Couldn't read the code at line 3. Check for a missing comma or quote.",
  );
  assert.equal(
    jsonErrorWords(text, new SyntaxError("JSON Parse error: Expected '}'")),
    "Couldn't read the code. Check for a missing comma or quote.",
  );
});

test("a version's changes name their section once", () => {
  assert.deepEqual(diffChangeWords({ section: "summary", label: "Summary" }), { section: "Summary", label: null });
  assert.deepEqual(diffChangeWords({ section: "experience", label: "Acme" }), { section: "Experience", label: "Acme" });
  assert.deepEqual(diffChangeWords({ section: "extra", label: "Awards" }), { section: "Other sections", label: "Awards" });
  assert.equal(
    versionSummaryWords("Updated summary · Summary; Added experience · Acme; +2 more"),
    "Updated Summary; Added Experience · Acme; +2 more",
  );
  assert.equal(versionSummaryWords("Materialized from base resume jordan"), "Materialized from base resume jordan");
  assert.equal(versionSummaryWords("Added resume · Initial version"), "Initial version");
});
