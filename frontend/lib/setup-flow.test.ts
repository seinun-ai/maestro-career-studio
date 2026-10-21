import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SETUP_STEPS,
  firstOpenStep,
  formQuestions,
  importCounts,
  modelPlan,
  opensSetup,
  planWords,
  preference,
  progressWords,
  stepsDone,
  testPassed,
} from "./setup-flow.ts";

const MARKETS = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true, work_auth_vocab: "us_visa" },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true, work_auth_vocab: "uk" },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false, work_auth_vocab: "generic" },
  { key: "IE", label: "Ireland", country_code: "IE", currency: "EUR", date_format: "DMY", offers_eeo: false, work_auth_vocab: "generic" },
];

const step = (done: boolean) => ({ done, detail: {} });
const status = (over: Record<string, unknown> = {}) =>
  ({
    model_key: step(false),
    import_resumes: step(false),
    autofill: { done: false, readiness: 0, groups: {}, blocking: ["work_auth"], work_auth_by_country: {} },
    job_preferences: step(false),
    persona: step(false),
    template: step(false),
    engines: { pdflatex: {}, typst: {} },
    suggested_bases: [],
    complete: false,
    ...over,
  }) as never;

test("four steps, each with a time", () => {
  assert.deepEqual(
    SETUP_STEPS.map((s) => [s.id, s.title, s.time]),
    [
      ["model", "AI model", "1 minute"],
      ["resume", "Your resume", "2 minutes"],
      ["where", "Where and what", "1 minute"],
      ["answers", "Form answers", "2 minutes"],
    ],
  );
});

test("a step is done from the data it writes, never from a visit", () => {
  // Setup status counts each country's work-permit answers in its own words (the US visa status too).
  const counted = (byCountry: Record<string, { answered: number; answerable: number }>) => ({
    autofill: { done: false, readiness: 0, groups: {}, blocking: [], work_auth_by_country: byCountry },
  });
  assert.deepEqual(stepsDone(status(), ["DE"]), { model: false, resume: false, where: false, answers: false });
  assert.deepEqual(
    stepsDone(
      status({ model_key: step(true), import_resumes: step(true), job_preferences: step(true), ...counted({ DE: { answered: 3, answerable: 3 } }) }),
      ["DE"],
    ),
    { model: true, resume: true, where: true, answers: true },
  );
  // A second country with answers left, the US visa status say, keeps the form answers open.
  const two = counted({ DE: { answered: 3, answerable: 3 }, US: { answered: 3, answerable: 4 } });
  assert.equal(stepsDone(status(two), ["DE", "US"]).answers, false);
  assert.equal(stepsDone(status(two), ["DE", "UK"]).answers, false, "a country the status has not counted is open");
});

test("setup opens on the first step not done, and on the first one when all are", () => {
  assert.equal(firstOpenStep({ model: false, resume: false, where: false, answers: false }), 0);
  assert.equal(firstOpenStep({ model: true, resume: false, where: false, answers: false }), 1);
  assert.equal(firstOpenStep({ model: true, resume: true, where: true, answers: false }), 3);
  assert.equal(firstOpenStep({ model: true, resume: true, where: true, answers: true }), 0);
});

test("the progress line counts done steps", () => {
  assert.equal(progressWords(0), "0 of 4 done");
  assert.equal(progressWords(3), "3 of 4 done");
  assert.equal(progressWords(4), "All 4 done");
});

test("a brand-new install opens setup once; a returning user never", () => {
  assert.equal(opensSetup(status(), false), true);
  // Seen once (skipped or finished): Today stays Today.
  assert.equal(opensSetup(status(), true), false);
  // A key or a resume is not a first launch.
  assert.equal(opensSetup(status({ model_key: step(true) }), false), false);
  assert.equal(opensSetup(status({ import_resumes: step(true) }), false), false);
});

test("form questions: one work permit per country you apply in, named, then notice and relocation", () => {
  const qs = formQuestions(["DE", "IE"], MARKETS);
  assert.deepEqual(qs, [
    { kind: "permit", market: "DE", label: "Germany", vocab: "generic" },
    { kind: "permit", market: "IE", label: "Ireland", vocab: "generic" },
    { kind: "notice" },
    { kind: "relocate" },
  ]);
  // Each country carries its own work-permit wording from the market list.
  assert.equal((formQuestions(["US"], MARKETS)[0] as { vocab?: string }).vocab, "us_visa");
  // A market the list lacks still carries its key, never nothing (and no wording: generic).
  assert.deepEqual(formQuestions(["XX"], MARKETS)[0], { kind: "permit", market: "XX", label: "XX", vocab: undefined });
});

test("diversity is asked only for the countries with a checked set, and names them", () => {
  assert.equal(formQuestions(["DE"], MARKETS).some((q) => q.kind === "diversity"), false);
  const qs = formQuestions(["DE", "UK", "US"], MARKETS);
  assert.deepEqual(qs.at(-1), { kind: "diversity", countries: ["United Kingdom", "United States"] });
  assert.equal(qs.filter((q) => q.kind === "permit").length, 3);
});

test("a preference reads as stored: text, or a yes or no as typed", () => {
  assert.equal(preference({ preferences: { notice_period: "1 month" } }, "notice_period"), "1 month");
  assert.equal(preference({ preferences: { willing_to_relocate: "Yes" } }, "willing_to_relocate"), true);
  assert.equal(preference({}, "willing_to_relocate"), undefined);
});

const REC = {
  on: false,
  provider: null,
  active_provider: null,
  models: null,
  own: { fast: "gpt-5.6-luna", smart: "gpt-5.6-luna", assistant: "gpt-5.6-luna", reasoning: "gpt-6.1-sol" },
  sets: {
    openai: { fast: "gpt-5.6-luna", smart: "gpt-5.6-luna", assistant: "gpt-5.6-luna", reasoning: "gpt-6.1-sol" },
    anthropic: { fast: "claude-haiku-5-5", smart: "claude-sonnet-5-5", assistant: "claude-haiku-5-5", reasoning: "claude-sonnet-5-5" },
  },
} as const;
const OPTIONS = [
  { id: "gpt-5.6-luna", provider: "openai" },
  { id: "gpt-6.1-sol", provider: "openai" },
  { id: "claude-haiku-5-5", provider: "anthropic" },
  { id: "claude-sonnet-5-5", provider: "anthropic" },
  { id: "or-model", provider: "openrouter" },
];

test("a new key gets its provider's recommended set, unless your own picks already run on it", () => {
  // Own picks on another provider: the set is turned on for this one, and its Assistant model is tested.
  assert.deepEqual(modelPlan("anthropic", REC as never, OPTIONS), {
    kind: "recommended",
    test: "claude-haiku-5-5",
    change: { on: true, provider: "anthropic" },
  });
  // Own picks already on OpenAI: they stay, and recommended is not turned on.
  assert.deepEqual(modelPlan("openai", REC as never, OPTIONS), { kind: "own", test: "gpt-5.6-luna", change: null });
  // Recommended already on for this provider: nothing changes.
  const on = { ...REC, on: true, provider: "anthropic", active_provider: "anthropic", models: REC.sets.anthropic };
  assert.deepEqual(modelPlan("anthropic", on as never, OPTIONS), { kind: "recommended", test: "claude-haiku-5-5", change: null });
  // Own picks on this provider while recommended answers another: off, so your picks answer again.
  assert.deepEqual(modelPlan("openai", on as never, OPTIONS), { kind: "own", test: "gpt-5.6-luna", change: { on: false } });
});

test("a provider with no set keeps your picks and tests one of its own models", () => {
  assert.deepEqual(modelPlan("openrouter", REC as never, OPTIONS), { kind: "pick", test: "or-model", change: null });
  assert.deepEqual(modelPlan("openrouter", REC as never, OPTIONS.slice(0, 4)), { kind: "pick", test: null, change: null });
});

test("a passed test says what it chose", () => {
  assert.equal(
    planWords({ kind: "recommended", test: "claude-haiku-5-5", change: null }, "Claude"),
    "The recommended Claude models are picked for you. Change them in Settings any time.",
  );
  assert.equal(planWords({ kind: "own", test: "gpt-5.6-luna", change: null }, "OpenAI"), "Your own model picks stay. Change them in Settings any time.");
  assert.equal(
    planWords({ kind: "server", test: "llama3.3", change: null }, "Your own server"),
    "Every job uses llama3.3 on your server. Change it in Settings any time.",
  );
  assert.equal(
    planWords({ kind: "pick", test: null, change: null }, "OpenRouter"),
    "OpenRouter has no recommended models yet. Pick a model for each job in Settings.",
  );
});

test("a test passes only when the model was reached and writes", () => {
  const report = { model: "m", base_url: null, text: true, json: true, tools: false, errors: {}, checked_at: "" };
  assert.equal(testPassed(report, false), true);
  assert.equal(testPassed({ ...report, reachable: false }, false), false);
  assert.equal(testPassed({ ...report, text: false }, false), false);
  assert.equal(testPassed(report, true), false);
});


test("the import's counts come from its response, and only the ones it has", () => {
  const bases = [{ slug: "a" }, { slug: "b" }] as never;
  assert.deepEqual(importCounts({ bases, skipped: [], kb: null }), [{ n: 2, words: "base resumes" }]);
  assert.deepEqual(
    importCounts({
      bases,
      skipped: [],
      kb: { entities_created: 5, entities_matched: 1, points_approved: 23, points_draft: 0, skills_items_added: ["SQL", "Figma"] },
    }),
    [
      { n: 2, words: "base resumes" },
      { n: 5, words: "new items in your career history" },
      { n: 23, words: "bullets" },
      { n: 2, words: "skills" },
    ],
  );
  // An older response without the extra counts shows what it has.
  assert.deepEqual(
    importCounts({ bases: [{ slug: "a" }] as never, skipped: [], kb: { entities_created: 1, points_approved: 1, points_draft: 3 } }),
    [
      { n: 1, words: "base resume" },
      { n: 1, words: "new item in your career history" },
      { n: 1, words: "bullet" },
      { n: 3, words: "draft bullets to review" },
    ],
  );
});
