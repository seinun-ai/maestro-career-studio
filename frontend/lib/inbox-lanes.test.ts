import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  INBOX_LANES,
  NEEDS_YOU_STATUSES,
  STATUS_ORDER,
  inLane,
  laneOf,
  needsYouHelp,
  needsYouLine,
  selectedAmong,
} from "./inbox-lanes.ts";

/** `PROPOSAL_STATUSES` as lib/types.ts spells it (types.ts is not loadable here: it imports without an extension). */
function proposalStatuses(): string[] {
  const src = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
  const body = /const PROPOSAL_STATUSES = \[([^\]]*)\] as const;/.exec(src)?.[1];
  assert.ok(body, "PROPOSAL_STATUSES moved out of lib/types.ts");
  return [...body.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
}

test("every status is in exactly one lane", () => {
  const statuses = proposalStatuses();
  assert.equal(statuses.length, 9);
  for (const status of statuses) {
    const lanes = Object.entries(INBOX_LANES).filter(([, members]) => (members as readonly string[]).includes(status));
    assert.equal(lanes.length, 1, `${status} is in ${lanes.length} lanes`);
    assert.equal(laneOf(status), lanes[0][0]);
  }
  // Nothing in a lane that is not a status.
  assert.deepEqual([...STATUS_ORDER].sort(), [...statuses].sort());
});

test("the lanes hold the owner's statuses", () => {
  assert.equal(laneOf("needs_decision"), "needs_you");
  assert.equal(laneOf("needs_human"), "needs_you");
  assert.equal(laneOf("pending_review"), "triage");
  assert.equal(laneOf("accepted"), "queued");
  assert.equal(laneOf("approved"), "in_flight");
  for (const s of ["submitted", "submission_uncertain", "rejected", "expired"]) assert.equal(laneOf(s), "history", s);
  assert.equal(laneOf("from_a_newer_backend"), null);
});

test("the Needs you lane is the sidebar count's list", () => {
  assert.deepEqual([...NEEDS_YOU_STATUSES], ["needs_decision", "needs_human"]);
  assert.equal(NEEDS_YOU_STATUSES, INBOX_LANES.needs_you);
});

test("every status has a chip label: STATUS_ORDER lists each once, lane by lane", () => {
  assert.equal(new Set(STATUS_ORDER).size, STATUS_ORDER.length);
  assert.deepEqual(STATUS_ORDER, [
    "needs_decision",
    "needs_human",
    "pending_review",
    "accepted",
    "approved",
    "submitted",
    "submission_uncertain",
    "rejected",
    "expired",
  ]);
});

test("inLane keeps a lane's items in their order", () => {
  const items = [
    { id: "a", status: "needs_human" },
    { id: "b", status: "pending_review" },
    { id: "c", status: "needs_decision" },
    { id: "d", status: "expired" },
  ];
  assert.deepEqual(inLane(items, "needs_you").map((p) => p.id), ["a", "c"]);
  assert.deepEqual(inLane(items, "history").map((p) => p.id), ["d"]);
  assert.deepEqual(inLane(items, "queued"), []);
});

test("only selected rows that are shown are acted on", () => {
  const shown = [{ id: "a" }, { id: "b" }, { id: "c" }];
  // "x" is hidden by a filter; "d" has left the lane.
  assert.deepEqual(selectedAmong(shown, new Set(["x", "c", "a", "d"])), ["a", "c"]);
  assert.deepEqual(selectedAmong(shown, new Set()), []);
  assert.deepEqual(selectedAmong([], new Set(["a"])), []);
});

test("a Needs-you row says what the agent needs, in its own words when it gave some", () => {
  assert.equal(
    needsYouLine("needs_decision", "Salary is below your minimum; do you still want this?"),
    "Your agent asks: Salary is below your minimum; do you still want this?",
  );
  assert.equal(needsYouLine("needs_decision", null), "Your agent has a question about this job.");
  assert.equal(
    needsYouLine("needs_human", "The form asks for a portfolio upload."),
    "Your agent stopped: The form asks for a portfolio upload.",
  );
  assert.equal(needsYouLine("needs_human", "  "), "Your agent stopped and needs you to finish a step.");
  assert.equal(needsYouLine("pending_review", "x"), null);
});

test("the Needs-you lane says how each kind is answered, once", () => {
  assert.deepEqual(needsYouHelp([]), []);
  const both = needsYouHelp(["needs_decision", "needs_human", "needs_decision"]);
  assert.equal(both.length, 2);
  assert.match(both[0], /^Keep it answers yes: the job goes back to To review\. Skip answers no\.$/);
  // needs_human has no answer in this app: the agent is waiting in its own chat.
  assert.match(both[1], /in your agent's own chat/);
  assert.deepEqual(needsYouHelp(["needs_human"]), [both[1]]);
});
