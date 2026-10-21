// The Automations page rendered with a seeded catalog and run log (design refresh, Task 4.4).
// pytest runs it: backend/tests/test_frontend_automations.py.
import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement, withRouter } from "../render-harness.mjs";

const { default: AutomationsPage } = load("app/automations/page.tsx");

const card = (id, title, over = {}) => ({ id, title, summary: `${title} does its job.`, kind: "scheduled",
  needs: ["maestro"], never: `${title} never does the other thing.`, body: "", prompt: `Prompt for ${title}`, ...over });
const CATALOG = { cards: [
  card("mail-status", "Mail status", { needs: ["maestro", "email"] }),
  card("job-hunt", "Job hunt", { needs: ["maestro", "web"] }),
  card("apply-session", "Apply session", { kind: "attended", needs: ["maestro", "browser"] }),
  card("tailor-run", "Tailor run"),
  card("customize-job-skills", "Make your own", { kind: "custom", never: null }),
] };

const HOUR = 3600 * 1000;
const ago = (ms) => new Date(Date.now() - ms).toISOString();
let n = 0;
const run = (automation, title, finishedMsAgo, over = {}) => ({ id: `run-${++n}`, automation, title, outcome: "ok",
  agent: "claude-ai", on_bot: false, finished_at: ago(finishedMsAgo), counts: {}, digest: "", jobs: [], ...over });

function render(items, { runsPending = false } = {}) {
  const seed = [[["automations"], CATALOG], [["agent-runs", "latest"], { items: [], refused_requests: [] }]];
  if (!runsPending) seed.push([["agent-runs", "all"], { items }]);
  return renderElement(withRouter(React.createElement(AutomationsPage)), seed);
}

test("an automation with a run in 14 days is a Reporting card: strip, report line, one link", () => {
  const html = render([
    run("mail-status", "Mail status", 2 * HOUR, { counts: { updated: 3 }, digest: "Moved three applications." }),
    run("job-hunt", "Job hunt", 2 * 24 * HOUR, { counts: { found: 12, proposed: 4 }, on_bot: true, outcome: "partial" }),
  ]);
  assert.match(html, /How automations work/);
  assert.match(html, /Reporting.*>2</s);
  assert.match(html, /role="img" aria-label="Last 14 days: a report on 1 day, all done"/);
  assert.match(html, /2 hours ago · 3 updated · by Claude</);
  assert.match(html, /2 days ago · 12 found, 4 proposed · by Claude on your bot</);
  // Proposed jobs: one link to the Agent inbox. A digest: Last report opens it in place.
  assert.match(html, /<a[^>]*href="\/proposals"[^>]*>See in Agent inbox/);
  assert.match(html, /aria-expanded="false"[^>]*>Last report</);
  // Each card and each row has one Copy prompt, and no Show prompt.
  assert.equal((html.match(/>Copy prompt</g) ?? []).length, 5);
  assert.doesNotMatch(html, /Show prompt/);
  // A report proves an agent reached Maestro: the connect note goes.
  assert.doesNotMatch(html, /Connect your agent to Maestro first/);
});

test("nothing reported: every automation is a compact row, and the connect note leads", () => {
  const html = render([]);
  assert.doesNotMatch(html, /Reporting/);
  assert.match(html, /No reports yet.*>5</s);
  assert.match(html, /Connect your agent to Maestro first\./);
  assert.match(html, /Make your own/);
  assert.doesNotMatch(html, /role="img"/);
});

test("a run older than the strip keeps its card out of Reporting and says when", () => {
  const html = render([run("tailor-run", "Tailor run", 20 * 24 * HOUR, { counts: { tailored: 2 } })]);
  assert.doesNotMatch(html, /Reporting/);
  assert.match(html, /No reports in 14 days/);
  assert.match(html, /Last report 3 weeks ago/);
});

test("while the run log loads the page claims nothing about reports", () => {
  // Static rendering never fetches: an unseeded run log is a read still loading. A read that failed with no
  // data shows every card as a row instead (pinned from the source in test_frontend_automations.py).
  const html = render([], { runsPending: true });
  assert.doesNotMatch(html, /Reporting|No reports yet|No reports in/);
  assert.doesNotMatch(html, /Copy prompt/);
});

test("Recent runs and what each one never does are folded, with the newest run per automation counted", () => {
  const html = render([
    run("mail-status", "Mail status", 2 * HOUR),
    run("job-hunt", "Job hunt", 3 * HOUR, { outcome: "failed" }),
    run("job-hunt", "Job hunt", 30 * HOUR),
  ]);
  assert.match(html, /<button[^>]*aria-expanded="false"[^>]*>.*Recent runs.*2 · 1 failed/s);
  assert.match(html, /What each one never does/);
  assert.match(html, /Mail status never does the other thing\./);
  // Never shown: a schedule, a connection state, an app's button.
  assert.doesNotMatch(html, />Scheduled<|>Attended<|connected|Open in/);
});
