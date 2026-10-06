import assert from "node:assert/strict";
import test from "node:test";
import { jobOwnershipView, isSyncQueued, syncActionMessage } from "./job-ownership.ts";

const off = { owned_here: true, owner: null, handover: null, pending_requests: 0 };

test("sync off keeps every control available and has no mark", () => {
  assert.deepEqual(jobOwnershipView(off), {
    mark: null, action: null, canWrite: true, canRequest: true, reason: null, pending: false,
  });
});

test("a bot replica keeps request actions and locks all other writes", () => {
  assert.deepEqual(jobOwnershipView({ ...off, owned_here: false, owner: "bot" }), {
    mark: "With your bot", action: "work-here", canWrite: false, canRequest: true,
    reason: "This job is with your bot. Ask for it back with Work on it here.", pending: false,
  });
});

test("an offer locks requests until kept here", () => {
  assert.deepEqual(jobOwnershipView({ ...off, owned_here: false, owner: "laptop", handover: "offered" }), {
    mark: "Going to your bot", action: "keep-here", canWrite: false, canRequest: false,
    reason: "This job is on its way to your bot. Use Keep it here to keep working on it.", pending: false,
  });
});

test("a laptop replica cannot be requested through the home-only button", () => {
  const view = jobOwnershipView({ ...off, owned_here: false, owner: "laptop" });
  assert.equal(view.mark, "On your laptop");
  assert.equal(view.action, null);
  assert.equal(view.reason, "This job is on your laptop. Work on it there.");
});

test("returning jobs stay locked while their final bundle travels", () => {
  const view = jobOwnershipView({ ...off, owned_here: false, owner: "bot", handover: "returning" });
  assert.equal(view.canWrite, false);
  assert.equal(view.canRequest, false);
  assert.equal(view.action, null);
});

test("unanswered requests show their actual pending state", () => {
  assert.equal(jobOwnershipView({ ...off, owner: "bot", pending_requests: 2 }).pending, true);
});

test("a queued response never reports the requested change as saved", () => {
  assert.equal(isSyncQueued({ queued: true, detail: "Sent at the next sync." }), true);
  assert.equal(isSyncQueued({ queued: false }), false);
  assert.equal(isSyncQueued(null), false);
  assert.equal(syncActionMessage({ queued: true, detail: "Private text" }, "Saved"), "Sent at the next sync");
  assert.equal(syncActionMessage({ id: "local" }, "Saved"), "Saved");
});


test("unknown ownership cannot silently enable writes or requests", () => {
  const view = jobOwnershipView(undefined);
  assert.equal(view.canWrite, false);
  assert.equal(view.canRequest, false);
  assert.equal(view.reason, "Check where this job is being worked on before making changes.");
});
