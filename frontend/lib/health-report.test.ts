import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONTENT_CHANGED_PREFIX,
  DISPUTE_DETAIL,
  disputeChangedRating,
  disputeFailure,
  hasOpenRating,
  liftedDispute,
  resolvedFindings,
  composeMetricContext,
  explainScoreDelta,
  groupFindings,
  groupPoints,
  nextGradeLine,
  groupNotesByRule,
  hoistBlurb,
  isBulletSubjectRule,
  isContentChangedError,
  isMetricAsk,
  potentialPoints,
  punctFixOps,
  reportIsStale,
  scoreCompositionLine,
  healthCounts,
  leftToFix,
  checkDoneWords,
  addNumbersLabel,
  stripTrailingPunct,
  contentHash16,
  staleFindingIds,
  shortFindingLabel,
  addWord,
  bulletEditOp,
  canIgnore,
  isWordingRule,
  normalizeWord,
  slipFix,
  splitWordingNotes,
  withDraft,
  withIgnored,
  wordingEditOp,
  WORD_LIST_MAX,
} from "./health-report.ts";

test("reportIsStale treats missing as false", () => {
  assert.equal(reportIsStale(undefined), false);
  assert.equal(reportIsStale({}), false);
  assert.equal(reportIsStale({ stale: false }), false);
  assert.equal(reportIsStale({ stale: true }), true);
});

test("scoreCompositionLine names the real count and tier that capped the score", () => {
  const capped = (capped_by: "fatal" | "serious" | null) => ({ raw_score: 88, e_hot: 0.9, n_scoreable: 12, capped_by });
  assert.equal(scoreCompositionLine(83, null), null);
  assert.equal(scoreCompositionLine(88, capped(null), []), null);
  // One serious check caps at 69: it is not a must-fix problem.
  assert.equal(
    scoreCompositionLine(69, capped("serious"), [{ tier: "serious", status: "fail" }]),
    "Score limited to 69 by 1 serious problem",
  );
  assert.equal(
    scoreCompositionLine(54, capped("fatal"), [
      { tier: "fatal", status: "fail" },
      { tier: "fatal", status: "fail" },
      { tier: "serious", status: "waived" },
    ]),
    "Score limited to 54 by 2 must-fix problems",
  );
  // Two serious checks cap like a must-fix one, and are named as what they are.
  assert.equal(
    scoreCompositionLine(54, capped("fatal"), [
      { tier: "serious", status: "fail" },
      { tier: "serious", status: "fail" },
    ]),
    "Score limited to 54 by 2 serious problems",
  );
});

test("must fix counts only failed fatal checks, and left to fix agrees with it", () => {
  const counts = healthCounts({
    counts: { gate: 3, critical: 2, ask: 1, note: 4 },
    gates: [
      { tier: "fatal", status: "fail" },
      { tier: "serious", status: "fail" },
      { tier: "fatal", status: "waived" },
      { tier: "fatal", status: "not_assessed" },
      { tier: "fatal", status: "pass" },
    ],
  });
  assert.deepEqual(counts, { gate: 1, serious: 1, critical: 2, ask: 1, note: 4 });
  // "1 must fix" never sits beside "0 left to fix".
  assert.equal(leftToFix(counts, 0), 2);
  assert.equal(leftToFix(healthCounts({ counts: {}, gates: [] }), 3), 3);
});

test("a check with too little to grade never announces a grade", () => {
  assert.equal(checkDoneWords({ grade: "F", insufficient_evidence: true }), "Check done. Too little to grade yet.");
  assert.equal(checkDoneWords({ grade: "B" }), "Check done. Grade B.");
  assert.equal(addNumbersLabel(2), "Add numbers to 2 bullets");
  assert.equal(addNumbersLabel(1), "Add numbers to 1 bullet");
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
    { issue: "Specific, but has no number.", how: "Add the metric that measures it." },
    { issue: "Specific, but has no number.", how: "Add the metric that measures it." },
  ];
  assert.equal(
    hoistBlurb(shared),
    "2 bullets here: specific, but has no number. Add the metric that measures it.",
  );
  assert.equal(
    hoistBlurb([shared[0]]),
    "Specific, but has no number. Add the metric that measures it.",
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
  assert.equal(groups[0].title, "Skill not shown in any bullet");
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
    isMetricAsk({question: "What number measures this — users, rows, %, time saved?"}),
    true,
  );
  assert.equal(isMetricAsk({question: "What did you personally do here?"}), false);
  assert.equal(isMetricAsk({}), false);
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
    "2 new bullets in Awards & Honors.",
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
      label: "Projects outweigh your jobs",
      issue: "14 project bullets and 10 job bullets.",
      id: "n1",
    } as never,
  ]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].title, "Projects outweigh your jobs");
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
  assert.equal(groups[0].title, "Skill not shown in any bullet");
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

test("hoistBlurb never conjugates a backend issue sentence", () => {
  // These three shapes are why count-led phrasing was wrong: the issue is a
  // full sentence whose subject varies, so "N items here are <issue>" produced
  // "are a reader can't tell what you did here" / "are has a number for size".
  const analogue = {
    issue: "Has a number for size, but not for the result.",
    how: "Add the outcome if you have it; otherwise this bullet is already strong.",
  };
  assert.equal(
    hoistBlurb([analogue, analogue, analogue]),
    "3 bullets here: has a number for size, but not for the result. " +
      "Add the outcome if you have it; otherwise each bullet is already strong.",
  );
  const implied = {
    issue: "A reader can't tell what you did here.",
    how: "Rewrite to name the specific action you personally took.",
  };
  assert.equal(
    hoistBlurb([implied, implied]),
    "2 bullets here: a reader can't tell what you did here. " +
      "Rewrite to name the specific action you personally took.",
  );
  // "it" refers to the metric, never to the bullet — it must survive verbatim.
  assert.match(hoistBlurb([analogue, analogue])!, /if you have it;/);
});

test("shortFindingLabel drops the entry name the group header already shows", () => {
  assert.equal(
    shortFindingLabel(
      "Bone Muscle Research Center — Research Assistant - Data Science & Bioinformatics · bullet 1",
    ),
    "bullet 1",
  );
  assert.equal(shortFindingLabel("Awards & Honors · bullet 2"), "bullet 2");
  assert.equal(shortFindingLabel("Summary"), "Summary");
  assert.equal(shortFindingLabel("Trailing · "), "Trailing · ");
});


test("groupPoints sums gains once and supports older reports", () => {
  assert.equal(groupPoints([{level: 0.5}, {level: 0.5}, {level: 0.8}], 28), 5);
  assert.equal(groupPoints([{level: 0.5}], null), 0);
  assert.equal(groupPoints([{level: 0.5, gain: 0}, {level: 0.3, gain: 2}], 28), 2);
  assert.equal(groupPoints([], 28), 0);
});


test("explicit ask kind wins over legacy question wording", () => {
  assert.equal(isMetricAsk({ask_kind: "measure", question: "How fast?"}), true);
  assert.equal(isMetricAsk({ask_kind: "detail", question: "What number measures this?"}), false);
  assert.equal(isMetricAsk({ask_kind: "reword", question: null}), false);
});

test("nextGradeLine uses server distance with correct plural", () => {
  assert.equal(nextGradeLine({next_grade: {grade: "A", points: 1}}), "1 point to A");
  assert.equal(nextGradeLine({next_grade: {grade: "B", points: 12}}), "12 points to B");
  assert.equal(nextGradeLine({next_grade: null}), null);
  assert.equal(nextGradeLine({}), null);
});

test("disputeFailure tells the two 409s apart and leaves the rest to couldnt", () => {
  assert.equal(
    disputeFailure({ status: 409, message: `${CONTENT_CHANGED_PREFIX}; re-analyze before answering` }),
    "changed",
  );
  assert.equal(disputeFailure({ status: 409, message: DISPUTE_DETAIL.overridden }), "overridden");
  assert.equal(disputeFailure({ status: 409, message: "conflict" }), "failed");
  assert.equal(disputeFailure({ status: 422, message: DISPUTE_DETAIL.overridden }), "failed");
  assert.equal(disputeFailure({ status: 502, message: DISPUTE_DETAIL.unreadable }), "failed");
  assert.equal(disputeFailure({ status: 0, message: "Maestro CS isn't responding." }), "failed");
});

test("disputeChangedRating is true when the level or the question moved", () => {
  const same = { level: "adjacent" as const, question: "What came of it?" };
  assert.equal(disputeChangedRating({ before: same, after: { ...same, ask_kind: "detail" } }), false);
  assert.equal(
    disputeChangedRating({ before: same, after: { ...same, level: "direct", ask_kind: null } }),
    true,
  );
  assert.equal(
    disputeChangedRating({ before: same, after: { ...same, question: "Who used it?", ask_kind: "detail" } }),
    true,
  );
});

test("resolvedFindings: a rated bullet is fixed only once no open ask or fix rates its text", () => {
  const rated = (id: string, hash: string, bullet_index: number, type = "ask") => ({
    id,
    type,
    content_hash: hash,
    classification_level: "adjacent",
    location: { section: "experience", index: 0, bullet_index },
  });
  // A dispute changed the question: new id, same text, still asked. Not fixed.
  assert.deepEqual(resolvedFindings([rated("a", "h1", 1)], [rated("b", "h1", 1)]), []);
  // An ask that became a fix is still open.
  assert.deepEqual(resolvedFindings([rated("a", "h1", 1)], [rated("b", "h1", 1, "fix")]), []);
  // A real fix: the new text rates fine, and a note on the old text does not keep it open.
  const note = { ...rated("n", "h1", 1, "note"), classification_level: null };
  assert.deepEqual(resolvedFindings([rated("a", "h1", 1)], [note]), [rated("a", "h1", 1)]);
  // A rewrite that is still flagged: same place, new text (a hash the prior report never had),
  // still asked. Not fixed.
  assert.deepEqual(resolvedFindings([rated("a", "h1", 1)], [rated("b", "h9", 1)]), []);
  // A real rewrite elsewhere does not hold this one open.
  assert.deepEqual(resolvedFindings([rated("a", "h1", 1)], [rated("b", "h9", 4)]), [rated("a", "h1", 1)]);
  // A moved bullet: slot 2 was deleted and bullet 3 moved up into it, still flagged. Exactly the
  // deleted bullet is fixed; the moved one is not.
  assert.deepEqual(
    resolvedFindings([rated("a", "h2", 2), rated("b", "h3", 3)], [rated("c", "h3", 2)]),
    [rated("a", "h2", 2)],
  );
});

test("resolvedFindings: findings that share a location and rate no text keep the id test", () => {
  const gap = (id: string) => ({ id, type: "ask", location: { section: "experience" } });
  // Two gaps, one explained: that one is fixed, the other is not.
  assert.deepEqual(resolvedFindings([gap("g1"), gap("g2")], [gap("g2")]), [gap("g1")]);
  // The summary's years check (C2) carries the summary's hash but rates nothing: it is fixed while
  // the summary's own ask stays, and the ask's hash does not hold it open.
  const c2 = { id: "c2", type: "ask", content_hash: "hs", location: { section: "summary" } };
  const summaryAsk = {
    id: "s1",
    type: "ask",
    content_hash: "hs",
    classification_level: "implied",
    location: { section: "summary" },
  };
  assert.deepEqual(resolvedFindings([c2, summaryAsk], [summaryAsk]), [c2]);
  // And the other way: the summary's ask is fixed while C2 stays.
  assert.deepEqual(resolvedFindings([c2, summaryAsk], [c2]), [summaryAsk]);
  // Notes and gates are never listed.
  assert.deepEqual(resolvedFindings([{ ...gap("n"), type: "note" }, { ...gap("x"), type: "gate" }], []), []);
});

test("a dispute reply goes on a Fixed entry only when that dispute's re-run lifted the bullet", () => {
  const rated = { type: "ask", content_hash: "abc", classification_level: "adjacent" };
  assert.equal(hasOpenRating([rated], "abc"), true);
  assert.equal(hasOpenRating([{ ...rated, type: "note" }], "abc"), false);
  assert.equal(hasOpenRating([{ ...rated, classification_level: null }], "abc"), false);
  const disputes = { abc: { reply: "Re-read: now rated \"Shows a result\".", suggestion: null } };
  assert.equal(liftedDispute({ content_hash: "abc" }, new Set(["abc"]), disputes), disputes.abc);
  // A reply from an earlier dispute that moved nothing, then a real fix: no reply on the entry.
  assert.equal(liftedDispute({ content_hash: "abc" }, new Set(), disputes), undefined);
  assert.equal(liftedDispute({ content_hash: null }, new Set(["abc"]), disputes), undefined);
});

// --- Task 10b: the Wording checklist ------------------------------------------------------------

test("wording notes are every language.* rule, and only those", () => {
  assert.equal(isWordingRule("language.cliche"), true);
  assert.equal(isWordingRule("language.filler"), true);
  assert.equal(isWordingRule("language.slip"), true);
  assert.equal(isWordingRule("languages.listed"), false);
  assert.equal(isWordingRule("bullet.too_long"), false);
  assert.equal(isWordingRule(undefined), false);
  const note = (rule?: string) => ({ rule, label: "x", issue: "y" });
  const { wording, other } = splitWordingNotes([
    note("language.slip"),
    note("bullet.too_long"),
    note("language.cliche"),
    note(undefined),
  ]);
  assert.deepEqual(wording.map((n) => n.rule), ["language.slip", "language.cliche"]);
  assert.deepEqual(other.map((n) => n.rule), ["bullet.too_long", undefined]);
});

test("slipFix reads the fix out of the backend's issue sentence", () => {
  assert.equal(slipFix({ subject: "teh", issue: "'teh' looks like a slip: 'the'." }), "the");
  // An apostrophe inside the span or the fix is not a delimiter.
  assert.equal(
    slipFix({ subject: "its' team", issue: "'its' team' looks like a slip: 'its team'." }),
    "its team",
  );
  assert.equal(slipFix({ subject: "teh", issue: "'teh' is a cliché." }), null);
  assert.equal(slipFix({ issue: "'teh' looks like a slip: 'the'." }), null);
});

test("wordingEditOp sends the guarded suggestion with its hash, never a copy-only one", () => {
  const bullet = {
    location: { section: "experience", index: 1, bullet_index: 2 },
    suggestion: "Led the migration.",
    content_hash: "abc",
  };
  assert.deepEqual(wordingEditOp(bullet), {
    kind: "replace_bullet",
    section: "experience",
    index: 1,
    bullet_index: 2,
    value: "Led the migration.",
    expected_content_hash: "abc",
  });
  assert.deepEqual(wordingEditOp({ ...bullet, location: { section: "summary" } }), {
    kind: "replace_summary",
    value: "Led the migration.",
    expected_content_hash: "abc",
  });
  // The guards objected: nothing to apply.
  assert.equal(wordingEditOp({ ...bullet, suggestion: null }), null);
  // Other sections have no bullet edit op: copy-only.
  assert.equal(
    wordingEditOp({ ...bullet, location: { section: "extra:awards", index: 0, bullet_index: 0 } }),
    null,
  );
  // No hash, no guarded write.
  assert.equal(wordingEditOp({ ...bullet, content_hash: null }), null);
});

test("normalizeWord trims, collapses inner space and lower-cases, like the backend", () => {
  assert.equal(normalizeWord("  Team   Player "), "team player");
  assert.equal(normalizeWord("RESULTS-DRIVEN"), "results-driven");
  assert.equal(normalizeWord("   "), "");
});

test("addWord mirrors the backend's limits and says what is wrong", () => {
  assert.deepEqual(addWord(["synergy"], " Go-Getter "), { list: ["synergy", "go-getter"] });
  assert.deepEqual(addWord(["synergy"], "  "), { error: "Type a word or phrase." });
  assert.deepEqual(addWord([], "x".repeat(41)), { error: "Keep it to 40 characters or fewer." });
  assert.deepEqual(addWord([], "x".repeat(40)), { list: ["x".repeat(40)] });
  assert.deepEqual(addWord(["synergy"], "SYNERGY"), { error: "That's already on this list." });
  const full = Array.from({ length: WORD_LIST_MAX }, (_, i) => `w${i}`);
  assert.deepEqual(addWord(full, "new"), { error: "This list is full (200). Remove one first." });
});

test("withIgnored adds the lower-cased subject to Never flag and keeps the bank", () => {
  const wording = {
    cliche: ["synergy"],
    filler: ["very"],
    ignored: ["dynamic"],
    defaults: { cliche: [], filler: [] },
  };
  assert.deepEqual(withIgnored(wording, " Teh "), {
    cliche: ["synergy"],
    filler: ["very"],
    ignored: ["dynamic", "teh"],
  });
  // Already there: the list is unchanged, not doubled.
  assert.deepEqual(withIgnored(wording, "Dynamic").ignored, ["dynamic"]);
});

test("canIgnore offers Ignore only for a subject Never flag can hold", () => {
  assert.equal(canIgnore("teh"), true);
  assert.equal(canIgnore("  "), false);
  assert.equal(canIgnore(undefined), false);
  assert.equal(canIgnore("x".repeat(41)), false);
});

test("bulletEditOp replaces the summary or one bullet, hash-guarded when it has a hash", () => {
  assert.deepEqual(bulletEditOp({ section: "summary" }, "New summary.", "h1"), {
    kind: "replace_summary",
    value: "New summary.",
    expected_content_hash: "h1",
  });
  assert.deepEqual(bulletEditOp({ section: "projects", index: 0, bullet_index: 3 }, "New bullet.", "h2"), {
    kind: "replace_bullet",
    section: "projects",
    index: 0,
    bullet_index: 3,
    value: "New bullet.",
    expected_content_hash: "h2",
  });
  // No hash (an older report): the write goes unguarded rather than sending null.
  assert.equal("expected_content_hash" in bulletEditOp({ section: "summary" }, "x", null), false);
  assert.equal("expected_content_hash" in bulletEditOp({ section: "summary" }, "x"), false);
});

test("withDraft commits a typed-but-unadded word on Save, and refuses an invalid one", () => {
  assert.deepEqual(withDraft(["synergy"], "  "), { list: ["synergy"] });
  assert.deepEqual(withDraft(["synergy"], " Go-Getter "), { list: ["synergy", "go-getter"] });
  assert.deepEqual(withDraft(["synergy"], "Synergy"), { error: "That's already on this list." });
  assert.deepEqual(withDraft([], "x".repeat(41)), { error: "Keep it to 40 characters or fewer." });
});
