// Who writes for connected agents (Settings › Agent apps), rendered with seeded reads, and the one save
// it shares with the hints card. The frontend CI job runs it; so does
// backend/tests/test_frontend_settings_cards.py where the packages are installed.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

import { React, load, renderElement, withRouter } from "../render-harness.mjs";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server");
const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");

const { AgentWriterSection } = load("components/settings/agent-writer-section.tsx");
const { useSaveMcpWorkflow } = load("hooks/use-save-mcp-workflow.ts");

const KEY = ["settings", "mcp-workflow"];
const KEY_LINE = /Needs an API key:/;
const setup = (done) => ({ model_key: { done, detail: {} } });

function render(writer, status) {
  const seed = [[KEY, { key: "mcp_workflow", value: { hints: false, writer } }]];
  if (status) seed.push([["setup-status"], status]);
  return renderElement(withRouter(React.createElement(AgentWriterSection)), seed);
}

/** The radio Base UI renders for `value`, as markup. */
function radio(html, value) {
  const tag = [...html.matchAll(/<[^>]*role="radio"[^>]*>/g)].map((m) => m[0]).find((t) => t.includes(`-${value}-label`));
  assert.ok(tag, `no radio for ${value}`);
  return tag;
}

/** The polite region the key line renders into, and its id. */
function keyRegion(html) {
  const m = /<div id="([^"]+)" aria-live="polite"[^>]*>(.*?)<\/div>/.exec(html);
  assert.ok(m, "no live region for the key line");
  return { id: m[1], inner: m[2] };
}

test("both answers show with their lines, and the saved one is picked", () => {
  const html = render("agent", setup(true));
  assert.match(html, /Who writes for connected agents/);
  assert.match(
    html,
    /For Claude, Codex and other agent apps connected to Maestro\. The Maestro app and the Companion always use your API key\./,
  );
  assert.match(html, /Your agent app/);
  assert.match(
    html,
    /It writes the tailored wording, letters, answers and notes with its own AI\. Your API key isn(?:'|&#x27;)t used for them\./,
  );
  assert.match(html, /Maestro(?:'|&#x27;)s AI/);
  assert.match(
    html,
    /Maestro writes the tailored wording, letters, answers and notes with your API key\. Your agent app steers\./,
  );
  assert.match(radio(html, "agent"), /aria-checked="true"/);
  assert.match(radio(html, "maestro"), /aria-checked="false"/);
  assert.doesNotMatch(html, /\bMCP\b/);
});

test("Maestro's AI with no key says it needs one, links to the key in Basics, and announces it", () => {
  const html = render("maestro", setup(false));
  assert.match(radio(html, "maestro"), /aria-checked="true"/);
  const region = keyRegion(html);
  assert.match(region.inner, KEY_LINE);
  assert.match(region.inner, /<a[^>]*href="\/settings#api-keys"[^>]*>add one in Basics<\/a>/);
  // The region describes the pick it is about, and only that one.
  assert.match(radio(html, "maestro"), new RegExp(`aria-describedby="[^"]*${region.id}"`));
  assert.doesNotMatch(radio(html, "agent"), new RegExp(region.id));
});

test("the key line shows only for Maestro's AI and only on a confirmed missing key", () => {
  // The region stays mounted and empty, so the line is announced when it appears.
  for (const html of [render("maestro", setup(true)), render("agent", setup(false)), render("maestro", null)]) {
    assert.doesNotMatch(html, KEY_LINE);
    assert.equal(keyRegion(html).inner, "");
  }
});

// --- The one save both cards share --------------------------------------------------------

/** Two cards' saves over one seeded cache, and a fetch that answers only when told to. */
function mount(value) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(KEY, { key: "mcp_workflow", value });
  const cards = [];
  function Probe() {
    cards.push(useSaveMcpWorkflow(), useSaveMcpWorkflow());
    return null;
  }
  renderToStaticMarkup(React.createElement(QueryClientProvider, { client }, React.createElement(Probe)));
  const [writerCard, hintsCard] = cards;
  return { client, writerCard, hintsCard };
}

const puts = [];
globalThis.fetch = (url, init) =>
  new Promise((resolve) => {
    puts.push({ url, method: init.method, body: JSON.parse(init.body), resolve });
  });
/** The server's echo of what it saved. */
function reply(put) {
  put.resolve(
    new Response(JSON.stringify({ key: "mcp_workflow", value: put.body.value }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a writer pick and a hints flip made together both land, in order", async () => {
  puts.length = 0;
  const { client, writerCard, hintsCard } = mount({ hints: true, writer: "maestro" });
  const first = writerCard.mutateAsync({ writer: "agent" });
  const second = hintsCard.mutateAsync({ hints: false });
  await settle();
  // The hints save waits for the writer's, so it cannot send the writer it saw before.
  assert.equal(puts.length, 1);
  assert.match(puts[0].url, /\/api\/settings\/mcp-workflow$/);
  assert.equal(puts[0].method, "PUT");
  assert.deepEqual(puts[0].body, { value: { hints: true, writer: "agent" } });
  reply(puts[0]);
  await first;
  await settle();
  assert.equal(puts.length, 2);
  assert.deepEqual(puts[1].body, { value: { hints: false, writer: "agent" } });
  reply(puts[1]);
  await second;
  assert.deepEqual(client.getQueryData(KEY).value, { hints: false, writer: "agent" });
  client.clear();
});

test("a hints flip keeps the saved writer, and a writer pick keeps the saved hints", async () => {
  puts.length = 0;
  const { client, writerCard, hintsCard } = mount({ hints: false, writer: "maestro" });
  const flip = hintsCard.mutateAsync({ hints: true });
  await settle();
  assert.deepEqual(puts[0].body, { value: { hints: true, writer: "maestro" } });
  reply(puts[0]);
  await flip;
  const pick = writerCard.mutateAsync({ writer: "agent" });
  await settle();
  assert.deepEqual(puts[1].body, { value: { hints: true, writer: "agent" } });
  reply(puts[1]);
  await pick;
  assert.deepEqual(client.getQueryData(KEY).value, { hints: true, writer: "agent" });
  client.clear();
});
