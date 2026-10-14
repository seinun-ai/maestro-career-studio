import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement, withRouter } from "./render-harness.mjs";

const { ArrivalsStrip } = load("components/proposals/arrivals-strip.tsx");
const { CapToday } = load("components/proposals/cap-today.tsx");
const { InboxRunNotice } = load("components/proposals/inbox-run-notice.tsx");
const { RecentRuns } = load("components/automations/recent-runs.tsx");
const { JobKnockoutCard, KnockoutLine } = load("components/job-knockout-card.tsx");
const { ProposalAgentPanel } = load("components/proposals/proposal-agent-panel.tsx");

const SINCE = "2026-10-01T00:00:00Z";
const summary = (over) => [["proposals", "summary", SINCE],
  { since: SINCE, new: 0, ready: 0, queued: 0, needs_you: 0, applied_this_week: 0, ...over }];
const strip = (over) => renderElement(React.createElement(ArrivalsStrip, { since: SINCE }), [summary(over)]);

// ── B1: one summary line ────────────────────────────────────────────────────

test("the summary is one line, zero parts left out, new first", () => {
  const html = strip({ new: 3, needs_you: 1, queued: 4, applied_this_week: 2 });
  assert.match(html, /3 new/);
  assert.match(html, /1 needs you/);
  assert.match(html, /4 queued/);
  assert.match(html, /2 applied this week/);
  assert.equal((html.match(/<button/g) ?? []).length, 4);
  assert.doesNotMatch(html, /Ready to apply|New since your last visit/);
  const some = strip({ queued: 4 });
  assert.match(some, /4 queued/);
  assert.doesNotMatch(some, /need|applied this week|new/);
});

test("all zero is Nothing waiting, and unloaded counts claim nothing", () => {
  assert.match(strip({}), /Nothing waiting/);
  assert.equal(renderElement(React.createElement(ArrivalsStrip, { since: SINCE })), "");
});

// ── B4: the daily limit only near it ────────────────────────────────────────

const funnel = (reserved, max) => [["proposals", "funnel"], { cap: { reserved_last_24h: reserved, max_per_day: max } }];
const cap = (props, reserved, max) => renderElement(React.createElement(CapToday, props), [funnel(reserved, max)]);

test("the inbox's daily limit shows only at 80 percent or more", () => {
  assert.equal(cap({ onlyNearLimit: true }, 7, 10), "");
  assert.match(cap({ onlyNearLimit: true }, 8, 10), /Applications per day: 8 of 10 used in the last 24 hours/);
  assert.match(cap({ onlyNearLimit: true }, 10, 10), /10 of 10/);
});

test("Analytics always shows the daily limit", () => {
  assert.match(cap({}, 1, 10), /Applications per day: 1 of 10/);
});

// ── B5: the inbox's run line, and Recent runs on Automations ────────────────

const run = (counts, over = {}) => ({ id: "r1", automation: "job-hunt", title: "Job hunt", outcome: "ok", agent: null,
  finished_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(), counts, digest: "Looked at four boards.",
  jobs: [{ id: "j1", title: "Data Scientist", company: "Acme" }], ...over });
const runs = (items) => [["agent-runs", "latest"], { items, refused_requests: [] }];
const linked = (element) => withRouter(element);

test("the inbox says the newest run found new jobs, with a link to the runs", () => {
  const html = renderElement(linked(React.createElement(InboxRunNotice)), [runs([run({ found: 12 })])]);
  assert.match(html, /Job hunt found 12 new jobs 2 hours ago/);
  assert.match(html, /<a[^>]*href="\/automations"[^>]*>See runs<\/a>/);
  assert.doesNotMatch(html, /Looked at four boards/);
});

test("the inbox says nothing about a run that found nothing new", () => {
  const html = renderElement(linked(React.createElement(InboxRunNotice)), [runs([run({ proposed: 2 })])]);
  assert.equal(html, "");
});

test("Automations lists the runs, each with its digest and job links", () => {
  const html = renderElement(linked(React.createElement(RecentRuns)), [runs([run({ found: 12 })])]);
  assert.match(html, /Recent runs/);
  assert.match(html, /Looked at four boards\./);
  assert.match(html, /<a[^>]*href="\/jobs\/j1"[^>]*>Data Scientist, Acme<\/a>/);
  assert.match(renderElement(linked(React.createElement(RecentRuns)), [runs([])]), /No runs yet/);
});

// ── A4: the knock-out banner only when it blocks ────────────────────────────

const job = { salary_min: null, salary_max: null, salary_period: null, years_experience_min: null };
const check = (kind, result, message = null) => ({ kind, result, job_value: null, profile_value: null, message });
const banner = (scan) => renderElement(linked(React.createElement(JobKnockoutCard, { scan, job })));
const line = (scan) => renderElement(linked(React.createElement(KnockoutLine, { scan, job })));

test("a conflict is a banner and not a line", () => {
  const scan = { status: "conflict", checks: [check("work_authorization", "conflict", "Needs US citizenship")] };
  assert.match(banner(scan), /You may not qualify: Work auth/);
  assert.equal(line(scan), "");
});

test("a missing profile answer is a banner", () => {
  const scan = { status: "incomplete_profile", checks: [check("salary", "profile_missing")] };
  assert.match(banner(scan), /Your profile is missing an answer/);
  assert.equal(line(scan), "");
});

test("a clear scan is one small line, never a card", () => {
  const scan = { status: "clear", checks: [check("opt", "pass")] };
  assert.equal(banner(scan), "");
  assert.match(line(scan), /No knock-outs/);
});

test("unstated and not-run scans are lines too", () => {
  assert.equal(banner({ status: "unstated", checks: [] }), "");
  assert.match(line({ status: "unstated", checks: [] }), /No requirements listed/);
  const lists = { ...job, years_experience_min: 5 };
  const html = renderElement(linked(React.createElement(KnockoutLine, { scan: { status: "unstated", checks: [] }, job: lists })));
  assert.match(html, /Checks not run yet/);
});

// ── A5: the proposal card ───────────────────────────────────────────────────

const proposal = (over) => ({ id: "p1", job_id: "j1", status: "accepted", reason: null, proposed_by: "you",
  plan_json: { summary: "Queued from the Companion by the user" }, evidence_json: [], qa_entries: [], application: null,
  created_at: "2026-10-05T10:00:00Z", expires_at: "2026-10-12T10:00:00Z", ...over });
const card = (p) => renderElement(linked(React.createElement(ProposalAgentPanel, { proposalId: "p1" })), [[["proposal", "p1"], p]]);

test("expires shows only while the proposal can expire", () => {
  assert.match(card(proposal({ status: "pending_review", proposed_by: "claude-code" })), /expires/);
  assert.match(card(proposal({ status: "needs_decision", reason: "Salary is below your floor" })), /expires/);
  assert.doesNotMatch(card(proposal({ status: "accepted", proposed_by: "claude-code" })), /expires/);
  assert.doesNotMatch(card(proposal({ status: "rejected", reason: "not a fit" })), /expires/);
});
