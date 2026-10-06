import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import Module, { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
const frontend = path.resolve(import.meta.dirname, "..");
const resolveFilename = Module._resolveFilename;
Module._resolveFilename = function (name, ...args) {
  return resolveFilename.call(this, name.startsWith("@/") ? path.join(frontend, name.slice(2)) : name, ...args);
};
for (const extension of [".ts", ".tsx"]) {
  Module._extensions[extension] = function (module, filename) {
    const output = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
      fileName: filename,
    });
    module._compile(output.outputText, filename);
  };
}

const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");
const { JobOwnershipMark, JobOwnershipNotice } = require("./job-ownership.tsx");
const { RecentRuns } = require("./proposals/recent-runs.tsx");
const { ConfirmDialogProvider } = require("./confirm-dialog.tsx");
const { AppRouterContext } = require("next/dist/shared/lib/app-router-context.shared-runtime");

function renderElement(element, seed = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, data] of seed) client.setQueryData(key, data);
  const markup = renderToStaticMarkup(React.createElement(QueryClientProvider, { client },
    element));
  client.clear();
  return markup;
}

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

test("Recent runs marks a bot run without jobs and shows a refused request", () => {
  const run = { id: "example-run", automation: "job-hunt", title: "Job hunt", outcome: "ok",
    agent: null, on_bot: true, finished_at: "2026-10-06T12:00:00Z", counts: {}, digest: "", jobs: [] };
  const reason = "Maestro couldn't apply this request.";
  const request = { id: "example-request", job_id: "example-job", reason, job_company: "Example employer",
    job_title: "Example role", answered_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString() };
  // Static rendering never dispatches navigation; mount the real link and confirmation providers.
  const element = React.createElement(AppRouterContext.Provider, { value: {} },
    React.createElement(ConfirmDialogProvider, null, React.createElement(RecentRuns)));
  const html = renderElement(element, [
    [["agent-runs", "latest"], { items: [run], refused_requests: [request] }],
  ]);
  assert.match(html, /on your bot/);
  assert.match(html, /Request refused/);
  assert.match(html, /Maestro couldn/);
  assert.match(html, /href="\/jobs\/example-job"/);
  assert.match(html, /Example role, Example employer/);
  assert.match(html, /3 hours ago/);
});

test("Recent runs with sync off shows no refusal block", () => {
  const element = React.createElement(AppRouterContext.Provider, { value: {} },
    React.createElement(ConfirmDialogProvider, null, React.createElement(RecentRuns)));
  const html = renderElement(element, [[["agent-runs", "latest"], { items: [], refused_requests: [] }]]);
  assert.doesNotMatch(html, /Request refused/);
});
