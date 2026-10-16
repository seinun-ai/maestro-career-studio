import assert from "node:assert/strict";
import { test } from "node:test";

import { nextStep, nextStepHref } from "./next-step.ts";

const none = {};

test("a saved job's next step is Score, a ghost on the fit tab", () => {
  assert.deepEqual(nextStep("saved", none), { label: "Score", variant: "ghost", tab: "fit" });
});

test("a scored job's next step is Analyze gaps, a ghost on the fit tab", () => {
  assert.deepEqual(nextStep("scored", none), { label: "Analyze gaps", variant: "ghost", tab: "fit" });
});

test("open gaps continue the gap analysis with its counts, outlined, through its session", () => {
  const step = nextStep("gaps", { open_session_id: "s-1", gaps_done: 2, gaps_total: 5 });
  assert.deepEqual(step, { label: "Continue gaps · 2 of 5", variant: "outline", tab: "fit", session: "s-1" });
});

test("gaps without counts read zero of zero, never undefined", () => {
  assert.equal(nextStep("gaps", none)?.label, "Continue gaps · 0 of 0");
});

test("a tailored draft is reviewed on the output tab, outlined", () => {
  assert.deepEqual(nextStep("tailored", none), { label: "Review resume", variant: "outline", tab: "output" });
});

test("a ready PDF is Apply, tonal and never filled, on the qa tab", () => {
  assert.deepEqual(nextStep("pdf_ready", none), { label: "Apply", variant: "tonal", tab: "qa" });
});

test("an applied or closed job shows no control: the status chip carries it", () => {
  assert.equal(nextStep("applied", none), null);
  assert.equal(nextStep("closed", none), null);
});

test("a row from a backend that predates the stage shows no control", () => {
  assert.equal(nextStep(undefined, none), null);
});

test("each tab links the job page with that tab", () => {
  assert.equal(nextStepHref("j-1", { label: "Score", variant: "ghost", tab: "fit" }), "/jobs/j-1?tab=fit");
  assert.equal(nextStepHref("j-1", { label: "Review resume", variant: "outline", tab: "output" }), "/jobs/j-1?tab=output");
  assert.equal(nextStepHref("j-1", { label: "Apply", variant: "tonal", tab: "qa" }), "/jobs/j-1?tab=qa");
});

test("open gaps link the gap analysis itself", () => {
  const step = nextStep("gaps", { open_session_id: "s-1", gaps_done: 2, gaps_total: 5 });
  assert.ok(step);
  assert.equal(nextStepHref("j-1", step), "/jobs/j-1/tailor/s-1");
});

test("gaps without a session id fall back to the fit tab", () => {
  const step = nextStep("gaps", { open_session_id: null });
  assert.ok(step);
  assert.equal(nextStepHref("j-1", step), "/jobs/j-1?tab=fit");
});
