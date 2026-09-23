import assert from "node:assert/strict";
import { test } from "node:test";

import { startOnce } from "./single-flight.ts";

/** A mutation that records each start and settles only when told to. */
function mutation() {
  const started: string[] = [];
  const settle: Array<() => void> = [];
  const mutate = (vars: string, options?: { onSettled?: () => void }) => {
    started.push(vars);
    settle.push(() => options?.onSettled?.());
  };
  return { started, settle, mutate };
}

test("a second call while the first runs starts nothing", () => {
  const lock = { current: false };
  const m = mutation();
  startOnce(lock, m.mutate, "first");
  startOnce(lock, m.mutate, "second");
  assert.deepEqual(m.started, ["first"]);
  assert.equal(lock.current, true);
});

test("the lock opens when the request settles, success or error", () => {
  const lock = { current: false };
  const m = mutation();
  startOnce(lock, m.mutate, "first");
  m.settle[0]();
  assert.equal(lock.current, false);
  startOnce(lock, m.mutate, "retry");
  assert.deepEqual(m.started, ["first", "retry"]);
});

test("the lock is shut before the request starts", () => {
  const lock = { current: false };
  let shutWhenStarted: boolean | null = null;
  startOnce(lock, () => {
    shutWhenStarted = lock.current;
  }, "only");
  assert.equal(shutWhenStarted, true);
});
