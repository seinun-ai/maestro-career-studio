import assert from "node:assert/strict";
import { test } from "node:test";

import { keyFormatProblem, keysSavedText } from "./api-key-format.ts";

test("a key in the wrong shape is refused plainly, before any call", () => {
  assert.equal(keyFormatProblem("openai", "sk-proj-abc123", false), undefined);
  assert.equal(keyFormatProblem("gemini", "AIzaSyAbc", false), undefined);
  assert.equal(
    keyFormatProblem("openai", "hello", false),
    "An OpenAI API key starts with sk-. Check that you copied the whole key.",
  );
  assert.equal(
    keyFormatProblem("gemini", "sk-proj-abc", false),
    "A Gemini API key starts with AIza. Check that you copied the whole key.",
  );
  // Spaces from a copy are not the key's fault; an empty field removes the key.
  assert.equal(keyFormatProblem("openai", "  sk-abc  ", false), undefined);
  assert.equal(keyFormatProblem("openai", "", false), undefined);
  // A custom AI server's key has its own shape, whatever it is.
  assert.equal(keyFormatProblem("openai", "local-key", true), undefined);
});

test("a saved key is not called working: it is checked on first use", () => {
  assert.equal(keysSavedText({ openai_api_key: "sk-a" }), "API key saved. We'll check it on first use.");
  assert.equal(
    keysSavedText({ openai_api_key: "sk-a", gemini_api_key: "AIza" }),
    "API keys saved. We'll check them on first use.",
  );
  assert.equal(keysSavedText({ gemini_api_key: null }), "API key removed.");
  assert.equal(keysSavedText({ openai_api_key: null, gemini_api_key: null }), "API keys removed.");
});
