import assert from "node:assert/strict";
import test from "node:test";
import {
  jobOwnershipView, isOwnershipRefusal, isSyncQueued, ownershipReason, ownershipSays, ownershipWhere, syncActionMessage,
} from "./job-ownership.ts";

const off = { owned_here: true, owner: null, handover: null, pending_requests: 0 };

test("sync off keeps every control available and has no mark", () => {
  assert.deepEqual(jobOwnershipView(off), {
    mark: null, action: null, canWrite: true, canRequest: true, reason: null, pending: false,
  });
});

test("a bot replica keeps request actions and locks all other writes", () => {
  assert.deepEqual(jobOwnershipView({ ...off, owned_here: false, owner: "bot" }), {
    mark: "With your bot", action: "work-here", canWrite: false, canRequest: true,
    reason: "This job is with your bot; ask for it back with Work on it here.", pending: false,
  });
});

test("an offer locks requests until kept here", () => {
  assert.deepEqual(jobOwnershipView({ ...off, owned_here: false, owner: "laptop", handover: "offered",
    can_keep_here: true }), {
    mark: "Going to your bot", action: "keep-here", canWrite: false, canRequest: false,
    reason: "This job is on its way to your bot. Use Keep it here to keep working on it.", pending: false,
  });
});

test("a laptop replica cannot be requested through the home-only button", () => {
  const view = jobOwnershipView({ ...off, owned_here: false, owner: "laptop" });
  assert.equal(view.mark, "On your laptop");
  assert.equal(view.action, null);
  assert.equal(view.reason, "This job is on your laptop; work on it there.");
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


test("no ownership on a row means sync is off: owned, unmarked and nothing locked", () => {
  assert.deepEqual(jobOwnershipView(undefined), {
    mark: null, action: null, canWrite: true, canRequest: true, reason: null, pending: false,
  });
});

test("the bot's copy of an offered job never offers Keep it here, which only the laptop can do", () => {
  const view = jobOwnershipView({ ...off, owned_here: false, owner: "laptop", handover: "offered" });
  assert.equal(view.action, null);
  assert.equal(view.canWrite, false);
  assert.doesNotMatch(view.reason ?? "", /Keep it here/);
});

test("only the server's other-copy sentences count as an ownership refusal", () => {
  assert.equal(isOwnershipRefusal("This job is with your bot; ask for it back with Work on it here."), true);
  assert.equal(isOwnershipRefusal("This gap analysis is out of date."), false);
  assert.equal(isOwnershipRefusal(undefined), false);
});

test("the Where column says Laptop, Bot or Moving, with the long sentence behind it", () => {
  assert.equal(ownershipWhere(undefined), null);
  assert.equal(ownershipWhere(off), null);
  assert.deepEqual(ownershipWhere({ ...off, owner: "laptop" }),
    { word: "Laptop", bot: false, pending: false, sentence: "On your laptop" });
  const replica = { ...off, owned_here: false, owner: "bot" as const };
  assert.deepEqual(ownershipWhere(replica),
    { word: "Bot", bot: true, pending: false, sentence: ownershipReason(replica) });
  const offered = { ...off, owner: "laptop" as const, handover: "offered", can_keep_here: true };
  assert.deepEqual(ownershipWhere(offered),
    { word: "Moving", bot: false, pending: false, sentence: ownershipReason(offered) });
  // Moving keeps the icon of whoever holds the job now: the bot while it hands the job back.
  const returning = ownershipWhere({ ...off, owned_here: false, owner: "bot", handover: "returning" });
  assert.equal(returning?.word, "Moving");
  assert.equal(returning?.bot, true);
});

test("a request still waiting for the next sync says so in the Where sentence", () => {
  const waiting = ownershipWhere({ ...off, owned_here: false, owner: "bot", pending_requests: 1 });
  assert.equal(waiting?.pending, true);
  assert.equal(waiting?.sentence, `${ownershipReason({ ...off, owned_here: false, owner: "bot" })} · Sent at the next sync`);
});

test("a row's ownership icon shows only when the job is not here or a request waits", () => {
  assert.equal(ownershipSays(undefined), false);
  assert.equal(ownershipSays(off), false);
  assert.equal(ownershipSays({ ...off, owner: "laptop" }), false);
  assert.equal(ownershipSays({ ...off, owned_here: false, owner: "bot" }), true);
  assert.equal(ownershipSays({ ...off, owner: "laptop", handover: "offered", can_keep_here: true }), true);
  assert.equal(ownershipSays({ ...off, owner: "laptop", pending_requests: 1 }), true);
});
