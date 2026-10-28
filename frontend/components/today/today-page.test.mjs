// The Today page rendered with seeded reads (design refresh, Task 6.2).
// pytest runs it: backend/tests/test_frontend_today.py.
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

import { React, load, withRouter } from "../render-harness.mjs";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server");
const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");

const { default: TodayPage } = load("app/today/page.tsx");
const { todayKey } = load("lib/today.ts");

// The page reads the zone as the browser reports it; node reports its own the same way.
const ZONE = { tz: Intl.DateTimeFormat().resolvedOptions().timeZone || null, offsetMinutes: -new Date().getTimezoneOffset() };
const TODAY_KEY = todayKey(ZONE);
// The one filled button's classes (components/ui/button.tsx, variant "default").
const FILLED = /bg-primary text-primary-foreground/g;

/** The one filled control: its tag, its href (a link) and its words. */
function filled(html) {
  const m = /<(a|button)\b([^>]*bg-primary text-primary-foreground[^>]*)>([^<]*)<\/\1>/.exec(html);
  assert.ok(m, "no filled button");
  return { tag: m[1], href: /href="([^"]*)"/.exec(m[2])?.[1] ?? null, label: m[3] };
}

const WEEK = {
  days: [
    { date: "2026-10-14", applied: 2 },
    { date: "2026-10-15", applied: 3 },
    { date: "2026-10-16", applied: 1 },
    { date: "2026-10-17", applied: 0 },
    { date: "2026-10-18", applied: 0 },
    { date: "2026-10-19", applied: 1 },
    { date: "2026-10-20", applied: 2 },
  ],
  applied: 9,
  replies: 2,
  interviews: 1,
  applied_all_time: 64,
};

const item = (over = {}) => ({
  kind: "pdf_ready",
  job_id: "job-1",
  application_id: "app-1",
  proposal_id: null,
  title: "Senior Product Designer",
  company: "Northwind Studio",
  location: "Berlin",
  pay: { min: 75000, max: 90000, currency: "EUR", period: "year" },
  base_resume: { slug: "product_designer", name: "Product Designer", color_hue: 230 },
  score: 81.4,
  status: "draft",
  proposed_by: null,
  reason: null,
  steps: [
    { key: "saved", at: "2026-10-16T09:00:00+00:00" },
    { key: "gaps_closed", at: "2026-10-17T09:00:00+00:00" },
    { key: "tailored", at: "2026-10-17T12:00:00+00:00" },
  ],
  ...over,
});

const response = (over = {}) => ({
  today: "2026-10-20",
  time_zone: "Europe/Berlin",
  next_up: item(),
  also: [
    { key: "to_approve", count: 3, href: "/proposals" },
    { key: "to_check", count: 4, href: "/applications?stage=tailored" },
    { key: "quiet", count: 5, days: 14, href: "/applications?status=applied" },
  ],
  more: [
    { key: "gaps_to_close", count: 3, gaps: 7, href: "/applications?stage=gaps" },
    { key: "health_check", count: 1, href: "/base-resumes/product_designer/health" },
  ],
  week: WEEK,
  ...over,
});

const step = (done) => ({ done, detail: {} });
const SETUP_DONE = {
  model_key: step(true),
  import_resumes: { done: true, detail: { base_resumes: 2, kb_entities: 40 } },
  autofill: { done: true, readiness: 1, groups: {}, blocking: [], work_auth_by_country: {} },
  job_preferences: step(true),
  persona: step(true),
  template: { done: true, detail: { default_origin: "user", default_template_name: "Clean" } },
  engines: { pdflatex: { available: true, warning: null }, typst: { available: true, warning: null } },
  suggested_bases: [],
  complete: true,
};
const SETUP_NEW = {
  ...SETUP_DONE,
  model_key: step(false),
  import_resumes: { done: false, detail: { base_resumes: 0, kb_entities: 0 } },
  complete: false,
};

function fail(client, queryKey) {
  const query = client.getQueryCache().build(client, { queryKey, queryFn: () => Promise.reject(new Error("no")) });
  query.setState({
    status: "error", fetchStatus: "idle", error: new Error("no"),
    errorUpdateCount: 1, errorUpdatedAt: Date.now(), fetchFailureCount: 1,
  });
}

function render({ today, setup = SETUP_DONE, todayFails = false, setupFails = false } = {}) {
  // A data-less error is fetched again on mount unless retryOnMount is off; static markup renders once.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
  if (today) client.setQueryData(TODAY_KEY, today);
  if (setup) client.setQueryData(["setup-status"], setup);
  client.setQueryData(["settings", "money"], {
    key: "money",
    value: { currency: null, period: "year", hours_per_year: 2080, show_posted: true },
    home_currency: "EUR",
  });
  if (todayFails) fail(client, TODAY_KEY);
  if (setupFails) fail(client, ["setup-status"]);
  const html = renderToStaticMarkup(
    React.createElement(QueryClientProvider, { client }, withRouter(React.createElement(TodayPage))),
  );
  client.clear();
  return html;
}

test("a ready PDF is next up: the job, its resume square, where it is, and one filled Apply", () => {
  const html = render({ today: response() });
  assert.match(html, /<h1[^>]*>Today<\/h1>/);
  assert.match(html, /Tue, Oct 20/);
  assert.match(html, />Next up</);
  assert.match(html, /Senior Product Designer/);
  assert.match(html, /Northwind Studio · Berlin · €75K–€90K a year/);
  // D2: the base resume's square and its name.
  assert.match(html, /rounded-corner-2xs bg-resume[^>]*><\/span>Product Designer/);
  assert.match(html, /role="meter" aria-label="Match score"[^>]*aria-valuetext="81"/);
  // Where this job is: the dated steps, then the move that is next.
  assert.match(html, /Where this job is/);
  assert.match(html, /Saved<\/span><span[^>]*>Oct 16</);
  assert.match(html, /Gaps closed<\/span>/);
  assert.match(html, /Tailored<\/span>/);
  assert.match(html, /Apply<\/span><span[^>]*>now</);
  // The one filled button, a link to the job's Apply step.
  assert.equal((html.match(FILLED) ?? []).length, 1);
  assert.deepEqual(filled(html), { tag: "a", href: "/jobs/job-1?tab=qa", label: "Apply" });
  assert.doesNotMatch(html, /Nothing waiting on you/);
});

test("an offer and a proposal's question each say their own move", () => {
  const offer = render({
    today: response({
      next_up: item({ kind: "offer", status: "offered", steps: [{ key: "saved", at: "2026-09-01T09:00:00+00:00" }, { key: "offered", at: "2026-10-18T09:00:00+00:00" }] }),
    }),
  });
  assert.deepEqual(filled(offer), { tag: "a", href: "/jobs/job-1?tab=qa", label: "Review the offer" });
  assert.match(offer, /Offer<\/span><span[^>]*>Oct 18</);

  const asks = render({
    today: response({
      next_up: item({
        kind: "needs_you", status: "needs_decision", application_id: null, proposal_id: "p-1",
        proposed_by: "claude-ai", reason: "The post asks for a portfolio. Send yours?",
        steps: [{ key: "saved", at: "2026-10-19T09:00:00+00:00" }, { key: "proposed", at: "2026-10-19T09:05:00+00:00" }],
      }),
    }),
  });
  assert.match(asks, /Your agent asks: The post asks for a portfolio\. Send yours\?/);
  assert.match(asks, /Proposed<\/span>/);
  assert.deepEqual(filled(asks), { tag: "a", href: "/jobs/job-1?from=proposals", label: "Answer" });
  assert.equal((asks.match(FILLED) ?? []).length, 1);
});

/** The quiet Skip beside the filled button: an outline button worded Skip, or null. */
function skip(html) {
  const m = /<button\b([^>]*)>Skip<\/button>/.exec(html);
  return m ? { outline: /\bborder\b/.test(m[1]) && !/bg-primary text-primary-foreground/.test(m[1]) } : null;
}

test("Skip sits beside the button for a ready PDF and an agent's question, never for an offer", () => {
  const ready = render({ today: response() });
  assert.deepEqual(skip(ready), { outline: true });
  assert.equal((ready.match(FILLED) ?? []).length, 1);
  assert.equal(filled(ready).label, "Apply");

  const asks = render({
    today: response({
      next_up: item({ kind: "needs_you", status: "needs_decision", application_id: null, proposal_id: "p-1" }),
    }),
  });
  assert.deepEqual(skip(asks), { outline: true });
  assert.equal((asks.match(FILLED) ?? []).length, 1);
  // The reason dialog opens on the press; nothing of it renders before.
  assert.doesNotMatch(asks, /Skip this job\?/);

  const offer = render({ today: response({ next_up: item({ kind: "offer", status: "offered" }) }) });
  assert.equal(skip(offer), null);
  // A ready PDF with no application id (an older backend) has nothing to skip.
  assert.equal(skip(render({ today: response({ next_up: item({ application_id: null }) }) })), null);
});

test("missing pay and an undated resume stay missing", () => {
  const html = render({ today: response({ next_up: item({ pay: null, base_resume: null, score: null, steps: [] }) }) });
  assert.match(html, /Northwind Studio · Berlin</);
  assert.doesNotMatch(html, /€/);
  assert.doesNotMatch(html, /role="meter"/);
  assert.doesNotMatch(html, /Where this job is/);
});

test("also today: three counts, each a link to its list", () => {
  const html = render({ today: response() });
  assert.match(html, /Also today/);
  assert.match(html, /<a[^>]*href="\/proposals"[^>]*>.*?3.*?Agent jobs to review<\/span><\/a>/s);
  assert.match(html, /<a[^>]*href="\/applications\?stage=tailored"[^>]*>.*?Tailored resumes to check<\/span><\/a>/s);
  // The quiet ones are among every job waiting to hear, and the card says so.
  assert.match(html, /<a[^>]*href="\/applications\?status=applied"[^>]*>.*?No reply after 14 days<\/span><span[^>]*>Among your jobs waiting to hear<\/span><\/a>/s);
  // A count of zero is left out by the server, and the page draws only what came.
  const one = render({ today: response({ also: [{ key: "to_check", count: 1, href: "/applications?stage=tailored" }] }) });
  assert.match(one, /Tailored resume to check/);
  assert.doesNotMatch(one, /Agent job/);
  const none = render({ today: response({ also: [] }) });
  assert.doesNotMatch(none, /Also today/);
});

test("the rest folds into one row that says what it holds", () => {
  const html = render({ today: response() });
  assert.match(html, /<button[^>]*aria-expanded="false"[^>]*>.*2 more.*7 gaps to close, 1 health check/s);
  assert.match(html, /href="\/applications\?stage=gaps"/);
  assert.match(html, /href="\/base-resumes\/product_designer\/health"/);
  assert.doesNotMatch(render({ today: response({ more: [] }) }), / more</);
});

test("this week: seven bars as one sentence, with replies and interviews", () => {
  const html = render({ today: response() });
  assert.match(html, /This week/);
  assert.match(html, /role="img" aria-label="Applied per day: Wed 2, Thu 3, Fri 1, Sat 0, Sun 0, Mon 1, today 2"/);
  assert.match(html, /applied, 64 in all/);
  assert.match(html, />2<\/span> replies/);
  assert.match(html, />1<\/span> interview</);
});

test("nothing to do: an honest line, and no filled button", () => {
  const html = render({ today: response({ next_up: null, also: [], more: [] }) });
  assert.match(html, /Nothing waiting on you/);
  assert.equal((html.match(FILLED) ?? []).length, 0);
  assert.match(html, /This week/);
});

test("a failed setup read does not hold the lead: Today's own read says nothing waits", () => {
  const html = render({ today: response({ next_up: null }), setup: null, setupFails: true });
  assert.match(html, /Nothing waiting on you/);
  assert.doesNotMatch(html, />Set up</);
});

test("a new user without a key or a resume sees Setup's card instead", () => {
  const html = render({ today: response({ next_up: null, also: [], more: [] }), setup: SETUP_NEW });
  assert.doesNotMatch(html, /Nothing waiting on you/);
  assert.match(html, />Set up</);
  assert.match(html, /Add an API key/);
  assert.match(html, /Import your resumes/);
  // Its one filled button opens Setup, which starts on the first step not done (components/setup/setup-flow.tsx).
  assert.equal((html.match(FILLED) ?? []).length, 1);
  assert.deepEqual(filled(html), { tag: "a", href: "/setup", label: "Start setup" });
  // A key in place: one step left, and the same button finishes it.
  const keyed = render({ today: response({ next_up: null }), setup: { ...SETUP_NEW, model_key: step(true) } });
  assert.match(keyed, /One step before your first job/);
  assert.deepEqual(filled(keyed), { tag: "a", href: "/setup", label: "Finish setup" });
  // Next up outranks setup: a user with something to do sees it.
  const busy = render({ today: response(), setup: SETUP_NEW });
  assert.match(busy, />Next up</);
  assert.doesNotMatch(busy, />Set up</);
});

test("a failed read is its own state, never the empty one", () => {
  const html = render({ todayFails: true });
  assert.match(html, /role="alert"/);
  assert.match(html, /Couldn&#x27;t load Today\./);
  assert.match(html, /Try again/);
  assert.doesNotMatch(html, /Nothing waiting on you/);
  assert.doesNotMatch(html, /Next up/);
});

test("while it loads, nothing claims a state", () => {
  const html = render({});
  assert.doesNotMatch(html, /Nothing waiting on you|Next up|Set up|This week/);
  assert.match(html, /data-slot="skeleton"/);
  // Nothing next and setup still loading: the lead waits rather than show one card and then the other.
  const lead = render({ today: response({ next_up: null }), setup: null });
  assert.doesNotMatch(lead, /Nothing waiting on you|>Set up</);
  assert.match(lead, /data-slot="skeleton"/);
  assert.match(lead, /This week/);
});
