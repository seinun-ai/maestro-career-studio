import assert from "node:assert/strict";
import { test } from "node:test";

import { modelName, providerLabel, showsModelId, sourceLabel } from "./model-catalog.ts";

test("provider and source read as words, never keys", () => {
  assert.equal(providerLabel("openai"), "OpenAI");
  assert.equal(providerLabel("gemini"), "Gemini");
  assert.equal(sourceLabel(undefined), "Built-in");
  assert.equal(sourceLabel("seed"), "Built-in");
  assert.equal(sourceLabel("configured"), "In use");
  assert.equal(sourceLabel("extra"), "Added");
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
