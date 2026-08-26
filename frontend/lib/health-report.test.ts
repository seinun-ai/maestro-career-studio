import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONTENT_CHANGED_PREFIX,
  composeMetricContext,
  explainScoreDelta,
  groupFindings,
  groupNotesByRule,
  hoistBlurb,
  isBulletSubjectRule,
  isContentChangedError,
  isMetricAsk,
  potentialPoints,
  punctFixOps,
  reportIsStale,
  scoreCompositionLine,
  stripTrailingPunct,
  contentHash16,
  staleFindingIds,
} from "./health-report.ts";

test("reportIsStale treats missing as false", () => {
  assert.equal(reportIsStale(undefined), false);
  assert.equal(reportIsStale({}), false);
  assert.equal(reportIsStale({ stale: false }), false);
  assert.equal(reportIsStale({ stale: true }), true);
});

test("scoreCompositionLine names the cap tier", () => {
  assert.equal(scoreCompositionLine(83, null), null);
  assert.equal(
    scoreCompositionLine(69, {
      raw_score: 88,
      e_hot: 0.9,
      n_scoreable: 12,
      capped_by: "serious",
    }),
    "mean evidence 88 · capped to 69 by one serious gate",
  );
  assert.equal(
    scoreCompositionLine(88, {
      raw_score: 88,
      e_hot: null,
      n_scoreable: 12,
      capped_by: null,
    }),
    "mean evidence 88",
  );
});

test("potentialPoints is 100 × (1 − level) / n_scoreable", () => {
  assert.equal(potentialPoints("adjacent", 10), 5);
  assert.equal(potentialPoints("unaddressed", 4), 25);
  assert.equal(potentialPoints("direct", 8), 0);
  assert.equal(potentialPoints("adjacent", null), null);
});

test("groupFindings orders groups by first appearance, findings within by input order", () => {
  const findings = [
    { id: "a", location: { section: "experience", index: 1 } },
    { id: "b", location: { section: "summary" } },
    { id: "c", location: { section: "experience", index: 1 } },
    { id: "d", location: { section: "skills" } },
    { id: "e", location: { section: "experience", index: 0 } },
  ];
  const groups = groupFindings(findings);
  assert.deepEqual(
    groups.map((g) => g.key),
    ["experience:1", "summary", "skills", "experience:0"],
  );
  assert.deepEqual(
    groups[0].findings.map((f) => f.id),
    ["a", "c"],
  );
});

test("hoistBlurb fires only when issue and how are identical", () => {
  const shared = [
    { issue: "Specific, but carries no number.", how: "Add the metric that measures it." },
    { issue: "Specific, but carries no number.", how: "Add the metric that measures it." },
  ];
  assert.equal(
    hoistBlurb(shared),
    "2 items here are specific, but carries no number. Add the metric that measures each.",
  );
  assert.equal(
    hoistBlurb([shared[0]]),
    "This bullet is specific, but carries no number. Add the metric that measures it.",
  );
  assert.equal(
    hoistBlurb([
      shared[0],
      { issue: "A reader can't tell what you did here.", how: shared[0].how },
    ]),
    null,
  );
});

test("groupNotesByRule counts subjects inline", () => {
  const groups = groupNotesByRule([
    {
      rule: "skills.undemonstrated",
      subject: "Docker",
      label: "Skills · Docker",
      issue: '"Docker" is listed but never demonstrated in a bullet.',
    },
    {
      rule: "skills.undemonstrated",
      subject: "Git",
      label: "Skills · Git",
      issue: '"Git" is listed but never demonstrated in a bullet.',
    },
    {
      rule: "skills.trailing_punct",
      subject: "Python.",
      label: "Skills · Python.",
      issue: '"Python." ends with a stray period.',
    },
  ]);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].title, "Listed but never demonstrated");
  assert.equal(groups[0].count, 2);
  assert.deepEqual(groups[0].subjects, ["Docker", "Git"]);
  assert.equal(groups[1].count, 1);
});

test("isContentChangedError matches the pinned 409 prefix", () => {
  assert.equal(
    isContentChangedError({
      status: 409,
      message: `${CONTENT_CHANGED_PREFIX}: bullet 2`,
    }),
    true,
  );
  assert.equal(isContentChangedError({ status: 409, message: "conflict" }), false);
  assert.equal(
    isContentChangedError({ status: 422, message: CONTENT_CHANGED_PREFIX }),
    false,
  );
});

test("punctFixOps rewrites skills via replace_skills_group", () => {
  const ops = punctFixOps(
    "skills.trailing_punct",
    ["Python."],
    {
      contact: { name: "", email: "" },
      skills: [{ category: "Languages", items: ["Python.", "Go"] }],
      experience: [],
      projects: [],
      education: [],
      certifications: [],
      extra_sections: [],
    },
  );
  assert.deepEqual(ops, [
    {
      kind: "replace_skills_group",
      category: "Languages",
      items: ["Python", "Go"],
    },
  ]);
});

test("stripTrailingPunct drops the stray mark and preceding space", () => {
  assert.equal(stripTrailingPunct("Python."), "Python");
  assert.equal(stripTrailingPunct("Python ."), "Python");
  assert.equal(stripTrailingPunct("AWS…"), "AWS");
});

test("isMetricAsk matches the adjacent number question", () => {
  assert.equal(
    isMetricAsk("What number measures this — users, rows, %, time saved?"),
    true,
  );
  assert.equal(isMetricAsk("What did you personally do here?"), false);
  assert.equal(isMetricAsk(undefined), false);
});

test("composeMetricContext builds the walk-through sentence", () => {
  assert.equal(
    composeMetricContext({
      amount: "5,000",
      unit: "users",
      timeframe: "6 months",
    }),
    "served 5,000 users within 6 months",
  );
  assert.equal(
    composeMetricContext({ amount: "40", unit: "percent" }),
    "40%",
  );
  assert.equal(
    composeMetricContext({ amount: "12", unit: "other", unitOther: "datasets" }),
    "12 datasets",
  );
});

test("isBulletSubjectRule is only the bullet-length notes", () => {
  assert.equal(isBulletSubjectRule("bullet.too_long"), true);
  assert.equal(isBulletSubjectRule("bullet.too_short"), true);
  assert.equal(isBulletSubjectRule("skills.undemonstrated"), false);
});

test("explainScoreDelta names implied Awards bullets entering the score", () => {
  const prior = [
    {
      type: "ask",
      location: { section: "experience", index: 0, bullet_index: 0 },
      content_hash: "aaaaaaaaaaaaaaaa",
      classification_level: "adjacent",
      level: 0.5,
    },
  ];
  const next = [
    ...prior,
    {
      type: "ask",
      location: { section: "extra:awards", bullet_index: 0 },
      content_hash: "bbbbbbbbbbbbbbbb",
      classification_level: "implied",
      level: 0.3,
    },
    {
      type: "ask",
      location: { section: "extra:awards", bullet_index: 1 },
      content_hash: "cccccccccccccccc",
      classification_level: "implied",
      level: 0.3,
    },
  ];
  assert.equal(
    explainScoreDelta(prior, next, (key) =>
      key === "extra:awards" ? "Awards & Honors" : key,
    ),
    "+2 bullets in Awards & Honors entered at implied.",
  );
});

test("explainScoreDelta falls back when the diff is empty", () => {
  const row = {
    type: "ask",
    location: { section: "experience", index: 0, bullet_index: 0 },
    content_hash: "aaaaaaaaaaaaaaaa",
    classification_level: "adjacent",
    level: 0.5,
  };
  assert.equal(explainScoreDelta([row], [row], () => "x"), null);
});
test("groupNotesByRule titles a rule-less shape note by its label", () => {
  const groups = groupNotesByRule([
    {
      label: "Evidence concentrated in projects",
      issue: "14 project bullets vs 10 employment bullets.",
      id: "n1",
    } as never,
  ]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].title, "Evidence concentrated in projects");
  assert.equal(groups[0].shapeNote, true);
});

test("groupNotesByRule keeps rule-keyed titles for advisory notes", () => {
  const groups = groupNotesByRule([
    {
      rule: "skills.undemonstrated",
      subject: "Docker",
      label: "Skills · Docker",
      issue: '"Docker" is listed but never demonstrated in a bullet.',
      id: "n2",
    } as never,
  ]);
  assert.equal(groups[0].title, "Listed but never demonstrated");
  assert.equal(groups[0].shapeNote, false);
});


test("contentHash16 matches backend bullet_classify.content_hash", async () => {
  assert.equal(await contentHash16("Kept the lights on."), "25a0d525ab092b34");
  assert.equal(await contentHash16("  Kept   the lights on. "), "25a0d525ab092b34");
  assert.equal(await contentHash16("Built an MCP server."), "c6939498dc73db90");
});

test("staleFindingIds flags only findings whose text drifted", async () => {
  const data = {
    experience: [{ bullets: ["Kept the lights on.", "Built an MCP server."] }],
  } as never;
  const findings = [
    {
      id: "fresh",
      content_hash: "25a0d525ab092b34",
      location: { section: "experience", index: 0, bullet_index: 0 },
    },
    {
      id: "drifted",
      content_hash: "0000000000000000",
      location: { section: "experience", index: 0, bullet_index: 1 },
    },
    {
      id: "vanished",
      content_hash: "25a0d525ab092b34",
      location: { section: "experience", index: 0, bullet_index: 9 },
    },
    {
      id: "no-hash",
      location: { section: "experience", index: 0, bullet_index: 0 },
    },
  ];
  const stale = await staleFindingIds(findings as never, data);
  assert.deepEqual([...stale].sort(), ["drifted", "vanished"]);
});
