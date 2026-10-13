import assert from "node:assert/strict";
import { test } from "node:test";

import { inOrder } from "./in-order.ts";

/** A promise settled from outside, to hold a call open. */
function gate<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("calls with one key run in the order they were made, each after the last settles", async () => {
  const log: string[] = [];
  const first = gate();
  const a = inOrder("k", async () => {
    log.push("a start");
    await first.promise;
    log.push("a end");
    return "a";
  });
  const b = inOrder("k", async () => {
    log.push("b start");
    return "b";
  });
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(log, ["a start"], "b waits for a");
  first.resolve();
  assert.deepEqual(await Promise.all([a, b]), ["a", "b"]);
  assert.deepEqual(log, ["a start", "a end", "b start"]);
});

test("a rejection reaches its own caller and does not block the next call", async () => {
  const a = inOrder("k2", () => Promise.reject(new Error("boom")));
  const b = inOrder("k2", async () => "ok");
  await assert.rejects(a, /boom/);
  assert.equal(await b, "ok");
});

test("different keys do not wait on each other", async () => {
  const held = gate();
  const slow = inOrder("one", () => held.promise.then(() => "slow"));
  assert.equal(await inOrder("two", async () => "fast"), "fast");
  held.resolve();
  assert.equal(await slow, "slow");
});

test("a key is free again once its calls have settled", async () => {
  await inOrder("k3", async () => 1);
  await new Promise((r) => setTimeout(r, 0));
  const ran: number[] = [];
  await inOrder("k3", async () => ran.push(2));
  assert.deepEqual(ran, [2]);
});
