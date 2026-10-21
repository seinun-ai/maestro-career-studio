import assert from "node:assert/strict";
import { test } from "node:test";

import { NO_EDITS, edited, landed, surfaceStatus, type SurfaceSaves } from "./save-surfaces.ts";

// What `useAutosave` reports for the one value: a write in flight or queued, and the newest value not on the server.
const SAVING = { pending: true, failed: false };
const FAILED = { pending: false, failed: true };
const RETRYING = { pending: true, failed: true };
const IDLE = { pending: false, failed: false };

/** Each editor's status at once. */
const shown = (state: SurfaceSaves, save: typeof SAVING, ...surfaces: string[]) =>
  Object.fromEntries(surfaces.map((surface) => [surface, surfaceStatus(state, surface, save)]));

test("an edit in another editor within one round trip leaves the first one saving until its write lands", () => {
  // A Phone typed in Next up: the write that goes out now carries it.
  let state = edited(NO_EDITS, "next-up");
  const first = state.seq;
  // Contact is typed before that write answers: queued behind it.
  state = edited(state, "contact");
  assert.deepEqual(shown(state, SAVING, "next-up", "contact"), {
    "next-up": { pending: true, failed: false },
    contact: { pending: true, failed: false },
  });
  // The first write lands: the phone is on the server, and only Contact still waits for the queued one.
  state = landed(state, first);
  assert.deepEqual(shown(state, SAVING, "next-up", "contact"), {
    "next-up": { pending: false, failed: false },
    contact: { pending: true, failed: false },
  });
  // The queued write fails: Contact says so, and Next up, whose edit is on the server, does not.
  assert.deepEqual(shown(state, FAILED, "next-up", "contact"), {
    "next-up": { pending: false, failed: false },
    contact: { pending: false, failed: true },
  });
});

test("a failed write fails every editor whose edit it carried, until a write carrying them lands", () => {
  let state = edited(NO_EDITS, "next-up");
  state = edited(state, "contact");
  // The first write failed and the queued one, carrying both edits, failed too.
  assert.deepEqual(shown(state, FAILED, "next-up", "contact"), {
    "next-up": { pending: false, failed: true },
    contact: { pending: false, failed: true },
  });
  // Try again: both are saving again, then both are saved once that write lands.
  assert.deepEqual(shown(state, RETRYING, "next-up", "contact"), {
    "next-up": { pending: true, failed: true },
    contact: { pending: true, failed: true },
  });
  state = landed(state, state.seq);
  assert.deepEqual(shown(state, IDLE, "next-up", "contact"), {
    "next-up": { pending: false, failed: false },
    contact: { pending: false, failed: false },
  });
});

test("an editor with no edit announces no save, whoever is saving", () => {
  const state = edited(NO_EDITS, "contact");
  assert.deepEqual(surfaceStatus(state, "diversity", SAVING), { pending: false, failed: false });
  assert.deepEqual(surfaceStatus(state, "diversity", FAILED), { pending: false, failed: false });
});

test("a later edit in the same editor waits for the write that carries it, not the one before", () => {
  let state = edited(NO_EDITS, "contact");
  const first = state.seq;
  state = edited(state, "contact");
  state = landed(state, first);
  assert.deepEqual(surfaceStatus(state, "contact", SAVING), { pending: true, failed: false });
  state = landed(state, state.seq);
  assert.deepEqual(surfaceStatus(state, "contact", IDLE), { pending: false, failed: false });
});

test("an older write landing late never unsaves a newer one", () => {
  let state = edited(NO_EDITS, "contact");
  const first = state.seq;
  state = edited(state, "start");
  state = landed(state, state.seq);
  state = landed(state, first);
  assert.equal(state.saved, state.seq);
  assert.deepEqual(surfaceStatus(state, "start", SAVING), { pending: false, failed: false });
});
