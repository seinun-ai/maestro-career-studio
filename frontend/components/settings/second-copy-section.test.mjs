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

function render(data) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["settings", "second-copy"], data);
  const html = renderToStaticMarkup(React.createElement(QueryClientProvider, { client },
    React.createElement(component().SecondCopySection)));
  client.clear();
  return html;
}

test("sync off offers only the explicit opt-in, with plain copy", () => {
  const html = render({ enabled: false, open_until: null, last_paired_at: null });
  assert.match(html, /Second copy/);
  assert.match(html, /Lets your always-on copy fetch the sync key once, through its tunnel\. Nothing to copy or paste\./);
  assert.match(html, /Allow pairing for 10 minutes/);
  assert.doesNotMatch(html, />Stop<|Paired with your bot at|role="timer"/);
});

test("an open window renders a countdown and Stop, without a second Allow button", () => {
  const html = render({ enabled: true, open_until: new Date(Date.now() + 590000).toISOString(), last_paired_at: null });
  assert.match(html, /role="timer"/);
  assert.match(html, /[0-9]+:[0-9]{2}/);
  assert.match(html, />Stop</);
  assert.doesNotMatch(html, /Allow pairing for 10 minutes/);
});

test("an expired window offers Allow again", () => {
  const html = render({ enabled: true, open_until: new Date(Date.now() - 1000).toISOString(), last_paired_at: null });
  assert.match(html, /Allow pairing for 10 minutes/);
  assert.doesNotMatch(html, />Stop</);
});

test("a consumed window shows the bot's paired time and can be reopened", () => {
  const html = render({ enabled: true, open_until: null, last_paired_at: "2026-10-06T12:00:00Z" });
  assert.match(html, /Paired with your bot at/);
  assert.match(html, /datetime="2026-10-06T12:00:00Z"/i);
  assert.match(html, /Allow pairing for 10 minutes/);
});

test("the web talks only to the settings route, with POST and DELETE actions", () => {
  const source = fs.readFileSync(path.join(import.meta.dirname, "second-copy-section.tsx"), "utf8");
  assert.match(source, /\/api\/settings\/second-copy/);
  assert.match(source, /method:.*POST/);
  assert.match(source, /DELETE/);
  assert.match(source, /pending=/);
  assert.match(source, /SettingCard/);
  assert.doesNotMatch(source, /\/api\/sync\/|sync-setup|\.key\b/);
});
