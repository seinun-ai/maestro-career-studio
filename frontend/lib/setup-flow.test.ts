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
  progressWords,
  stepsDone,
  checkVerdict,
  movesOnUnchecked,
  refusedWords,
} from "./setup-flow.ts";

const MARKETS = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true, work_auth_vocab: "us_visa" },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true, work_auth_vocab: "uk" },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false, work_auth_vocab: "generic" },
  { key: "IE", label: "Ireland", country_code: "IE", currency: "EUR", date_format: "DMY", offers_eeo: false, work_auth_vocab: "generic" },
];

// A small set in the served shape (GET /api/settings/autofill/questions): citizenship in personal, then each
// country you apply in, in its order. A node-tested lib file builds its own; components/setup/setup-flow.test.mjs
// renders the served fixtures.
const CITIZEN_OF = { key: "citizenships", label: "Citizen of", type: "countries" as const };
const served = (markets: string[], { citizenship = true, offersEeo = true } = {}) =>
  ({
    groups: [{ key: "personal", title: "Personal details", fields: citizenship ? [CITIZEN_OF] : [] }],
    countries: markets.map((market) => ({
      market,
      label: MARKETS.find((m) => m.key === market)?.label ?? market,
      permits: [],
      answers: [],
    })),
    offers_eeo: offersEeo,
    chosen: markets.length > 0,
  }) as never;

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
  // Setup status counts each country's work-permit answers in its own words (the US visa status too), and
  // citizenship beside them in the work-permit group.
  const counted = (
    byCountry: Record<string, { answered: number; answerable: number }>,
    citizenship = { answered: 1, answerable: 1 },
  ) => {
    const all = [citizenship, ...Object.values(byCountry)];
    const sum = (key: "answered" | "answerable") => all.reduce((n, g) => n + g[key], 0);
    return {
      autofill: {
        done: false,
        readiness: 0,
        groups: { work_auth: { answered: sum("answered"), answerable: sum("answerable") } },
        blocking: [],
        work_auth_by_country: byCountry,
      },
    };
  };
  assert.deepEqual(stepsDone(status(), served(["DE"])), { model: false, resume: false, where: false, answers: false });
  assert.deepEqual(
    stepsDone(
      status({ model_key: step(true), import_resumes: step(true), job_preferences: step(true), ...counted({ DE: { answered: 3, answerable: 3 } }) }),
      served(["DE"]),
    ),
    { model: true, resume: true, where: true, answers: true },
  );
  // A second country with answers left, the US visa status say, keeps the form answers open.
  const two = counted({ DE: { answered: 3, answerable: 3 }, US: { answered: 3, answerable: 4 } });
  assert.equal(stepsDone(status(two), served(["DE", "US"])).answers, false);
  assert.equal(stepsDone(status(two), served(["DE", "UK"])).answers, false, "a country the status has not counted is open");
  // Citizenship is the one other answer the step needs.
  const noCitizenship = counted({ DE: { answered: 3, answerable: 3 } }, { answered: 0, answerable: 1 });
  assert.equal(stepsDone(status(noCitizenship), served(["DE"])).answers, false);
});

test("with no country chosen, the form answers need only citizenship, never the default country's permits", () => {
  // Unchosen, the market still stores the US, but the set serves no country and readiness counts none.
  const unchosen = (answered: number) =>
    status({
      autofill: {
        done: false,
        readiness: 0,
        groups: { work_auth: { answered, answerable: 1 } },
        blocking: [],
        work_auth_by_country: {},
      },
    });
  assert.equal(stepsDone(unchosen(1), served([])).answers, true);
  assert.equal(stepsDone(unchosen(0), served([])).answers, false);
});

test("where and what is done only once the countries are chosen, job preferences or not", () => {
  // Unchosen, readiness can read complete while every form pauses on the permits no country asks.
  const wanted = status({ job_preferences: step(true) });
  assert.equal(stepsDone(wanted, served([])).where, false);
  assert.equal(stepsDone(wanted, served(["DE"])).where, true);
  assert.equal(stepsDone(status(), served(["DE"])).where, false);
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

test("form questions: citizenship, then one work permit per country served, named, then notice and relocation", () => {
  const qs = formQuestions(served(["DE", "IE"]), MARKETS);
  assert.deepEqual(qs, [
    { kind: "citizenship" },
    { kind: "permit", market: "DE", label: "Germany" },
    { kind: "permit", market: "IE", label: "Ireland" },
    { kind: "notice" },
    { kind: "relocate" },
  ]);
  // The countries and their names are the served set's, in its order, never the market list's.
  const lagging = { ...(served(["IE"]) as object), countries: [{ market: "XX", label: "Elsewhere", permits: [], answers: [] }] };
  assert.deepEqual(formQuestions(lagging as never, MARKETS)[1], { kind: "permit", market: "XX", label: "Elsewhere" });
  // A set that does not ask citizenship starts at the first country.
  assert.deepEqual(formQuestions(served(["DE"], { citizenship: false }), MARKETS)[0], { kind: "permit", market: "DE", label: "Germany" });
});

test("with no country chosen: citizenship, notice and relocation, and no work permit", () => {
  assert.deepEqual(formQuestions(served([], { offersEeo: false }), MARKETS), [
    { kind: "citizenship" },
    { kind: "notice" },
    { kind: "relocate" },
  ]);
});

test("diversity is asked only for the countries with a checked set, and names them", () => {
  assert.equal(formQuestions(served(["DE"], { offersEeo: false }), MARKETS).some((q) => q.kind === "diversity"), false);
  const qs = formQuestions(served(["DE", "UK", "US"]), MARKETS);
  assert.deepEqual(qs.at(-1), { kind: "diversity", countries: ["United Kingdom", "United States"] });
  assert.equal(qs.filter((q) => q.kind === "permit").length, 3);
  // The served set decides: one that offers no checked set asks none, whatever the market list says.
  assert.equal(formQuestions(served(["UK"], { offersEeo: false }), MARKETS).some((q) => q.kind === "diversity"), false);
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

test("a check passes only when the model was reached and writes; a refusal and a check that never ran differ", () => {
  const report = { model: "m", base_url: null, text: true, json: true, tools: false, errors: {}, checked_at: "" };
  assert.equal(checkVerdict(report, false, false), "passed");
  assert.equal(checkVerdict({ ...report, reachable: false }, true, false), "refused");
  assert.equal(checkVerdict({ ...report, reachable: false }, false, false), "unchecked");
  // Your own server never reached is a failed check of its address, not a check that could not run.
  assert.equal(checkVerdict({ ...report, reachable: false }, false, true), "failed");
  assert.equal(checkVerdict({ ...report, text: false }, false, false), "failed");
  assert.equal(checkVerdict(report, true, false), "refused");
});

test("Save and continue moves on unchecked only when untouched, set, and the last check did not fail", () => {
  assert.equal(movesOnUnchecked(true, true, null), true);
  assert.equal(movesOnUnchecked(true, true, "passed"), true);
  // The check could not run: the key is saved and the same button now moves on.
  assert.equal(movesOnUnchecked(true, true, "unchecked"), true);
  // After a failed or refused check, the next press checks again, key set or not.
  assert.equal(movesOnUnchecked(true, true, "failed"), false);
  assert.equal(movesOnUnchecked(true, true, "refused"), false);
  assert.equal(movesOnUnchecked(false, true, null), false);
  assert.equal(movesOnUnchecked(true, false, null), false);
});

test("a refused key says it was not saved, what that left, and to paste it again, never Settings", () => {
  const none = refusedWords("OpenAI", true, false, false);
  assert.equal(none, "OpenAI refused this key, so it wasn't saved. Check the key and paste it again.");
  assert.equal(
    refusedWords("OpenAI", true, true, false),
    "OpenAI refused this key, so it wasn't saved. It had replaced your earlier key, so no OpenAI key is saved now. Check the key and paste it again.",
  );
  assert.match(refusedWords("OpenAI", true, true, true), /The key set outside the app is used again\./);
  assert.equal(refusedWords("Gemini", false, true, true), "Gemini refused your saved key. Check the key and paste it again.");
  for (const words of [none, refusedWords("OpenAI", true, true, false), refusedWords("OpenAI", false, true, true)]) {
    assert.doesNotMatch(words, /Settings/);
  }
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
