import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PROVIDERS,
  everydayCan,
  everydayStatus,
  isRemoteEndpoint,
  keyWarning,
  modelName,
  providerLabel,
  showsModelId,
  keysInUse,
  runsOn,
  sourceLabel,
  type EverydayState,
} from "./model-catalog.ts";

test("provider and source read as words, never keys", () => {
  assert.equal(providerLabel("openai"), "OpenAI");
  assert.equal(providerLabel("gemini"), "Gemini");
  assert.equal(sourceLabel(undefined), "Built-in");
  assert.equal(sourceLabel("seed"), "Built-in");
  assert.equal(sourceLabel("configured"), "In use");
  assert.equal(sourceLabel("extra"), "Added");
});

test("an unknown provider reads as a title-cased word, never a key or a prototype property", () => {
  assert.equal(providerLabel("constructor"), "Constructor");
  assert.equal(providerLabel("toString"), "ToString");
  assert.equal(providerLabel("open_router"), "Open Router");
  assert.equal(providerLabel("mistral"), "Mistral");
});

test("only a server off this machine is remote", () => {
  for (const local of [
    "",
    "  ",
    "http://localhost:11434/v1",
    "http://127.0.0.1:1/v1",
    "http://[::1]:11434/v1",
    "http://host.docker.internal:11434/v1",
    "http://studio.local:1234/v1",
    "not a url yet",
  ]) {
    assert.equal(isRemoteEndpoint(local), false, local);
  }
  assert.equal(isRemoteEndpoint("https://openrouter.ai/api/v1"), true);
  assert.equal(isRemoteEndpoint("http://192.168.1.20:11434/v1"), true);
});

test("the id shows only when it differs from the name", () => {
  // The id only restates the name (its provider in front, dots and dashes aside): hidden.
  assert.equal(showsModelId({ id: "gpt-5.6-luna", label: "OpenAI GPT-5.6 Luna" }), false);
  assert.equal(showsModelId({ id: "gemini-3.7-flash", label: "Gemini 3.7 Flash" }), false);
  assert.equal(showsModelId({ id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite" }), false);
  // It says something the name does not: shown.
  assert.equal(showsModelId({ id: "gpt-4o-mini-2024-07-18", label: "GPT-4o mini" }), true);
  assert.equal(showsModelId({ id: "llama3.2:3b", label: "My laptop model" }), true);
  assert.equal(showsModelId({ id: "luna", label: "Acme Luna" }), true);
  assert.equal(showsModelId({ id: "gpt-6-luna", label: "gpt-6-luna" }), false);
  assert.equal(showsModelId({ id: "gpt-6-luna", label: " gpt-6-luna " }), false);
});

test("a model is named by its label, else its id", () => {
  const options = [{ id: "gemini-3.7-flash", label: "Gemini 3.7 Flash" }];
  assert.equal(modelName(options, "gemini-3.7-flash"), "Gemini 3.7 Flash");
  assert.equal(modelName(options, "llama3.2:3b"), "llama3.2:3b");
});

test("four providers, in the order the screen lists them", () => {
  assert.deepEqual([...PROVIDERS], ["openai", "anthropic", "gemini", "openrouter"]);
  assert.equal(providerLabel("anthropic"), "Claude");
  assert.equal(providerLabel("openrouter"), "OpenRouter");
});

test("an id is hidden when the name is only the provider plus the id", () => {
  assert.equal(showsModelId({ id: "sonnet-9", label: "Claude Sonnet-9" }), false);
  assert.equal(showsModelId({ id: "x-1", label: "Anthropic X-1" }), false);
  assert.equal(showsModelId({ id: "x-1", label: "OpenRouter X-1" }), false);
  assert.equal(showsModelId({ id: "x-1", label: "Fancy X-1" }), true);
});

const KEYS = {
  api_key_configured: true,
  gemini_api_key_configured: false,
  anthropic_api_key_configured: false,
  openrouter_api_key_configured: true,
  custom_endpoint: false,
  model_options: [
    { id: "gpt-a", provider: "openai" },
    { id: "gem-a", provider: "gemini" },
    { id: "cl-a", provider: "anthropic" },
  ],
};

test("a role warns when its model's provider has no key saved", () => {
  assert.equal(keyWarning("Fast model", "gem-a", KEYS), "Fast model uses Gemini, but no Gemini key is saved.");
  assert.equal(keyWarning("Smart model", "cl-a", KEYS), "Smart model uses Claude, but no Claude key is saved.");
  assert.equal(keyWarning("Assistant model", "gpt-a", KEYS), undefined);
  assert.equal(keyWarning("Fast model", "unknown", KEYS), undefined);
});

test("a custom AI server stands in for the OpenAI key only", () => {
  const custom = { ...KEYS, api_key_configured: false, custom_endpoint: true };
  assert.equal(keyWarning("Fast model", "gpt-a", custom), undefined);
  assert.equal(keyWarning("Fast model", "gem-a", custom), "Fast model uses Gemini, but no Gemini key is saved.");
  assert.equal(
    keyWarning("Fast model", "gpt-a", { ...KEYS, api_key_configured: false }),
    "Fast model uses OpenAI, but no OpenAI key is saved.",
  );
});

const everyday = (over: Partial<EverydayState> = {}): EverydayState => ({
  api_key_configured: false,
  gemini_api_key_configured: false,
  anthropic_api_key_configured: true,
  openrouter_api_key_configured: false,
  custom_endpoint: false,
  model_options: [
    { id: "claude-haiku", provider: "anthropic" },
    { id: "claude-sonnet", provider: "anthropic" },
    { id: "gpt-luna", provider: "openai" },
  ],
  fast_model: "claude-haiku",
  smart_model: "claude-sonnet",
  chat_model: "claude-haiku",
  capabilities: {},
  ...over,
});
const passes = { text: true, json: true, tools: true };

test("the everyday jobs name where they run, in screen order", () => {
  assert.deepEqual(runsOn(everyday()), ["Claude"]);
  assert.deepEqual(runsOn(everyday({ fast_model: "gpt-luna" })), ["OpenAI", "Claude"]);
  // A custom server takes the OpenAI-style models and any the list lacks; Claude's stay Claude's.
  assert.deepEqual(runsOn(everyday({ custom_endpoint: true, fast_model: "llama3" })), ["Claude", "your own AI server"]);
  assert.deepEqual(runsOn(everyday({ custom_endpoint: true, fast_model: "gpt-luna", smart_model: "x", chat_model: "y" })), ["your own AI server"]);
  assert.deepEqual(keysInUse(everyday({ fast_model: "gpt-luna" })), ["openai", "anthropic"]);
  assert.deepEqual(keysInUse(everyday({ fast_model: "gpt-luna", custom_endpoint: true })), ["anthropic"]);
});

test("the status is the worst of the three jobs, from saved test results only", () => {
  assert.deepEqual(everydayStatus(everyday({ fast_model: "gpt-luna" })), { kind: "no-key", words: "Add your OpenAI key" });
  assert.equal(everydayStatus(everyday()).kind, "untested");
  const tested = { "claude-haiku": passes, "claude-sonnet": passes };
  assert.deepEqual(everydayStatus(everyday({ capabilities: tested })), { kind: "works", words: "Works" });
  const noTools = { "claude-haiku": { ...passes, tools: false }, "claude-sonnet": passes };
  // The Fast and Assistant models are one model here, so both jobs read its one result.
  assert.deepEqual(everydayStatus(everyday({ capabilities: noTools })), { kind: "cannot", words: "Can't run the Assistant" });
  assert.deepEqual(everydayCan(everyday({ capabilities: noTools })), ["reads jobs", "writes"]);
  assert.deepEqual(everydayCan(everyday()), []);
});
