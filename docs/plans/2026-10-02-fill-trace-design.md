# Fill trace: the path each Autofill decision took

Approved by the owner on 2026-10-02 (brainstorming session, approach A).

## Goal

Cut the wrong steps Autofill takes before it decides. The trace should show which
mechanisms work, how accurate the predictions are, and where retries are wasted, so the
engine gets tuned from data and not from DevTools snippets. On 2026-10-02 the iCIMS
veteran and disability fields took three rounds of hand inspection each. The trace would
have pointed at the failing step (label source, map, polarity, pick) in one read.

## Owner decisions

- **Store.** A dedicated local store, not Langfuse. Langfuse is opt-in and usually off. It
  sees only fast-model calls (Jev is not traced), as standalone records with full prompts,
  which hold values.
- **First reader.** Claude, through a script run on a database copy. No panel view yet; a
  later panel view reads the same record.
- **Retention.** The last 50 full run traces, plus running counters that never expire
  (value-free, no host, no labels).
- **Outcomes only.** No record of the user's corrections: the trace measures how the
  engine behaves, not how one person edits. Accuracy comes from (1) the eval's labelled
  cases, run against the live models, and (2) outcome proxies in real runs: a pick the page
  rejected or reverted, a "closest" match instead of an exact one, a confident pick that
  failed verification, and steps that made no progress.
- **Approach A.** The extension assembles the trace, and the backend explains each answer
  it gives. Rejected: (B) both sides write halves joined by a run id, which needs two
  writers, a join and partial-run cleanup; (C) logs only, which keeps no per-run record and
  merges observations across runs.

## The record

One record per Autofill run:

- `run_id` (the loop's existing `newRunId()`), `host`, started and ended time, mode
  ("Saved answers + AI" or "Saved answers only"), the engine setting (jev or fast), and
  `halted` (stopped, or out of time)
- totals: fields seen, filled, left and prefilled, and the rounds used
- `fields`: one entry per field, in page order:
  - **what was read:** `label` (blanked if it holds the written value, as telemetry does),
    `label_source` (label-for, preceding, trailing-text, row-above, …), shape, `section`,
    `required`, option count and option texts (the page's own, capped as telemetry caps
    them), and the widget family (the key the recipe book already computes)
  - **steps:** an ordered list of events. Each has its kind, `ms`, and `effect` (progress,
    no_effect, reverted, refused or error):
    - `map`: route, slot, engine, confidence, threshold, second opinion (not asked, asked
      or decided), `why`
    - `polarity`: way (same, opposite, neither or unsure), engine, confidence
    - `pick`: index of the chosen option, reason, engine, confidence, threshold, second
      opinion
    - `explore` / `step`: move id and the page's outcome word (the existing `adapt`
      history entries)
    - `add` (sections), `sweep` (a revert was caught), `recipe` (a learned move was used)
  - **outcome:** the final status (verified, needs_answer, closest_filled, …) and the
    round it settled in

The trace never holds an answer value, typed text, a prompt, or the profile's own words.

## Learning from many runs

`autofill_mechanism_stats` holds running counters, with no host and no label:

- move × widget family: tries, progress, no_effect, ms
- decision kind (map, polarity, pick, step) × engine × confidence band (0.1 wide): count,
  and the outcome proxies (kept, rejected or reverted, failed verification)
- second opinion: asked, overturned, and whether the overturn was then kept

`scripts/fill_trace.py`, run on a database copy (the eval's rule, which refuses the live
file):

- `last [--host X]` prints one run, field by field
- `report` prints the moves that waste most time per widget family, the confidence-band
  table, the second opinion's value, the fields that took the most steps, and suggested
  threshold changes with the evidence for each

## How it is built

**Backend: each answer explained, value-free by construction.** The `/map`, `/pick` and
`/step` responses gain a per-field `trace` made only of enums and numbers: engine,
confidence, threshold and second opinion, plus the direction verdict on a pick. The
services already compute these and discard them (only logged, or recovered by the eval
through monkeypatching); they are now returned.

**Backend: storage.**

- `POST /api/autofill/runs` takes one run. The schema is strict (`extra="forbid"`), with
  caps of 200 fields, 40 steps per field and 160-character labels.
- Table `autofill_runs` holds one row per run, pruned to the newest 50 on each write.
- Table `autofill_mechanism_stats` holds the counters, updated in the same write.
- The existing Clear (`DELETE /api/autofill/telemetry`) also deletes the runs; the counters
  stay, since they hold nothing personal.
- The capture switch (`telemetryEnabled`) turns the trace off with telemetry.

**Extension.**

- The fill loop gets a recorder. Each decision point appends to it: map result, polarity,
  pick, every explore and step move with its ms and effect, sweep catches, recipe use, and
  the final outcome.
- At the end of a run, a stopped or cut-short one included (marked `halted`), the panel
  sends one `fill_trace` message.
- The service worker scrubs it against a whitelist, as `scrubObservation` does, and posts
  it.

## Tests

- **Privacy:**
  - A full harness run with known answer values never contains them anywhere in the
    posted trace.
  - The service-worker whitelist drops unknown keys.
  - The backend rejects extra keys.
  - The `/map`, `/pick` and `/step` `trace` objects hold only the allowed enums and numbers.
- **Backend:** pruning to 50, counter increments, the confidence-band edges, that Clear
  deletes runs and keeps counters, and the switch.
- **Loop:** a harness run records the right events in order, including a stopped run; ms
  and effect are set on every move.
- **Script:** `last` and `report` on a synthetic database copy; the live file is refused.
- **Live check:** one real Autofill run, then `fill_trace.py last` reads it back.

## Not in this build

- A panel view: later, from the same record.
- Langfuse links.
- User corrections.
- Changing any decision rule: the trace only observes. Tuning is a later batch, driven by
  what `report` shows.
