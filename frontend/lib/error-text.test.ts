import assert from "node:assert/strict";
import { test } from "node:test";

import { couldnt, errorDetail, isPlainSentence, loadErrorDetail } from "./error-text.ts";

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
  const refused = "refused your API key. Check it in Settings › AI & models.";
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
  for (const [text, who] of [
    ["OpenAI API request failed: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-abc. You can find your API key at https://platform.openai.com/account/api-keys.', 'type': 'invalid_request_error', 'code': 'invalid_api_key'}}", "OpenAI"],
    ["OpenAI models.list failed: Error code: 401 - {'error': {'code': 'invalid_api_key'}}", "OpenAI"],
    ['Gemini models.list failed: 400 {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}', "Gemini"],
  ]) {
    assert.equal(errorDetail(new Error(text)), `${who} ${refused}`, text);
  }
  assert.equal(couldnt("find models", new Error("GEMINI_API_KEY is required for Gemini models")), `Couldn't find models. ${missing}`);
  // A sentence that only mentions a key is not a key error.
  assert.equal(
    errorDetail(new Error("The Assistant needs an API key. Add one in Settings › AI & models.")),
    "The Assistant needs an API key. Add one in Settings › AI & models.",
  );
});

/** An ApiError's shape (lib/api.ts), without importing it: error-text.ts stays pure. */
function apiError(status: number, message: string, body: unknown = null): Error {
  return Object.assign(new Error(message), { status, body });
}

test("a load error says why it failed, and only a network failure says the app isn't running", () => {
  const down = "Maestro CS isn't responding. Check that it's running, then try again.";
  // lib/api.ts (the browser's fetch failed) and the proxy's 502 both write this sentence.
  assert.equal(loadErrorDetail(apiError(0, down), "job"), down);
  assert.equal(loadErrorDetail(apiError(502, down), "job"), down);
  // A running backend: the job was deleted, the link is malformed, or the server failed.
  assert.equal(loadErrorDetail(apiError(404, "Job not found"), "job"), "This job may have been deleted.");
  assert.equal(loadErrorDetail(apiError(404, "Application not found"), "application"), "This application may have been deleted.");
  const pathError = { detail: [{ type: "uuid_parsing", loc: ["path", "job_id"], msg: "Input should be a valid UUID" }] };
  assert.equal(
    loadErrorDetail(apiError(422, "Some details weren't accepted. Check them and try again.", pathError), "job"),
    "This link doesn't point to a job.",
  );
  assert.equal(
    loadErrorDetail(apiError(422, "Some details weren't accepted. Check them and try again.", pathError), "application"),
    "This link doesn't point to an application.",
  );
  assert.equal(loadErrorDetail(apiError(500, "sqlite3.OperationalError: database is locked"), "job"), "Something went wrong on our side. Try again.");
  assert.equal(loadErrorDetail(apiError(500, "Something went wrong. Try again."), "job"), "Something went wrong on our side. Try again.");
  // A server sentence written for the user still wins (a provider's words, a plain 409).
  assert.equal(
    loadErrorDetail(apiError(502, "OpenAI refused your API key. Check it in Settings › AI & models."), "job"),
    "OpenAI refused your API key. Check it in Settings › AI & models.",
  );
  // A list has no "this thing": a 404 or 422 there is the server's fault, never a deleted item.
  assert.equal(loadErrorDetail(apiError(404, "Not Found")), "Something went wrong on our side. Try again.");
  assert.equal(loadErrorDetail(new Error("boom")), "Something went wrong on our side. Try again.");
});

test("a refused key names who refused it", () => {
  assert.equal(
    errorDetail(new Error("Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-abc', 'code': 'invalid_api_key'}}")),
    "OpenAI refused your API key. Check it in Settings › AI & models.",
  );
  assert.equal(
    errorDetail(new Error('Gemini models.list failed: 400 {"error": {"message": "API key not valid.", "details": [{"reason": "API_KEY_INVALID"}]}}')),
    "Gemini refused your API key. Check it in Settings › AI & models.",
  );
});

test("the server's own refused-key sentences keep the fix, whichever wording it sent", () => {
  // backend/app/services/llm.py `_no_answer` for a refused key, and its wording before this change.
  for (const text of [
    "OpenAI refused your API key. Check it in Settings › AI & models.",
    "Gemini refused your API key. Check it in Settings › AI & models.",
    "Your AI server refused your API key. Check it in Settings › AI & models.",
  ]) {
    assert.equal(errorDetail(new Error(text)), text, text);
  }
  assert.equal(
    errorDetail(new Error("The AI model didn't answer (your key was refused). Try again, or check your key in Settings › AI & models.")),
    "The AI provider refused your API key. Check it in Settings › AI & models.",
  );
});
