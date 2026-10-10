import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import Module, { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
const frontend = path.resolve(import.meta.dirname, "../..");
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

function component() {
  return require("./second-copy-section.tsx");
}

const PROMPT_KEY = ["settings", "second-copy", "setup-prompt"];

function render(data) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["settings", "second-copy"], data);
  client.setQueryData(PROMPT_KEY, { prompt: "SENTINEL-PROMPT-DO-NOT-RENDER" });
  const html = renderToStaticMarkup(React.createElement(QueryClientProvider, { client },
    React.createElement(component().SecondCopySection)));
  client.clear();
  return html;
}

function renderPromptError(data) {
  // A data-less error is fetched again on mount unless retryOnMount is off, and that
  // optimistic fetch hides the error on the only render static markup performs.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryOnMount: false } },
  });
  client.setQueryData(["settings", "second-copy"], data);
  const query = client.getQueryCache().build(client, {
    queryKey: PROMPT_KEY,
    queryFn: () => Promise.reject(new Error("no")),
  });
  query.setState({
    status: "error", fetchStatus: "idle", error: new Error("no"),
    errorUpdateCount: 1, errorUpdatedAt: Date.now(), fetchFailureCount: 1,
  });
  const html = renderToStaticMarkup(React.createElement(QueryClientProvider, { client },
    React.createElement(component().SecondCopySection)));
  client.clear();
  return html;
}

function renderBody(props) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(PROMPT_KEY, { prompt: "SENTINEL-PROMPT-DO-NOT-RENDER" });
  return renderToStaticMarkup(React.createElement(QueryClientProvider, { client },
    React.createElement(component().SecondCopyBody, props)));
}

const CARD = "Pair an always-on copy of Maestro with this laptop.";
const CARD_RE = new RegExp(CARD.replace(/[.]/g, "\\."));
const PASTE = /Paste this code to your bot\. It works once, for 10 minutes\./;
const SHOW_NEW = "Show a new pairing code";

test("sync off offers only the explicit opt-in, with a neutral description", () => {
  const html = render({ enabled: false, open_until: null, last_paired_at: null });
  assert.match(html, /Second copy/);
  assert.match(html, CARD_RE);
  assert.match(html, /Show a pairing code/);
  assert.doesNotMatch(html, PASTE);
  assert.doesNotMatch(html, /through its tunnel|Allow pairing/);
  assert.doesNotMatch(html, />Stop<|Paired with your bot at|role="timer"/);
});

test("a live window this page did not open shows Stop and the countdown, not the code", () => {
  const html = render({
    enabled: true,
    open_until: new Date(Date.now() + 590000).toISOString(),
    last_paired_at: null,
    code: "0123-4567-89AB-CDEF",
  });
  assert.match(html, CARD_RE);
  assert.match(html, new RegExp(SHOW_NEW));
  assert.match(html, /role="timer"/);
  assert.match(html, /Expires in \d+:\d{2}/);
  assert.match(html, />Stop</);
  assert.doesNotMatch(html, /Show a pairing code(?! )/);
  assert.doesNotMatch(html, PASTE);
  assert.doesNotMatch(html, /0123-4567-89AB-CDEF/);
  assert.doesNotMatch(html, /Copy pairing code/);
});

test("an expired window offers Show a pairing code again", () => {
  const html = render({ enabled: true, open_until: new Date(Date.now() - 1000).toISOString(), last_paired_at: null });
  assert.match(html, /Show a pairing code/);
  assert.doesNotMatch(html, />Stop</);
});

test("a consumed window shows the bot's paired time and can be reopened", () => {
  const html = render({ enabled: true, open_until: null, last_paired_at: "2026-10-06T12:00:00Z" });
  assert.match(html, /Paired with your bot at/);
  assert.match(html, /datetime="2026-10-06T12:00:00Z"/i);
  assert.match(html, /Show a pairing code/);
  assert.doesNotMatch(html, PASTE);
  assert.doesNotMatch(html, new RegExp(SHOW_NEW));
});

const NEW_BOT = /New bot\? Copy its setup prompt and paste it into the agent app on that machine\./;

test("a new bot can copy its setup prompt from the same card", () => {
  const html = render({ enabled: false, open_until: null, last_paired_at: null });
  assert.match(html, NEW_BOT);
  assert.match(html, /Copy setup prompt/);
  assert.doesNotMatch(html, /Copied/);
  assert.doesNotMatch(html, /SENTINEL-PROMPT-DO-NOT-RENDER/);
  assert.match(html, /Show a pairing code/);
});

test("copying the setup prompt is a link, secondary to showing a code", () => {
  const html = render({ enabled: false, open_until: null, last_paired_at: null });
  const at = html.indexOf("Copy setup prompt");
  assert.ok(at > 0);
  const tag = html.slice(html.lastIndexOf("<button", at), at);
  assert.match(tag, /underline-offset-4/);
  assert.doesNotMatch(tag, /bg-secondary-container/);
  const show = html.indexOf("Show a pairing code");
  const showTag = html.slice(html.lastIndexOf("<button", show), show);
  assert.match(showTag, /bg-secondary-container/);
});

test("a failed setup-prompt load is one inline line and not a toast", () => {
  const html = renderPromptError({ enabled: false, open_until: null, last_paired_at: null });
  assert.match(html, /Couldn(?:'|&#x27;)t load the setup prompt\./);
  assert.doesNotMatch(html, /Copy setup prompt/);
  assert.doesNotMatch(html, /toast/);
});

test("a code just shown is large, copyable, and not offered again", () => {
  const code = "0123-4567-89AB-CDEF";
  const html = renderBody({
    data: { enabled: true, open_until: new Date(Date.now() + 590000).toISOString(), last_paired_at: null },
    seconds: 590, pending: false, code, act: () => {},
  });
  assert.match(html, /0123-4567-89AB-CDEF/);
  assert.match(html, NEW_BOT);
  assert.match(html, /Copy setup prompt/);
  assert.match(html, /Copy pairing code/);
  assert.match(html, PASTE);
  assert.match(html, /role="timer"/);
  assert.match(html, />Stop</);
  assert.match(html, /This laptop/);
  assert.doesNotMatch(html, /Show a pairing code/);
});

test("the web talks only to the settings route, with POST and DELETE actions", () => {
  const source = fs.readFileSync(path.join(import.meta.dirname, "second-copy-section.tsx"), "utf8");
  assert.match(source, /\/api\/settings\/second-copy/);
  assert.match(source, /\/api\/settings\/second-copy\/setup-prompt/);
  assert.match(source, /useQuery\(/);
  assert.match(source, /useCopy\(/);
  assert.match(source, /onClick=\{\(\) => void copy\(text\)\}/);
  assert.doesNotMatch(source, /await apiFetch/);
  assert.doesNotMatch(source, /couldnt\("copy the setup prompt"/);
  assert.match(source, /variant="link"[\s\S]{0,200}Copy setup prompt/);
  assert.doesNotMatch(source, /variant="tonal"[\s\S]{0,160}Copy setup prompt/);
  assert.match(source, /w-fit/);
  assert.match(source, /Couldn't load the setup prompt\./);
  assert.match(source, /copied \? "Copied" : "Copy setup prompt"/);
  assert.match(source, NEW_BOT);
  assert.match(source, /method:.*POST/);
  assert.match(source, /DELETE/);
  assert.match(source, /pending=/);
  assert.match(source, /SettingCard/);
  assert.match(source, /CONCEPT_ICONS/);
  assert.match(source, /Show a pairing code/);
  assert.match(source, /Show a new pairing code/);
  assert.match(source, CARD_RE);
  assert.match(source, /Paste this code to your bot\. It works once, for 10 minutes\./);
  assert.match(source, /focusIfDropped\(focusTarget\(/);
  assert.match(source, /action === "stop" \? showRef : codeRef/);
  assert.doesNotMatch(source, /type SecondCopy = \{[^}]*\bcode\b/);
  assert.doesNotMatch(source, /data\.code/);
  assert.doesNotMatch(source, /\/api\/sync\/|sync-setup|\.key\b|through its tunnel|Allow pairing/);
});
