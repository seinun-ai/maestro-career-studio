import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement, withRouter } from "./render-harness.mjs";

const { JobOwnershipMark, JobOwnershipNotice } = load("components/job-ownership.tsx");
const { RecentRuns } = load("components/automations/recent-runs.tsx");
const { InboxRunNotice } = load("components/proposals/inbox-run-notice.tsx");

function renderMark(ownership) {
  return renderElement(React.createElement(JobOwnershipMark, { jobId: "example-job", ownership }));
}

const off = { owned_here: true, owner: null, handover: null, pending_requests: 0 };

test("sync off renders no mark or handover controls", () => {
  assert.equal(renderMark(off), "");
});

test("replicas show their owner and the work-here action", () => {
  const html = renderMark({ ...off, owned_here: false, owner: "bot" });
  assert.match(html, /With your bot/);
  assert.match(html, /<button[^>]*>.*Work on it here<\/button>/);
  assert.doesNotMatch(html, /Keep it here/);
});

test("offers show the keep-here action beside the mark", () => {
  const html = renderMark({ ...off, owned_here: false, owner: "laptop", handover: "offered", can_keep_here: true });
  assert.match(html, /Going to your bot/);
  assert.match(html, /<button[^>]*>.*Keep it here<\/button>/);
});

test("the bot's copy of an offer shows the mark but no Keep it here", () => {
  const html = renderMark({ ...off, owned_here: false, owner: "laptop", handover: "offered" });
  assert.match(html, /Going to your bot/);
  assert.doesNotMatch(html, /<button/);
  assert.doesNotMatch(renderElement(React.createElement(JobOwnershipNotice, {
    ownership: { ...off, owned_here: false, owner: "laptop", handover: "offered" } })), /Keep it here/);
});

test("pending requests stay visible beside the current owner", () => {
  const html = renderMark({ ...off, owned_here: false, owner: "bot", pending_requests: 1 });
  assert.match(html, /With your bot/);
  assert.match(html, /Sent at the next sync/);
});

test("a row with no ownership is unmarked, unlocked and says nothing", () => {
  assert.equal(renderMark(undefined), "");
  assert.equal(renderElement(React.createElement(JobOwnershipNotice)), "");
  assert.equal(renderElement(React.createElement(JobOwnershipNotice, { ownership: off })), "");
});

const linked = withRouter;

test("Recent runs marks a bot run without jobs", () => {
  const run = { id: "example-run", automation: "job-hunt", title: "Job hunt", outcome: "ok",
    agent: null, on_bot: true, finished_at: "2026-10-06T12:00:00Z", counts: {}, digest: "", jobs: [] };
  const html = renderElement(linked(React.createElement(RecentRuns)), [
    [["agent-runs", "latest"], { items: [run], refused_requests: [] }],
  ]);
  assert.match(html, /on your bot/);
});

test("the Agent inbox shows a refused request, and sync off shows no refusal block", () => {
  const reason = "Maestro couldn't apply this request.";
  const request = { id: "example-request", job_id: "example-job", reason, job_company: "Example employer",
    job_title: "Example role", answered_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString() };
  // Static rendering never dispatches navigation; mount the real link and confirmation providers.
  const html = renderElement(linked(React.createElement(InboxRunNotice)), [
    [["agent-runs", "latest"], { items: [], refused_requests: [request] }],
  ]);
  assert.match(html, /Request refused/);
  assert.match(html, /Maestro couldn/);
  assert.match(html, /href="\/jobs\/example-job"/);
  assert.match(html, /Example role, Example employer/);
  assert.match(html, /3 hours ago/);
  const quiet = renderElement(linked(React.createElement(InboxRunNotice)), [
    [["agent-runs", "latest"], { items: [], refused_requests: [] }],
  ]);
  assert.doesNotMatch(quiet, /Request refused/);
});
