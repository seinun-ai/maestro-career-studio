import { test } from "node:test";
import assert from "node:assert/strict";
import { MIN_RATE_N, rateWords, showsRate } from "./rates.ts";

const rc = (count: number, of: number, rate: number | null, low: number | null = null, high: number | null = null) => ({
  count,
  of,
  rate,
  low,
  high,
});

test("a rate shows only from 20 in its denominator, the server's MIN_RATE_N", () => {
  assert.equal(MIN_RATE_N, 20);
});

test("from 20, the rate reads as a percent with its likely range", () => {
  assert.deepEqual(rateWords(rc(12, 64, 0.1875, 0.111, 0.3)), { value: "19%", range: "11–30%" });
  assert.deepEqual(rateWords(rc(0, 20, 0, 0, 0.161)), { value: "0%", range: "0–16%" });
});

test("below 20 the server sends no rate, and it reads as x of n", () => {
  assert.deepEqual(rateWords(rc(5, 12, null)), { value: "5 of 12", range: null });
  assert.deepEqual(rateWords(rc(5, 12, null), ["reply", "replies"]), { value: "5 of 12 replies", range: null });
  assert.deepEqual(rateWords(rc(1, 1, null), ["interview", "interviews"]), { value: "1 of 1 interview", range: null });
});

test("a rate sent for fewer than 20 still reads as counts: never a rate below 20", () => {
  assert.deepEqual(rateWords(rc(3, 4, 0.75, 0.3, 0.95)), { value: "3 of 4", range: null });
});

test("with nothing to count it is an empty cell, not 0 of 0", () => {
  assert.deepEqual(rateWords(rc(0, 0, null), ["reply", "replies"]), { value: "—", range: null });
});

test("a rate with no range reads alone", () => {
  assert.deepEqual(rateWords(rc(10, 40, 0.25)), { value: "25%", range: null });
});

test("showsRate says when a share reads as a percent", () => {
  assert.equal(showsRate(rc(12, 64, 0.1875, 0.111, 0.3)), true);
  assert.equal(showsRate(rc(5, 12, null)), false);
  assert.equal(showsRate(rc(3, 4, 0.75)), false);
});
