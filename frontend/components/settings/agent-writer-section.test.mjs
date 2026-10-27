// Who writes for connected agents (Settings › Agent apps), rendered with seeded reads.
// pytest runs it where the packages are installed: backend/tests/test_frontend_settings_cards.py.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { React, load, renderElement, withRouter } from "../render-harness.mjs";

const { AgentWriterSection } = load("components/settings/agent-writer-section.tsx");

const KEY_LINE = /Needs an API key:/;
const setup = (done) => ({ model_key: { done, detail: {} } });

function render(writer, status) {
  const seed = [[["settings", "mcp-workflow"], { key: "mcp_workflow", value: { hints: false, writer } }]];
  if (status) seed.push([["setup-status"], status]);
  return renderElement(withRouter(React.createElement(AgentWriterSection)), seed);
}

/** The radio input Base UI renders for `value`, as markup. */
function radio(html, value) {
  const m = new RegExp(`<[^>]*role="radio"[^>]*>`, "g");
  const found = [...html.matchAll(m)].map((x) => x[0]);
  const tag = found.find((t) => t.includes(`-${value}-label`));
  assert.ok(tag, `no radio for ${value}`);
  return tag;
}

test("both answers show with their lines, and the saved one is picked", () => {
  const html = render("agent", setup(true));
  assert.match(html, /Who writes for connected agents/);
  assert.match(html, /Your agent app/);
  assert.match(html, /It writes the tailored wording, letters, answers and notes with its own AI\./);
  assert.match(html, /Maestro(?:'|&#x27;)s key isn(?:'|&#x27;)t used for it\./);
  assert.match(html, /Maestro(?:'|&#x27;)s AI/);
  assert.match(html, /Maestro writes them with your API key\. Your agent app steers\./);
  assert.match(radio(html, "agent"), /aria-checked="true"/);
  assert.match(radio(html, "maestro"), /aria-checked="false"/);
  assert.doesNotMatch(html, /\bMCP\b/);
});

test("Maestro's AI with no key says it needs one and links to the key in Basics", () => {
  const html = render("maestro", setup(false));
  assert.match(radio(html, "maestro"), /aria-checked="true"/);
  assert.match(html, KEY_LINE);
  assert.match(html, /<a[^>]*href="\/settings#api-keys"[^>]*>add one in Basics<\/a>/);
  // The line describes the pick it is about.
  const lineId = /<p id="([^"]+)"[^>]*>Needs an API key:/.exec(html)?.[1];
  assert.ok(lineId);
  assert.match(radio(html, "maestro"), new RegExp(`aria-describedby="[^"]*${lineId}"`));
  assert.doesNotMatch(radio(html, "agent"), new RegExp(lineId));
});

test("the key line shows only for Maestro's AI and only on a confirmed missing key", () => {
  assert.doesNotMatch(render("maestro", setup(true)), KEY_LINE);
  assert.doesNotMatch(render("agent", setup(false)), KEY_LINE);
  // Setup status not read (or failed): nothing is claimed.
  assert.doesNotMatch(render("maestro", null), KEY_LINE);
});

test("a pick saves the whole setting, so the hints switch keeps its value", () => {
  const source = fs.readFileSync(path.join(import.meta.dirname, "agent-writer-section.tsx"), "utf8");
  // The same record and key as the hints card (mcp-workflow-section.tsx).
  assert.match(source, /queryKey: \["settings", "mcp-workflow"\]/);
  assert.match(source, /qc\.setQueryData\(\["settings", "mcp-workflow"\], result\)/);
  assert.match(source, /onValueChange=\{\(writer\) => save\.mutate\(\{ \.\.\.data\.value, writer \}\)\}/);
  assert.match(source, /method: "PUT",\s*body: JSON\.stringify\(\{ value \}\)/);
  assert.match(source, /inOrder\("mcp-workflow"/);
  assert.doesNotMatch(source, /scope:/);
  // The pick shows at once, and the saved value replaces it.
  assert.match(source, /save\.isPending \? save\.variables\.writer : data\.value\.writer/);
});
