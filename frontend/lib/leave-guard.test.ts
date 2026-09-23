import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allowLeave,
  consumeLeaveBypass,
  leaveBlocked,
  onInAppBlockedChange,
  setLeaveGuard,
} from "./leave-guard.ts";

function release(owner: string) {
  setLeaveGuard(owner, null);
}

test("an empty registry blocks neither exit", () => {
  assert.equal(leaveBlocked("in-app"), false);
  assert.equal(leaveBlocked("unload"), false);
});

test("an unload owner warns on reload only", () => {
  setLeaveGuard("unload-only", "unload");
  try {
    assert.equal(leaveBlocked("unload"), true);
    assert.equal(leaveBlocked("in-app"), false);
  } finally {
    release("unload-only");
  }
});

test("an all owner blocks both exits", () => {
  setLeaveGuard("all-owner", "all");
  try {
    assert.equal(leaveBlocked("in-app"), true);
    assert.equal(leaveBlocked("unload"), true);
  } finally {
    release("all-owner");
  }
});

test("removing the last all owner fires the listener with false once", () => {
  const seen: boolean[] = [];
  const stop = onInAppBlockedChange((blocked) => seen.push(blocked));
  try {
    setLeaveGuard("listener-a", "all");
    setLeaveGuard("listener-b", "all");
    setLeaveGuard("listener-a", null);
    setLeaveGuard("listener-b", null);
    assert.deepEqual(seen, [true, false]);
  } finally {
    stop();
    release("listener-a");
    release("listener-b");
  }
});

test("re-setting the same scope fires nothing", () => {
  const seen: boolean[] = [];
  const stop = onInAppBlockedChange((blocked) => seen.push(blocked));
  try {
    setLeaveGuard("same-scope", "all");
    setLeaveGuard("same-scope", "all");
    assert.deepEqual(seen, [true]);
  } finally {
    stop();
    release("same-scope");
  }
});

test("consumeLeaveBypass is true once, then false", () => {
  allowLeave();
  assert.equal(consumeLeaveBypass(), true);
  assert.equal(consumeLeaveBypass(), false);
});
