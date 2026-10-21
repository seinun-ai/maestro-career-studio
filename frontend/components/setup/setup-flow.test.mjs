// Setup rendered with seeded reads (design refresh, Task 7.1). pytest runs it:
// backend/tests/test_frontend_setup_flow.py.
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

import { React, load, withRouter } from "../render-harness.mjs";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server");
const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");

const { SetupFlow } = load("components/setup/setup-flow.tsx");
const { SetupDone } = load("components/setup/setup-done.tsx");
const { SetupAnswersStep } = load("components/setup/setup-answers-step.tsx");
const { formQuestions, stepsDone } = load("lib/setup-flow.ts");

// The one filled button's classes (components/ui/button.tsx, variant "default").
const FILLED = /bg-primary text-primary-foreground/g;

const MARKETS = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false },
];

const step = (done) => ({ done, detail: {} });
const STATUS = {
  model_key: step(false),
  import_resumes: { done: false, detail: { base_resumes: 0, kb_entities: 0 } },
  autofill: { done: false, readiness: 0, groups: {}, blocking: ["work_auth"], work_auth_by_country: {} },
  job_preferences: step(false),
  persona: step(false),
  template: { done: false, detail: {} },
  engines: { pdflatex: { available: true, warning: null }, typst: { available: true, warning: null } },
  suggested_bases: [],
  complete: false,
};
const INFO = {
  fast_model: "gpt-5.6-luna",
  smart_model: "gpt-5.6-luna",
  chat_model: "gpt-5.6-luna",
  reasoning_model: "gpt-6.1-sol",
  api_key_configured: false,
  gemini_api_key_configured: false,
  anthropic_api_key_configured: false,
  openrouter_api_key_configured: false,
  openai_key_source: "none",
  gemini_key_source: "none",
  anthropic_key_source: "none",
  openrouter_key_source: "none",
  model_options: [],
  base_url: null,
  custom_endpoint: false,
  json_mode: "auto",
  capabilities: {},
};
const market = (applyIn = ["DE"]) => ({
  key: "market",
  value: { home: "DE", apply_in: applyIn, market: "DE" },
  home: "DE",
  apply_in: applyIn,
  markets: MARKETS,
  currency: "EUR",
  offers_eeo: false,
});
const PREFS = {
  favored_roles: [],
  role_categories: [],
  years_experience: null,
  employment_types: [],
  locations: [],
  remote: "hybrid",
  min_salary: null,
  notes: null,
};
const PERMITS = { authorized_now: true, sponsorship_now: false, sponsorship_future: false };

function render({ status = STATUS, info = INFO, applyIn = ["DE"], profile = {} } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
  client.setQueryData(["setup-status"], status);
  client.setQueryData(["settings", "openai"], info);
  client.setQueryData(["settings", "market"], market(applyIn));
  client.setQueryData(["settings", "job-preferences"], { key: "job_preferences", value: PREFS });
  client.setQueryData(["settings", "autofill"], { key: "autofill_profile", value: profile });
  client.setQueryData(["settings", "money"], {
    key: "money",
    value: { home_currency: null, period: "year", hours_per_year: 2080, show_posted: true },
    home_currency: "EUR",
  });
  const html = renderToStaticMarkup(
    React.createElement(QueryClientProvider, { client }, withRouter(React.createElement(SetupFlow))),
  );
  client.clear();
  return html;
}

const KEYED = { ...STATUS, model_key: step(true) };
const IMPORTED = { ...KEYED, import_resumes: { done: true, detail: { base_resumes: 2, kb_entities: 40 } } };
const WANTED = { ...IMPORTED, job_preferences: step(true) };

test("a new install opens on the AI model: five providers in words, no image, one filled Continue", () => {
  const html = render();
  assert.match(html, /<h1[^>]*>Setup<\/h1>/);
  assert.match(html, /Pick the AI that does the writing/);
  for (const name of ["Claude", "OpenAI", "Gemini", "OpenRouter", "Your own server"]) assert.match(html, new RegExp(`>${name}<`));
  assert.doesNotMatch(html, /<img/);
  // The rail: four steps, each with its time, the first current, and the progress bar.
  assert.match(html, /role="progressbar"[^>]*aria-valuenow="0"/);
  assert.match(html, /0 of 4 done/);
  for (const [title, time] of [["AI model", "1 minute"], ["Your resume", "2 minutes"], ["Where and what", "1 minute"], ["Form answers", "2 minutes"]]) {
    assert.match(html, new RegExp(`${title}</span><span[^>]*>${time}<`));
  }
  assert.match(html, /aria-current="step"[^>]*>.*?AI model/s);
  // Skip for now, and no Back before the first step.
  assert.match(html, />Skip for now</);
  assert.doesNotMatch(html, />Back</);
  assert.equal((html.match(FILLED) ?? []).length, 1);
  assert.match(html, /bg-primary text-primary-foreground[^>]*>Continue</);
});

test("a saved key opens the resume step: one drop zone, Back and Skip for now", () => {
  const html = render({ status: KEYED, info: { ...INFO, anthropic_api_key_configured: true, anthropic_key_source: "settings" } });
  assert.match(html, /Bring your resume/);
  assert.equal((html.match(/type="file"/g) ?? []).length, 1);
  assert.match(html, />Back</);
  assert.match(html, />Skip for now</);
  assert.match(html, /1 of 4 done/);
  assert.match(html, /AI model<\/span><span[^>]*>Done</);
});

test("then where and what: where you live, where you apply as chips, roles and work mode", () => {
  const html = render({ status: IMPORTED, applyIn: ["DE", "UK"] });
  assert.match(html, /Where and what you&#x27;re looking for/);
  assert.match(html, /You live in/);
  assert.match(html, /Pay shows in EUR\./);
  assert.match(html, /aria-pressed="true"[^>]*>.*?Germany</s);
  assert.match(html, /aria-pressed="true"[^>]*>.*?United Kingdom</s);
  assert.match(html, /aria-pressed="false"[^>]*>United States</);
  assert.match(html, /2 countries, each with its own work-permit/);
  assert.match(html, /Roles you want/);
  assert.match(html, /Work mode/);
  assert.match(html, /aria-pressed="true"[^>]*>.*?Hybrid</s);
  assert.match(html, />Skip for now</);
});

test("then form answers, one at a time: the first country's work permit, named", () => {
  const html = render({ status: WANTED, applyIn: ["DE", "UK"] });
  assert.match(html, /Answers every job form asks/);
  // Two permits, notice, relocation, and diversity for the United Kingdom's checked set.
  assert.match(html, /1 of 5/);
  assert.match(html, /Work permit/);
  assert.match(html, /<h3 id="([^"]+)"[^>]*>Germany<\/h3>/);
  const country = /<h3 id="([^"]+)"[^>]*>Germany<\/h3>/.exec(html)[1];
  // Each question's answer group is named by the country first, then the question.
  for (const label of ["Can you work there now?", "Do you need visa sponsorship now?", "Will you need visa sponsorship later?"]) {
    const q = new RegExp(`<span id="([^"]+)"[^>]*>${label.replace("?", "\\?")}</span>`).exec(html);
    assert.ok(q, label);
    assert.match(html, new RegExp(`role="group" aria-labelledby="${country} ${q[1]}"`));
  }
  assert.doesNotMatch(html, /United Kingdom<\/h3>/);
  assert.match(html, />Skip for now</);
});

test("every step done opens the first again, all four marked", () => {
  const html = render({ status: WANTED, applyIn: ["DE"], profile: { work_auth_by_country: { DE: PERMITS } } });
  assert.match(html, /All 4 done/);
  assert.match(html, /Pick the AI that does the writing/);
});

function renderElement(element) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const html = renderToStaticMarkup(React.createElement(QueryClientProvider, { client }, withRouter(element)));
  client.clear();
  return html;
}

test("diversity: only for a country with a set, named, answered or declined, nothing saved here", () => {
  const without = formQuestions(["DE"], MARKETS);
  assert.equal(without.some((q) => q.kind === "diversity"), false);
  const questions = formQuestions(["DE", "UK", "US"], MARKETS);
  const html = renderElement(
    React.createElement(SetupAnswersStep, {
      profile: {},
      status: WANTED,
      questions,
      question: questions.length - 1,
      onQuestion: () => {},
      onDone: () => {},
      diversity: null,
      onDiversity: () => {},
      headingRef: { current: null },
    }),
  );
  assert.match(html, /Diversity questions on forms/);
  assert.match(html, /United Kingdom and United States/);
  assert.match(html, />Answer them</);
  assert.match(html, />Decline to answer</);
  assert.match(html, /Setup saves nothing here/);
});

test("the done screen: Add your first job filled, the agent app and the Companion beside it", () => {
  const questions = formQuestions(["DE"], MARKETS);
  const done = stepsDone(WANTED, { work_auth_by_country: { DE: PERMITS } }, ["DE"]);
  const html = renderElement(
    React.createElement(SetupDone, {
      status: WANTED,
      done,
      profile: { personal: { first_name: "Lena" }, work_auth_by_country: { DE: PERMITS } },
      questions,
      diversity: "answer",
      headingRef: { current: null },
      go: () => {},
    }),
  );
  assert.match(html, /You&#x27;re set, Lena/);
  assert.equal((html.match(FILLED) ?? []).length, 1);
  assert.match(html, /<a[^>]*href="\/new"[^>]*bg-primary text-primary-foreground[^>]*>Add your first job<\/a>|<a[^>]*bg-primary text-primary-foreground[^>]*href="\/new"[^>]*>Add your first job<\/a>/);
  assert.match(html, /href="\/settings\?tab=agents"[^>]*>.*?Connect an agent app/s);
  assert.match(html, /href="https:\/\/github\.com\/[^"]+GETTING_STARTED\.md#4-the-companion-browser-extension-optional"[^>]*target="_blank"[^>]*>.*?Add the Companion/s);
  // Chose to answer diversity: where to do it, beside its consent.
  assert.match(html, /href="\/profile\?tab=autofill#autofill-eeo"[^>]*>Answer the diversity questions/);
  // Open required steps say so instead of "You're set".
  const early = renderElement(
    React.createElement(SetupDone, {
      status: STATUS,
      done: stepsDone(STATUS, {}, ["DE"]),
      profile: {},
      questions,
      diversity: null,
      headingRef: { current: null },
      go: () => {},
    }),
  );
  assert.match(early, /Almost there/);
  assert.match(early, /Not done yet/);
  assert.doesNotMatch(early, /You&#x27;re set/);
  assert.doesNotMatch(early, /diversity/);
});
