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
const { questionAnswered, withDiversityDeclined, withPermitAnswer, withPreference } = load("lib/setup-answers.ts");

// The one filled button's classes (components/ui/button.tsx, variant "default").
const FILLED = /bg-primary text-primary-foreground/g;

const MARKETS = [
  { key: "US", label: "United States", country_code: "US", currency: "USD", date_format: "MDY", offers_eeo: true, work_auth_vocab: "us_visa" },
  { key: "UK", label: "United Kingdom", country_code: "GB", currency: "GBP", date_format: "DMY", offers_eeo: true, work_auth_vocab: "uk" },
  { key: "DE", label: "Germany", country_code: "DE", currency: "EUR", date_format: "DMY", offers_eeo: false, work_auth_vocab: "generic" },
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

const CONSENT_OFF = { enabled: false, consent_forms: false, acknowledged_at: null, policy_version: "2" };
const CONSENT_ON = { ...CONSENT_OFF, enabled: true, acknowledged_at: "2026-10-20T09:00:00Z" };

function render({ status = STATUS, info = INFO, applyIn = ["DE"], profile = {} } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
  client.setQueryData(["setup-status"], status);
  client.setQueryData(["settings", "openai"], info);
  client.setQueryData(["settings", "market"], market(applyIn));
  client.setQueryData(["settings", "job-preferences"], { key: "job_preferences", value: PREFS });
  client.setQueryData(["settings", "autofill"], { key: "autofill_profile", value: profile });
  client.setQueryData(["settings", "eeo-consent"], { key: "eeo_consent", value: CONSENT_OFF });
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
// Setup status counts each country's work-permit answers in its own words.
const PERMITTED = { ...WANTED, autofill: { ...STATUS.autofill, work_auth_by_country: { DE: { answered: 3, answerable: 3 } } } };

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
  // Each question's answer group is named by the country first, then the question, in Germany's words.
  for (const label of ["Can you work in this country now?", "Do you need visa sponsorship now?", "Will you need visa sponsorship later?"]) {
    const q = new RegExp(`<span id="([^"]+)"[^>]*>${label.replace("?", "\\?")}</span>`).exec(html);
    assert.ok(q, label);
    assert.match(html, new RegExp(`role="group" aria-labelledby="${country} ${q[1]}"`));
  }
  assert.doesNotMatch(html, /United Kingdom<\/h3>/);
  assert.doesNotMatch(html, /Work authorization status/, "the visa status is the US's only");
  // No link to another country's set (the old one edited the home country's).
  assert.doesNotMatch(html, /Answer in Profile/);
  assert.match(html, />Skip for now</);
});

test("the United States asks its visa status too, named by the country and the question", () => {
  const html = render({ status: WANTED, applyIn: ["US"] });
  const country = /<h3 id="([^"]+)"[^>]*>United States<\/h3>/.exec(html)[1];
  const q = /<span id="([^"]+)"[^>]*>Work authorization status<\/span>/.exec(html);
  assert.ok(q);
  assert.match(html, new RegExp(`aria-labelledby="${country} ${q[1]}"`));
  assert.match(html, /Authorized to work in the U\.S\. now\?/);
});

test("the United Kingdom is asked in its own words", () => {
  const html = render({ status: WANTED, applyIn: ["UK"] });
  assert.match(html, /Do you have the right to work in the UK now\?/);
  assert.doesNotMatch(html, /Work authorization status/);
});

test("every step done opens the first again, all four marked", () => {
  const html = render({ status: PERMITTED, applyIn: ["DE"], profile: { work_auth_by_country: { DE: PERMITS } } });
  assert.match(html, /All 4 done/);
  assert.match(html, /Pick the AI that does the writing/);
});

function renderElement(element, seed = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, data] of seed) client.setQueryData(key, data);
  const html = renderToStaticMarkup(React.createElement(QueryClientProvider, { client }, withRouter(element)));
  client.clear();
  return html;
}

const answersStep = (props, seed = []) =>
  renderElement(
    React.createElement(SetupAnswersStep, {
      profile: {},
      consent: CONSENT_OFF,
      onQuestion: () => {},
      onDone: () => {},
      diversity: null,
      onDiversity: () => {},
      headingRef: { current: null },
      ...props,
    }),
    seed,
  );

test("diversity: only for a country with a set, named, and nothing stored before the consent", () => {
  const without = formQuestions(["DE"], MARKETS);
  assert.equal(without.some((q) => q.kind === "diversity"), false);
  const questions = formQuestions(["DE", "UK", "US"], MARKETS);
  const html = answersStep({ questions, question: questions.length - 1 });
  assert.match(html, /Diversity questions on forms/);
  assert.match(html, /United Kingdom, United States/);
  assert.match(html, />Answer them</);
  // Decline fills only the blank questions that have a decline choice: race or ethnicity is typed, and stays yours.
  assert.match(html, />Decline the rest</);
  assert.doesNotMatch(html, /Decline them all/);
  assert.match(html, /Race or ethnicity has no decline choice, so it stays yours to answer\./);
  assert.match(html, /Nothing is saved until you allow it\./);
  // No question to answer, and no choice shown picked, until the consent is on record.
  assert.doesNotMatch(html, /Are you a veteran\?/);
  assert.doesNotMatch(html, /aria-pressed="true"/);
  // With the consent on record and Answer them picked: the questions in place, the switch and its date beside them.
  const answering = answersStep({ questions, question: questions.length - 1, consent: CONSENT_ON, diversity: "answer" });
  assert.match(answering, /Are you a veteran\?/);
  assert.match(answering, /Let the Companion fill these answers/);
  assert.match(answering, /role="switch"[^>]*aria-checked="true"/);
  assert.match(answering, /You agreed on/);
  assert.ok(answering.indexOf("Let the Companion fill these answers") < answering.indexOf("Are you a veteran?"), "the switch above the answers");
});

test("a dot is green only for a question that holds its answer, never one passed or skipped", () => {
  const questions = formQuestions(["DE", "UK"], MARKETS);
  const dots = (html) => [...html.matchAll(/<span class="size-1\.5 rounded-full ([^"]+)"><\/span>/g)].map((m) => m[1]);
  // On the notice question, both work permits passed by unanswered: neither is green.
  assert.deepEqual(dots(answersStep({ questions, question: 2 })), [
    "bg-surface-container-high", "bg-surface-container-high", "bg-primary", "bg-surface-container-high", "bg-surface-container-high",
  ]);
  const answered = answersStep({ questions, question: 2, profile: { work_auth_by_country: { DE: PERMITS } } });
  assert.deepEqual(dots(answered).slice(0, 2), ["bg-success", "bg-surface-container-high"]);
});

test("contact fields fill from career history in place, and say why they cannot", () => {
  const questions = formQuestions(["DE"], MARKETS);
  const ready = answersStep({ questions, question: 0 }, [[["kb", "profile"], { contact: { name: "Lena Vogel", email: "lena@example.com" } }]]);
  assert.match(ready, /<button[^>]*>Fill from career history<\/button>/);
  assert.doesNotMatch(ready, /aria-disabled="true"[^>]*>Fill from career history/);
  assert.doesNotMatch(ready, /href="\/profile#autofill-personal"/);
  const empty = answersStep({ questions, question: 0 }, [[["kb", "profile"], { contact: {} }]]);
  assert.match(empty, /Add your contact details to your career history first\./);
  // Once the email is in, the line goes.
  const filled = answersStep({ questions, question: 0, profile: { personal: { email: "lena@example.com" } } });
  assert.doesNotMatch(filled, /Fill from career history/);
});

test("what Setup writes: each answer on its own country, never the one-set view", () => {
  const before = {
    personal: { first_name: "Lena" },
    work_auth: { authorized_now: true },
    work_auth_by_country: { DE: { authorized_now: true, status: "citizen" }, UK: { authorized_now: false } },
  };
  const after = withPermitAnswer(before, "UK", "sponsorship_now", true);
  assert.deepEqual(after.work_auth_by_country, {
    DE: { authorized_now: true, status: "citizen" },
    UK: { authorized_now: false, sponsorship_now: true },
  });
  assert.equal("work_auth" in after, false);
  assert.deepEqual(before.work_auth_by_country.UK, { authorized_now: false }, "the input is not changed");
  assert.deepEqual(withPermitAnswer({}, "US", "status", "citizen"), { work_auth_by_country: { US: { status: "citizen" } } });
  const prefs = withPreference({ preferences: { desired_salary: "80k" }, work_auth: {} }, "notice_period", "1 month");
  assert.deepEqual(prefs, { preferences: { desired_salary: "80k", notice_period: "1 month" } });
  // Declining fills each blank diversity question with its decline choice, the veteran one too, and leaves
  // race or ethnicity (typed, with no decline choice) blank.
  assert.deepEqual(withDiversityDeclined({ eeo: { gender: "female" } }).eeo, {
    gender: "female", veteran_status: "decline", disability_status: "decline", hispanic_latino: "decline",
  });
  assert.equal("race_ethnicity" in withDiversityDeclined({}).eeo, false);
  assert.equal(questionAnswered({ kind: "notice" }, { preferences: { notice_period: "  " } }), false);
  assert.equal(questionAnswered({ kind: "relocate" }, { preferences: { willing_to_relocate: "No" } }), true);
  assert.equal(questionAnswered(formQuestions(["US"], MARKETS)[0], { work_auth_by_country: { US: PERMITS } }), false,
    "the United States also needs its visa status");
});

test("the done screen: Add your first job filled, the agent app and the Companion beside it", () => {
  const questions = formQuestions(["DE"], MARKETS);
  const done = stepsDone(PERMITTED, ["DE"]);
  const html = renderElement(
    React.createElement(SetupDone, {
      status: PERMITTED,
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
  // Chose to answer diversity and left some blank: where to finish, beside its consent (the hash opens the fold).
  assert.match(html, /href="\/profile#autofill-eeo"[^>]*>Finish the diversity questions/);
  // A country's work permit left open links to that country's own question, never another country's set.
  const left = renderElement(
    React.createElement(SetupDone, {
      status: PERMITTED,
      done,
      profile: { work_auth_by_country: { DE: PERMITS } },
      questions: formQuestions(["DE", "UK"], MARKETS),
      diversity: null,
      headingRef: { current: null },
      go: () => {},
    }),
  );
  assert.match(left, /href="\/profile#af-permit-UK-authorized_now"[^>]*>Finish your work permit for United Kingdom/);
  assert.doesNotMatch(left, /Germany/);
  // Open required steps say so instead of "You're set".
  const early = renderElement(
    React.createElement(SetupDone, {
      status: STATUS,
      done: stepsDone(STATUS, ["DE"]),
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
