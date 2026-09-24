import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isRemoteEndpoint,
  modelName,
  providerLabel,
  showsModelId,
  sourceLabel,
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
  assert.equal(showsModelId({ id: "gpt-5.6-luna", label: "OpenAI GPT-5.6 Luna" }), true);
  assert.equal(showsModelId({ id: "gpt-6-luna", label: "gpt-6-luna" }), false);
  assert.equal(showsModelId({ id: "gpt-6-luna", label: " gpt-6-luna " }), false);
});

test("a model is named by its label, else its id", () => {
  const options = [{ id: "gemini-3.7-flash", label: "Gemini 3.7 Flash" }];
  assert.equal(modelName(options, "gemini-3.7-flash"), "Gemini 3.7 Flash");
  assert.equal(modelName(options, "llama3.2:3b"), "llama3.2:3b");
});
