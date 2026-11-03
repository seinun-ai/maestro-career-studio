// Setup rendered with seeded reads (design refresh, Task 7.1). pytest runs it:
// backend/tests/test_frontend_setup_flow.py.
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

import { React, load, servedQuestions, withRouter } from "../render-harness.mjs";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server");
const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");

const { SetupFlow } = load("components/setup/setup-flow.tsx");
const { SetupDone } = load("components/setup/setup-done.tsx");
const { SetupAnswersStep } = load("components/setup/setup-answers-step.tsx");
const { formQuestions, stepsDone } = load("lib/setup-flow.ts");
const { buildSetupSteps } = load("components/setup/setup-steps.ts");
const { countryCodes } = load("lib/autofill-options.ts");
const {
  citizenshipNext,
  permitAsks,
  questionAnswered,
  questionsToAsk,
  withCitizenshipAnswer,
  withCitizenshipListed,
  withDiversityDeclined,
  withPermitAnswer,
  withPreference,
} = load("lib/setup-answers.ts");

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
// GET /api/countries, a few of them, with the aliases the server's normalize reads.
const COUNTRIES = [
  { code: "AE", name: "United Arab Emirates", aliases: ["uae"] }, { code: "DE", name: "Germany" },
  { code: "GB", name: "United Kingdom", aliases: ["uk", "great britain"] }, { code: "IE", name: "Ireland" },
  { code: "IN", name: "India" }, { code: "NL", name: "Netherlands", aliases: ["holland"] },
  { code: "US", name: "United States", aliases: ["usa"] },
];
const CODES = countryCodes(COUNTRIES);
const market = (applyIn = ["DE"], chosen = true) => ({
  key: "market",
  value: { home: "DE", apply_in: applyIn, market: "DE", chosen },
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

function render({
  status = STATUS,
  info = INFO,
  applyIn = ["DE"],
  chosen = true,
  profile = {},
  served = servedQuestions("DE", applyIn, { chosen }),
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
  client.setQueryData(["setup-status"], status);
  client.setQueryData(["settings", "openai"], info);
  client.setQueryData(["settings", "market"], market(applyIn, chosen));
  client.setQueryData(["settings", "job-preferences"], { key: "job_preferences", value: PREFS });
  client.setQueryData(["settings", "autofill"], { key: "autofill_profile", value: profile });
  client.setQueryData(["settings", "eeo-consent"], { key: "eeo_consent", value: CONSENT_OFF });
  client.setQueryData(["settings", "form-questions"], served);
  client.setQueryData(["countries"], COUNTRIES);
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

function renderElement(element, seed = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, data] of seed) client.setQueryData(key, data);
  const html = renderToStaticMarkup(React.createElement(QueryClientProvider, { client }, withRouter(element)));
  client.clear();
  return html;
}

// What the server serves for every country these tests apply in.
const SERVED = servedQuestions("DE", ["DE", "UK", "US"]);

// The answers as the flow holds them (`useSetupAnswers`), with nothing saving.
const held = (profile) => ({ value: profile, update: () => {}, pending: false, failed: false, retry: () => {} });
const answersStep = ({ profile = {}, opened = {}, ...props }, seed = []) =>
  renderElement(
    React.createElement(SetupAnswersStep, {
      answers: held(profile),
      opened,
      questionSet: SERVED,
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

const KEYED = { ...STATUS, model_key: step(true) };
const IMPORTED = { ...KEYED, import_resumes: { done: true, detail: { base_resumes: 2, kb_entities: 40 } } };
const WANTED = { ...IMPORTED, job_preferences: step(true) };
// Setup status counts each country's work-permit answers in its own words, and citizenship beside them.
const PERMITTED = {
  ...WANTED,
  autofill: {
    ...STATUS.autofill,
    groups: { work_auth: { answered: 4, answerable: 4 } },
    work_auth_by_country: { DE: { answered: 3, answerable: 3 } },
  },
};

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

test("with no country chosen, where you apply shows none picked and says so", () => {
  const html = render({ status: IMPORTED, applyIn: ["US"], chosen: false });
  // The stored default (the US) is not a choice: no chip is pressed, and the hint says none is chosen.
  for (const name of ["United States", "United Kingdom", "Germany"]) assert.match(html, new RegExp(`aria-pressed="false"[^>]*>${name}<`));
  assert.match(html, /No country chosen yet\. Each one you pick has its own work-permit answers\./);
  assert.doesNotMatch(html, /0 countries/);
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

test("then form answers, one at a time: citizenship first, with its country picker", () => {
  const html = render({ status: WANTED, applyIn: ["DE", "UK"] });
  assert.match(html, /Answers every job form asks/);
  // Citizenship, two permits, notice, relocation, and diversity for the United Kingdom's checked set.
  assert.match(html, /1 of 6/);
  assert.match(html, /<h3[^>]*><label for="([^"]+)">Citizen of<\/label><\/h3>/);
  assert.match(html, /aria-label="Citizen of"/);
  assert.match(html, /its work-permit answers follow from it\./);
  assert.doesNotMatch(html, /Work permit</);
  // Continue moves on; nothing is saving.
  assert.match(html, /<button[^>]*bg-primary text-primary-foreground[^>]*>Continue<\/button>/);
  assert.doesNotMatch(html.match(/<button[^>]*>Continue<\/button>/)?.[0] ?? "", /aria-disabled="true"|disabled=""/);
  assert.match(html, />Skip for now</);
});

test("with no country chosen, where and what stays open though the job preferences are saved", () => {
  // Unchosen, no country's permits are asked, so every form would pause on them: Setup opens where to choose.
  const html = render({ status: WANTED, applyIn: ["US"], chosen: false });
  assert.match(html, /Where and what you&#x27;re looking for/);
  assert.match(html, /2 of 4 done/);
  assert.doesNotMatch(html, /Where and what<\/span><span[^>]*>Done</);
});

test("with no country chosen, the form answers are citizenship, notice and relocation: no work permit", () => {
  const unchosen = servedQuestions("US", [], { chosen: false });
  const questions = formQuestions(unchosen, MARKETS);
  assert.equal(questions.some((q) => q.kind === "permit"), false);
  const html = answersStep({ questionSet: unchosen, questions, question: 0 });
  assert.match(html, /1 of 3/);
  assert.match(html, />Citizen of<\/label>/);
});

test("a country's work permit, named, each question's group named by the country and the question", () => {
  const questions = formQuestions(servedQuestions("DE", ["DE", "UK"]), MARKETS);
  const html = answersStep({ questionSet: servedQuestions("DE", ["DE", "UK"]), questions, question: 1 });
  assert.match(html, /2 of 6/);
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
});

const permitCard = (applyIn, { profile = {}, opened = {} } = {}) => {
  const questionSet = servedQuestions("DE", applyIn);
  const questions = formQuestions(questionSet, MARKETS);
  return answersStep({ questionSet, questions, question: 1, profile, opened });
};

test("the United States asks its visa status too, named by the country and the question", () => {
  const html = permitCard(["US"]);
  const country = /<h3 id="([^"]+)"[^>]*>United States<\/h3>/.exec(html)[1];
  const q = /<span id="([^"]+)"[^>]*>Work authorization status<\/span>/.exec(html);
  assert.ok(q);
  assert.match(html, new RegExp(`aria-labelledby="${country} ${q[1]}"`));
  assert.match(html, /Authorized to work in the U\.S\. now\?/);
});

test("the United Kingdom is asked in its own words", () => {
  const html = permitCard(["UK"]);
  assert.match(html, /Do you have the right to work in the UK now\?/);
  assert.doesNotMatch(html, /Work authorization status/);
});

test("every step done opens the first again, all four marked", () => {
  const html = render({
    status: PERMITTED,
    applyIn: ["DE"],
    profile: { personal: { citizenships: ["IN"] }, work_auth_by_country: { DE: PERMITS } },
  });
  assert.match(html, /All 4 done/);
  assert.match(html, /Pick the AI that does the writing/);
});

// An Indian citizen who lives in India and applies in India, the UAE, Germany and the Netherlands, as the server
// serves it: the citizenship settles India's three permit answers (`derived`), and nothing elsewhere.
const INDIA = servedQuestions("IN", ["IN", "AE", "DE", "NL"], { citizenships: ["IN"] });
const ASHA = { personal: { first_name: "Asha", citizenships: ["IN"] } };

test("a country your citizenship settles is answered, so the flow passes it: citizenship, then the UAE, Germany, the Netherlands", () => {
  const all = formQuestions(INDIA, MARKETS);
  assert.deepEqual(all.map((q) => q.kind === "permit" ? q.market : q.kind), ["citizenship", "IN", "AE", "DE", "NL", "notice", "relocate"]);
  assert.equal(questionAnswered(all[1], ASHA, INDIA), true, "India is settled by the citizenship");
  assert.deepEqual(permitAsks(ASHA, INDIA, "IN", {}), []);
  const asked = questionsToAsk(all, ASHA, INDIA, {});
  assert.deepEqual(asked.map((q) => q.kind === "permit" ? q.market : q.kind), ["citizenship", "AE", "DE", "NL", "notice", "relocate"]);
  // Removing the citizenship asks India again at once, before the questions are read again.
  const noLonger = { personal: { first_name: "Asha" } };
  assert.equal(questionsToAsk(all, noLonger, INDIA, {}).some((q) => q.kind === "permit" && q.market === "IN"), true);
  // The flow, rendered: India is not among the questions, so the first card after citizenship is the UAE's.
  const html = render({ status: WANTED, applyIn: ["IN", "AE", "DE", "NL"], served: INDIA, profile: ASHA });
  assert.match(html, /1 of 6/);
  assert.match(html, /aria-label="Remove India"/);
  const card = answersStep({ questionSet: INDIA, questions: asked, question: 1, profile: ASHA });
  assert.match(card, /<h3 id="[^"]+"[^>]*>United Arab Emirates<\/h3>/);
});

test("a permit card asks only the required questions neither settled nor answered before Setup opened", () => {
  // The UAE: its three yes/no questions, never its status list or expiry (optional), and none of its own answers.
  const uae = answersStep({ questionSet: INDIA, questions: questionsToAsk(formQuestions(INDIA, MARKETS), ASHA, INDIA, {}), question: 1, profile: ASHA });
  assert.match(uae, /Can you work in the UAE without an employer sponsoring your residence visa\?/);
  assert.match(uae, /Do you need an employer to sponsor your UAE residence visa now\?/);
  assert.match(uae, /Will you need an employer to sponsor your UAE residence visa later\?/);
  for (const optional of ["Immigration status", "Authorization expires on", "Expected total monthly salary", "Are you in the UAE now?", "UAE driving licence"]) {
    assert.ok(!uae.includes(optional), optional);
  }
  // Germany, answered in part before Setup opened: only what is left. An answer given here stays on its card.
  const opened = { ...ASHA, work_auth_by_country: { DE: { authorized_now: true } } };
  assert.deepEqual(permitAsks(opened, INDIA, "DE", opened).map((f) => f.key), ["sponsorship_now", "sponsorship_future"]);
  const now = { ...ASHA, work_auth_by_country: { DE: { authorized_now: true, sponsorship_now: false } } };
  assert.deepEqual(permitAsks(now, INDIA, "DE", opened).map((f) => f.key), ["sponsorship_now", "sponsorship_future"]);
  const de = answersStep({ questionSet: INDIA, questions: [{ kind: "permit", market: "DE", label: "Germany" }], question: 0, profile: now, opened });
  assert.doesNotMatch(de, /Can you work in this country now\?/);
  assert.match(de, /aria-pressed="true"[^>]*>.*?No</s);
  // A country answered in full before Setup opened is passed; one answered here is not.
  const done = { ...ASHA, work_auth_by_country: { DE: PERMITS } };
  assert.equal(questionsToAsk(formQuestions(INDIA, MARKETS), done, INDIA, done).some((q) => q.kind === "permit" && q.market === "DE"), false);
  assert.equal(questionsToAsk(formQuestions(INDIA, MARKETS), done, INDIA, ASHA).some((q) => q.kind === "permit" && q.market === "DE"), true);
});

test("citizenship saves as codes, without the one-set view; a plain string is stored as a list first", () => {
  const before = { personal: { first_name: "Lena" }, work_auth: { authorized_now: true } };
  const after = withCitizenshipAnswer(before, ["DE", "FR", "DE"]);
  assert.deepEqual(after.personal, { first_name: "Lena", citizenships: ["DE", "FR"] });
  assert.equal("work_auth" in after, false);
  assert.deepEqual(withCitizenshipAnswer({ personal: { citizenships: ["DE"] } }, []).personal, {});
  assert.deepEqual(withCitizenshipListed({ personal: { citizenships: "Germany" }, work_auth: {} }, CODES), {
    personal: { citizenships: ["DE"] },
  });
  // Answered once the picker stored a country; a plain string is no answer until it is a list.
  assert.equal(questionAnswered({ kind: "citizenship" }, { personal: { citizenships: ["DE"] } }, SERVED), true);
  assert.equal(questionAnswered({ kind: "citizenship" }, { personal: { citizenships: "Germany" } }, SERVED), false);
  assert.equal(questionAnswered({ kind: "citizenship" }, {}, SERVED), false);
  // Names left by a hand edit: not answered once the country list is read, so its dot stays open.
  assert.equal(questionAnswered({ kind: "citizenship" }, { personal: { citizenships: ["Germany"] } }, SERVED, CODES), false);
  assert.equal(questionAnswered({ kind: "citizenship" }, { personal: { citizenships: ["DE"] } }, SERVED, CODES), true);
});

test("one press on citizenship: store it as codes, wait for the save, then move on", () => {
  // Stored as codes and nothing saving: Continue moves on at once.
  assert.equal(citizenshipNext({ personal: { citizenships: ["IN"] } }, CODES, false), "move on");
  // Saving (a pick reads the questions again): the press waits, and moves on once the save lands.
  assert.equal(citizenshipNext({ personal: { citizenships: ["IN"] } }, CODES, true), "wait");
  // A plain string: stored as codes first; once stored, the press only waits for that save.
  const loose = { personal: { citizenships: "India" } };
  assert.equal(citizenshipNext(loose, CODES, false), "store");
  const stored = withCitizenshipListed(loose, CODES);
  assert.deepEqual(stored.personal.citizenships, ["IN"]);
  assert.equal(citizenshipNext(stored, CODES, true), "wait");
  // A list mixing a code and names ("UK" is GB): stored as codes too.
  const mixed = { personal: { citizenships: ["IN", "UK", "Holland"] } };
  assert.equal(citizenshipNext(mixed, CODES, false), "store");
  assert.deepEqual(withCitizenshipListed(mixed, CODES).personal.citizenships, ["IN", "GB", "NL"]);
  // Before the country list is read, a list is left as it is; a plain string still goes out as its parts.
  assert.equal(citizenshipNext(mixed, null, false), "move on");
  assert.equal(citizenshipNext(loose, null, false), "store");
});

test("a citizenship that names no country is dropped, and the done screen asks for it", () => {
  const stored = withCitizenshipListed({ personal: { first_name: "Lena", citizenships: "Narnia" } }, CODES);
  assert.deepEqual(stored.personal, { first_name: "Lena" });
  assert.equal(questionAnswered({ kind: "citizenship" }, stored, SERVED), false);
  const germany = servedQuestions("DE", ["DE"]);
  const html = renderElement(
    React.createElement(SetupDone, {
      questionSet: germany,
      status: PERMITTED,
      done: stepsDone(PERMITTED, germany),
      profile: { ...stored, work_auth_by_country: { DE: PERMITS } },
      diversity: null,
      headingRef: { current: null },
      go: () => {},
    }),
  );
  assert.match(html, /href="\/profile#af-citizenships"[^>]*>Add your citizenship/);
});

test("diversity: only for a country with a set, named, and nothing stored before the consent", () => {
  const without = formQuestions(servedQuestions("DE", ["DE"]), MARKETS);
  assert.equal(without.some((q) => q.kind === "diversity"), false);
  const questions = formQuestions(SERVED, MARKETS);
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
  const questionSet = servedQuestions("DE", ["DE", "UK"]);
  const questions = formQuestions(questionSet, MARKETS);
  const dots = (html) => [...html.matchAll(/<span class="size-1\.5 rounded-full ([^"]+)"><\/span>/g)].map((m) => m[1]);
  // On the notice question, citizenship and both work permits passed by unanswered: none is green.
  assert.deepEqual(dots(answersStep({ questionSet, questions, question: 3 })), [
    "bg-surface-container-high", "bg-surface-container-high", "bg-surface-container-high", "bg-primary",
    "bg-surface-container-high", "bg-surface-container-high",
  ]);
  const answered = answersStep({
    questionSet,
    questions,
    question: 3,
    profile: { personal: { citizenships: ["IN"] }, work_auth_by_country: { DE: PERMITS } },
  });
  assert.deepEqual(dots(answered).slice(0, 3), ["bg-success", "bg-success", "bg-surface-container-high"]);
});

test("contact fields fill from career history in place, and say why they cannot", () => {
  const questions = formQuestions(servedQuestions("DE", ["DE"]), MARKETS);
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
  const after = withPermitAnswer(before, SERVED, "UK", "sponsorship_now", true);
  assert.deepEqual(after.work_auth_by_country, {
    DE: { authorized_now: true, status: "citizen" },
    UK: { authorized_now: false, sponsorship_now: true },
  });
  assert.equal("work_auth" in after, false);
  assert.deepEqual(before.work_auth_by_country.UK, { authorized_now: false }, "the input is not changed");
  assert.deepEqual(withPermitAnswer({}, SERVED, "US", "status", "citizen"), { work_auth_by_country: { US: { status: "citizen" } } });
  const prefs = withPreference({ preferences: { desired_salary: "80k" }, work_auth: {} }, SERVED, "notice_period", "1 month");
  assert.deepEqual(prefs, { preferences: { desired_salary: "80k", notice_period: "1 month" } });
  // Declining fills each blank diversity question with its decline choice, the veteran one too, and leaves
  // race or ethnicity (typed, with no decline choice) blank.
  assert.deepEqual(withDiversityDeclined({ eeo: { gender: "female" } }, SERVED).eeo, {
    gender: "female", veteran_status: "decline", disability_status: "decline", hispanic_latino: "decline",
  });
  assert.equal("race_ethnicity" in withDiversityDeclined({}, SERVED).eeo, false);
  assert.equal(questionAnswered({ kind: "notice" }, { preferences: { notice_period: "  " } }, SERVED), false);
  assert.equal(questionAnswered({ kind: "relocate" }, { preferences: { willing_to_relocate: "No" } }, SERVED), true);
  const us = formQuestions(servedQuestions("DE", ["US"]), MARKETS).find((q) => q.kind === "permit");
  assert.equal(questionAnswered(us, { work_auth_by_country: { US: PERMITS } }, SERVED), false,
    "the United States also needs its visa status");
  // A country the set serves no questions for is open, never answered, whatever is stored for it.
  assert.equal(questionAnswered({ kind: "permit", market: "FR", label: "France" }, { work_auth_by_country: { FR: PERMITS } }, SERVED), false);
});

test("the done screen: Add your first job filled, the agent app and the Companion beside it", () => {
  const germany = servedQuestions("DE", ["DE"]);
  const done = stepsDone(PERMITTED, germany);
  const doneScreen = (props) =>
    renderElement(
      React.createElement(SetupDone, {
        questionSet: germany,
        status: PERMITTED,
        done,
        profile: {},
        diversity: null,
        headingRef: { current: null },
        go: () => {},
        ...props,
      }),
    );
  const html = doneScreen({
    profile: { personal: { first_name: "Lena", citizenships: ["DE"] }, work_auth_by_country: { DE: PERMITS } },
    diversity: "answer",
  });
  assert.match(html, /You&#x27;re set, Lena/);
  assert.equal((html.match(FILLED) ?? []).length, 1);
  assert.match(html, /<a[^>]*href="\/new"[^>]*bg-primary text-primary-foreground[^>]*>Add your first job<\/a>|<a[^>]*bg-primary text-primary-foreground[^>]*href="\/new"[^>]*>Add your first job<\/a>/);
  assert.match(html, /href="\/settings\?tab=agents"[^>]*>.*?Connect an agent app/s);
  assert.match(html, /href="https:\/\/github\.com\/[^"]+GETTING_STARTED\.md#4-the-companion-browser-extension-optional"[^>]*target="_blank"[^>]*>.*?Add the Companion/s);
  // Chose to answer diversity and left some blank: where to finish, beside its consent (the hash opens the fold).
  assert.match(html, /href="\/profile#autofill-eeo"[^>]*>Finish the diversity questions/);
  assert.doesNotMatch(html, /Add your citizenship/);
  // A country's work permit left open links to that country's own question, never another country's set; a
  // citizenship left blank links to Citizen of, in Country answers.
  const left = doneScreen({ questionSet: servedQuestions("DE", ["DE", "UK"]), profile: { work_auth_by_country: { DE: PERMITS } } });
  assert.match(left, /href="\/profile#af-permit-UK-authorized_now"[^>]*>Finish your work permit for United Kingdom/);
  assert.doesNotMatch(left, /Germany/);
  assert.match(left, /href="\/profile#af-citizenships"[^>]*>Add your citizenship/);
  // A country your citizenship settles is not left.
  assert.doesNotMatch(doneScreen({ questionSet: INDIA, profile: ASHA }), /Finish your work permit for India/);
  // A country served no permit questions is still left to finish, and its link opens the Country answers tile.
  const france = { ...germany, countries: [{ market: "FR", label: "France", permits: [], answers: [] }] };
  const unserved = doneScreen({ questionSet: france, profile: { work_auth_by_country: { FR: PERMITS } } });
  assert.match(unserved, /href="\/profile#af-permit-FR"[^>]*>Finish your work permit for France/);
  // Open required steps say so instead of "You're set".
  const early = doneScreen({ status: STATUS, done: stepsDone(STATUS, germany) });
  assert.match(early, /Almost there/);
  assert.match(early, /Not done yet/);
  assert.doesNotMatch(early, /You&#x27;re set/);
  assert.doesNotMatch(early, /diversity/);
});

test("only the home's pay missing: the setup card names it and opens Country answers; Setup's answers step stays done", () => {
  // Setup status counts the home's pay apart from the groups (`home_pay`), so every group reads complete.
  const count = (answered, answerable) => ({ answered, answerable });
  const autofill = {
    done: false, readiness: 0.96, blocking: [], chosen: true,
    groups: { personal: count(9, 9), work_auth: count(4, 4), preferences: count(4, 4) },
    work_auth_by_country: { DE: count(3, 3) },
    home_pay: count(0, 1),
  };
  const status = { ...STATUS, autofill };
  const card = buildSetupSteps(status, "/applications").find((s) => s.id === "autofill");
  assert.equal(card.detail, "96% done. Expected pay is missing.");
  assert.deepEqual(card.action, { kind: "navigate", href: "/profile#autofill-work_auth" });
  // Setup never asks pay (Decision 8): its answers step reads the work-permit counts alone.
  assert.equal(stepsDone(status, servedQuestions("DE", ["DE"])).answers, true);
  // Asked right after the work permits, as Next up asks it: before a Start and pay answer still open.
  const later = { ...autofill, groups: { ...autofill.groups, preferences: count(3, 4) } };
  const first = buildSetupSteps({ ...STATUS, autofill: later }, "/applications").find((s) => s.id === "autofill");
  assert.equal(first.detail, "96% done. Expected pay is missing.");
});
