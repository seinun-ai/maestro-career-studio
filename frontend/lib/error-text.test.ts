import assert from "node:assert/strict";
import { test } from "node:test";

import { couldnt, errorDetail, isPlainSentence } from "./error-text.ts";

test("a plain sentence passes; code, JSON and fragments do not", () => {
  assert.equal(isPlainSentence("This resume no longer exists."), true);
  assert.equal(isPlainSentence("Maestro CS isn't responding. Check that it's running, then try again."), true);
  assert.equal(isPlainSentence("slug must be lowercase alphanumeric with underscores"), false);
  assert.equal(isPlainSentence('[{"loc":["body","title"],"msg":"field required"}]'), false);
  assert.equal(isPlainSentence("experience.2.bullets.0: String must contain at least 1 character(s)"), false);
  assert.equal(isPlainSentence("Application not found"), false);
  assert.equal(isPlainSentence("Upstream fetch failed (http://127.0.0.1:8001): fetch failed"), false);
  assert.equal(isPlainSentence(`${"A".repeat(240)}.`), false);
});

test("couldnt names what failed, then the plain detail or Try again", () => {
  assert.equal(
    couldnt("save the resume", new Error("A section with this name already exists.")),
    "Couldn't save the resume. A section with this name already exists.",
  );
  assert.equal(couldnt("save the resume", new Error("Request failed: 500")), "Couldn't save the resume. Try again.");
  assert.equal(couldnt("save the resume", "boom"), "Couldn't save the resume. Try again.");
});

test("errorDetail hides what is not for the user", () => {
  assert.equal(errorDetail(new Error("Target entity not found")), undefined);
  assert.equal(errorDetail(new Error("  This job was deleted.  ")), "This job was deleted.");
  assert.equal(errorDetail(null), undefined);
});

test("a missing or refused API key says what to do, whatever the server's words", () => {
  const missing = "Add an API key in Settings › AI & models.";
  const refused = "Check your API key in Settings › AI & models.";
  // backend/app/services/llm.py, as the server sends them (a 502 detail).
  for (const text of [
    "No OpenAI API key configured. Add one under Settings → Models in the web app, or set OPENAI_API_KEY in .env and restart the backend. To use a local model instead, set an OpenAI-compatible endpoint under Settings → Models.",
    "GEMINI_API_KEY is required for Gemini models",
    "No Gemini API key configured. Add one under Settings → Models.",
    "No API key is set. Add one in Settings › AI & models › API keys. To use a model on your computer instead, add its address in Settings › AI & models › Custom AI server.",
    "No Gemini API key is set. Add one in Settings › AI & models.",
  ]) {
    assert.equal(errorDetail(new Error(text)), missing, text);
  }
  for (const text of [
    "OpenAI API request failed: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-abc. You can find your API key at https://platform.openai.com/account/api-keys.', 'type': 'invalid_request_error', 'code': 'invalid_api_key'}}",
    "OpenAI models.list failed: Error code: 401 - {'error': {'code': 'invalid_api_key'}}",
    'Gemini models.list failed: 400 {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}',
  ]) {
    assert.equal(errorDetail(new Error(text)), refused, text);
  }
  assert.equal(couldnt("find models", new Error("GEMINI_API_KEY is required for Gemini models")), `Couldn't find models. ${missing}`);
  // A sentence that only mentions a key is not a key error.
  assert.equal(
    errorDetail(new Error("The Assistant needs an API key. Add one in Settings › AI & models.")),
    "The Assistant needs an API key. Add one in Settings › AI & models.",
  );
});
