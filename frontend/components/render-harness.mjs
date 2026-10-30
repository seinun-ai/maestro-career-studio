// Renders real components to static markup under node, with no browser: TypeScript is transpiled on load,
// "@/" resolves to the frontend root, and react-query is seeded instead of fetching. Used by the
// components/*.test.mjs files (pytest runs them; see backend/tests/sync/test_frontend_ownership.py).
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
      // tsconfig.json's target: ES5's downlevel spread breaks `[..."123"]` (NumberRoll's digits).
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
      fileName: filename,
    });
    module._compile(output.outputText, filename);
  };
}

export const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");
const { AppRouterContext } = require("next/dist/shared/lib/app-router-context.shared-runtime");

/** `import` a TypeScript component by its path under the frontend root. */
export const load = (file) => require(path.join(frontend, file));

/** Markup for `element` with the query cache seeded from `[queryKey, data]` pairs. */
export function renderElement(element, seed = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, data] of seed) client.setQueryData(key, data);
  const markup = renderToStaticMarkup(React.createElement(QueryClientProvider, { client }, element));
  client.clear();
  return markup;
}

/**
 * What `GET /api/settings/autofill/questions` serves for `applyIn` (market keys of `markets`, each with its
 * `work_auth_vocab` and `offers_eeo`): the catalog's questions as the backend's golden test freezes them
 * (backend/tests/fixtures/form_questions_today.json), each country's permit in its vocabulary's words. The state
 * line stays "State", counted, as for a home with no state wording of its own.
 */
export function servedQuestions(markets, applyIn) {
  const fixture = path.join(frontend, "../backend/tests/fixtures/form_questions_today.json");
  const today = JSON.parse(fs.readFileSync(fixture, "utf8"));
  const byKey = new Map(markets.map((m) => [m.key, m]));
  return {
    groups: today.groups,
    permits: Object.fromEntries(applyIn.map((key) => [key, today.permits[byKey.get(key).work_auth_vocab]])),
    offers_eeo: applyIn.some((key) => byKey.get(key).offers_eeo),
  };
}

/** Static rendering never dispatches navigation; mount the router and confirmation providers links need. */
const { ConfirmDialogProvider } = require("./confirm-dialog.tsx");
export const withRouter = (element) =>
  React.createElement(AppRouterContext.Provider, { value: {} },
    React.createElement(ConfirmDialogProvider, null, element));
