/* Maestro CS Companion — the fill loop.
 *
 * observe → map → explore → pick → commit (+ adaptive step) → sweep → observe.
 * Panel-side: it touches no `document`, `location` or `chrome`; `broadcast`
 * (the per-frame fan-out) and `api` (the backend) arrive as dependencies, as in
 * shared/guided-run.js. Page operations (content/fill-ops.js) are sent ONE AT A
 * TIME and each is awaited: the page serializes them per frame anyway, and a
 * Stop must be able to fall between any two.
 *
 * THE RULES IT KEEPS
 * - Nothing is reported filled without a `verified` outcome from the page. A
 *   set is verified only when every SOURCE item is covered (the item cap
 *   limits work, never the bar); otherwise it is `partial`, and items the
 *   never-fill policy kept back are named apart from the missing ones.
 * - `answered` (not "has a value") decides "already". Unknown controls are
 *   listed as cannot_operate and never mapped. Page refusals (yours, blocked,
 *   unsupported) are final and never retried.
 * - Policy-blocked options are never offered to /pick or /map, nor a popup's
 *   placeholder row ("Select One", or an empty or dash-only one). Every set, search
 *   or native, is picked one source item at a time (`item`); single-answer
 *   fields whose whole list the inventory read are picked together, 40 a call.
 *   Only matched / closest / assumed (and /step's progress) count as answers.
 * - A field whose fingerprint changed under the same fid is a new question:
 *   mapped again, nothing carried over.
 * - A round works LEADS first — a choice whose mapped slot is an entry's
 *   `.current`, which removes that entry's To date when ticked (notes §4) —
 *   then text and dates, then the other choices. After a choice changes the
 *   page, a peek (the frames' fids only) asks whether fields came or went; if
 *   so, a fresh inventory comes before the next field: one that went is
 *   dropped, never written after it went and not reported; one that came is
 *   mapped and joins the round.
 * - A `reasoned` field (answered from the work and education history, /map's
 *   reasoning route) is picked like a low-stakes one, with no slot, and is
 *   never handed to /step, which has no history to answer from: its abstain
 *   is the user's.
 * - When the generic path is surprised (an unexpected commit, no options, an
 *   honest "no option states it" over a popup), /step picks the next move from
 *   the moves the page's code listed. A click is sent `as: "progress"` only when
 *   /step called it progress (a group). A move that progressed (a group or an
 *   unmarked category opened), went stale, or was refused as not_a_group
 *   re-takes the state and steps again. A group click that committed a value
 *   (group_committed) is left for the user, named — never "filled". History is
 *   built only from move ids and outcomes (`mid -> outcome (reason)`), last 8.
 * - ONE CONTROLLER PER FIELD. The generic commit, the adaptive step and a
 *   re-commit are ways of proposing the field's next move, not separate
 *   executors: they share the field's one budget (FIELD_MS, charged for the
 *   time the field was worked, across rounds — a retry never gets a fresh
 *   clock), a state + move pair that failed is never proposed to the page again
 *   (`failedMoves`: the state as shown, the value it was for, the move), and a
 *   field is `unsupported` only once two DIFFERENT kinds of gesture (pointer,
 *   keyboard; typing: two different values) — have had no effect at all
 *   (`no_effect`, with the kinds the page tried) since anything last did.
 * - Never stall: every backend wait is bounded (API_MS, and never past the
 *   field's or the run's clock); the run has a clock; rounds, attempts, steps
 *   and items are capped. A late answer is ignored. Before finishing, a quiet
 *   period (QUIET_MS) and a final sweep give a late reversion the chance to
 *   show: a field the engine wrote that reverted gets ONE re-commit per run,
 *   and a second reversion reports it `unconfirmed` (unstable).
 * - Exploring can commit (a search that finds one hit picks it): the page
 *   takes that back; one it could not take back leaves the field to the user,
 *   named (committed_while_exploring).
 * - REPEATING SECTIONS grow only by their own Add, and an added entry's fields
 *   are REQUIRED (notes §5), so each round, before /map, a section gets Add
 *   pressed only up to the profile entries that can fill one (/sections:
 *   `wanted`): add = wanted − the entries on the page, never more, never a
 *   Delete. Each entry is PLACED at a profile entry by the backend
 *   (/sections `order`, matched on what the entries hold): /map is told it
 *   per field (`profile_entry`, with the section's `entry_kind`; null places
 *   nothing there), so an empty entry before a pre-filled one is never given
 *   the job the page already shows. Two sections of one job, school,
 *   language or website kind are BOTH left alone (`ambiguous_kind`): which one is
 *   misread cannot be told. An order that cannot be read, or a section whose entry titles do
 *   not run 1..N in page order (the backend places by place, the loop finds
 *   an entry by its title's number), leaves the section alone (`unplaced`:
 *   nothing written, nothing added, a report line) — never page order. A
 *   section with no placement at all (/sections failed, the heading read as
 *   none) keeps page order only while every entry is empty; one holding data
 *   leaves the section alone too, as does a job, school, language or website section
 *   with no order at all. Only a kind's placed first section adds entries; one left
 *   alone still spends its kind. One holding data keeps it (`already`).
 *   Each press is a deliberate write, not a trial: once per wanted entry,
 *   counted only when the page's entry count grew; a press that did not grow
 *   it is not pressed again this run. A full inventory follows the adds, so
 *   the new entries' fields are mapped in the same round. The report's
 *   `sections` says what was added, by kind — value-free. The backend leaves
 *   a section whose entry holds something the profile does not have to the
 *   user (`reason` held_unmatched: nothing placed, nothing added), and adds
 *   nothing when two entries hold the same one (held_twice). Within a
 *   section, one fact is written into ONE entry (`in_another_entry`).
 * - RECIPES (`deps.recipes`, optional: { get, record }) remember which of the
 *   engine's own moves worked for a widget family (shared/recipe-book.js). A
 *   popup or search field's recipe is looked up once (by the page's
 *   value-free keys, `f.recipe`) and its ORDER rides with the field's
 *   explores and its commit (`variant`) — a proposal to the one controller,
 *   never a separate path: same budget, same `failedMoves`, same gates,
 *   verification unchanged. Text and passive choices (a signature box, a
 *   consent tick) are written once, on a decision, and never looked up. Only
 *   once the final sweep has reached the page (never after Stop, the run's
 *   clock, or a page gone) does the book hear each field's lesson: `kept`
 *   (the commit's moves verified, nothing reverted them, and the final sweep
 *   re-checked the value and found it holding; a filled value it could not
 *   re-check is never kept), `contradicted` (an unconfirmed commit, or a
 *   value the sweep found reverted — re-committed or not) or `mismatch` (the
 *   control could not take the learned move). A failing store costs nothing.
 * - Nothing is guessed when the AI cannot be reached (`aiFailure`).
 * - Stop: `cancelled()` is checked before every page action; the panel also
 *   sends `fill_cancel`, which cancels the page operation in flight.
 *
 * THE OUTCOME VOCABULARIES, and where each one ends
 *   page outcome   verified | partial | unexpected (+reason) | reverted | stale |
 *     (fill-ops)   unconfirmed (it shows, the page's proof did not move) |
 *                  progressed | closed | yours | blocked | unsupported |
 *                  cancelled | timeout; reason `no_effect` (+ `gestures`,
 *                  the kinds tried) when no gesture changed anything
 *                  → read by act(); never leaves this file as a status.
 *   act()          the page's outcome, or halted (Stop / run clock) | late
 *                  (field clock) | refused (yours/blocked/unsupported, or
 *                  no_effect from a second kind of gesture — already recorded
 *                  as the row's final status) | stale (no frame owns it)
 *                  → the caller turns it into a row status (notDone, settle).
 *   adapt()        verified (+reason) | landed (group_committed, search_committed) |
 *                  unconfirmed | gave_up | no_answer | exhausted | late |
 *                  stale | final | halted
 *                  → settle() (one value) or commitSet (one item).
 *   row status     new | open | retry while working; the final ones below.
 *                  `lastOutcome` keeps the word that decided it.
 *   report status  verified | closest | assumed | already | blocked | yours |
 *                  partial | unconfirmed (a value that shows but was never
 *                  confirmed; or one that reverted and was not re-committed
 *                  in time, `timeout`, or reverted again, `unstable`) |
 *                  needs_answer |
 *                  cannot_operate | unsupported (the widget ignored every
 *                  synthetic input) — what the panel shows.
 *   telemetry      the report status as the contract's outcome (verified,
 *                  closest_filled, assumed_filled, partial, prefilled, blocked,
 *                  user_edited, unconfirmed, needs_answer, cannot_operate,
 *                  unsupported; filled_unverified for a needs_answer row a value
 *                  landed on without being chosen as the answer: a group that
 *                  committed, a search that picked while exploring) —
 *                  buildLoopObservations, value-free.
 *
 * THE RUN TRACE (`report.trace`, app/schemas/autofill_trace.py) records each
 * field's decision path: the model calls it made (map, polarity, pick, step;
 * the prose /choose call is not recorded, and a call that failed or timed out
 * is a bare {op, ms}) and the page actions it sent, each with its ms and, for
 * an action, its effect (effectOf, exploreEffect: the vocabularies above,
 * folded to eight words). It is built from an ALLOWLIST (buildRunTrace names
 * every source). THE RULE (SYSTEM.md inv-autofill-telemetry-no-values): the
 * trace records which page option was chosen (an index into the options
 * offered) and the page's own option texts (the inventory's passive lists
 * only, never an explore's rows, which echo what a search typed); it never
 * holds a typed or profile string in a free-text slot. Labels and sections
 * are blanked RUN-WIDE when they hold any row's answer, value, write,
 * leftover or committed value (`committed` is a deny key only, never
 * emitted); `ignored`, `help` and every explore result are never read.
 * Recording is additive: it changes no status, request or page action.
 *
 * WHAT THIS FILE PUBLISHES: ns.fillLoop = { runFill, sourceHintOf, limits,
 * buildLoopObservations, buildRunTrace, effectOf, exploreEffect, sectionLines }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // Mutable so a test can shrink a clock or a cap; the loop never changes them,
  // and one run reads one copy.
  const limits = {
    MAX_ROUNDS: 4,
    MAX_ATTEMPTS: 3,
    MAX_STEPS: 8,
    MAX_ITEMS: 10,
    API_MS: 10000,
    FIELD_MS: 25000,
    ITEM_MS: 6000, // a set's clock grows by this per item worked, past the first
    RUN_MS: 180000,
    QUIET_MS: 600, // waited before the final sweep, so a late reversion can show
  };
  // The backend's limits (app/schemas/autofill_fill.py).
  const CHUNK = 40;
  const MAP_OPTIONS = 30;
  const PICK_OPTIONS = 250;
  const STEP_CANDIDATES = 60;
  const MAX_SECTIONS = 20;
  const MAX_ENTRIES = 50;
  const SECTION_KINDS = new Set(["experience", "education", "languages", "websites", "certifications"]);
  // Mirrors of app/schemas/autofill_fill.py's EntryKind and MAX_ENTRY_INDEX
  // (pinned by test_the_loops_entry_limits_mirror_the_backends): the kinds
  // whose entries are placed by profile entry (a Websites entry k is the
  // profile's k-th URL: website, then GitHub), and the highest entry index.
  const PLACED_KINDS = new Set(["experience", "education", "languages", "websites"]);
  const MAX_ENTRY_INDEX = 20;
  const entryIndex = (n) => Math.min(Math.max(Number(n) || 0, 0), MAX_ENTRY_INDEX);
  const MAX_HELD = 10;
  const HELD_CHARS = 200;
  // A MIRROR of content/field-reader.js's `ns.repeatOf` (the loop runs in the
  // panel, where field-reader.js never loads): "Work Experience 2" →
  // { base: "Work Experience", n: 2 }; "Step 2", "Page 3", "… of 4" → null.
  // The two patterns are pinned identical to the reader's by
  // test_the_loop_reads_repeated_titles_by_the_field_readers_rule.
  const REPEAT = /(\p{L}+)\s+(\d+)$/u;
  const NOT_REPEAT = /^(of|step|page)$/i;
  const repeatOf = (title) => {
    const t = String(title ?? "").replace(/\s+/g, " ").trim();
    const m = REPEAT.exec(t);
    if (!m || NOT_REPEAT.test(m[1])) return null;
    return { base: t.slice(0, m.index + m[1].length).trim(), n: Number(m[2]) };
  };
  const HISTORY_KEPT = 8;
  const FID = /^[A-Za-z0-9_-]{1,64}$/;
  const HISTORY_ENTRY = /^(click:o\d+|search:value|search:word:\d|open|scroll|close|give_up|choose) -> [a-z_]+( \([a-z_]+\))?$/;
  const FINAL = new Set(["verified", "closest", "assumed", "already", "blocked", "yours", "partial", "unconfirmed",
    "needs_answer", "cannot_operate", "unsupported"]);
  // What the engine itself committed and confirmed: the only rows a sweep may
  // reopen. `unconfirmed` and `unsupported` are final, never filled.
  const DONE = new Set(["verified", "closest", "assumed", "partial"]);
  // The only reasons that make an answer; anything else a backend says is an abstain.
  const STATUS = { matched: "verified", closest: "closest", assumed: "assumed" };
  const STEP_REASONS = new Set([...Object.keys(STATUS), "progress"]);
  const REFUSED = { yours: "yours", blocked: "blocked", unsupported: "cannot_operate" };
  const CAN_ADAPT = new Set(["popup", "search"]);
  const NO_EFFECT_KINDS = 2; // different kinds of gesture that changed nothing: the widget ignores the engine

  const sourceHintOf = (url) => {
    try {
      const q = new URL(url).searchParams;
      const raw = q.get("source") ?? q.get("utm_source") ?? q.get("src");
      return raw ? raw.split(/[?&#]/)[0].toLowerCase().slice(0, 60) : null;
    } catch {
      return null;
    }
  };
  const newRunId = () => {
    try {
      if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    } catch {
      // Not a secure context: fall through.
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  };
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
  // A /step history entry: a move id, the page's outcome word and its reason
  // word — never page text. Anything that would not pass the backend's pattern
  // loses its reason, then the entry.
  const wordOf = (s) => (typeof s === "string" && /^[a-z_]+$/.test(s) ? s : null);
  const historyEntry = (mid, outcome, reason) => {
    const base = `${mid} -> ${wordOf(outcome) ?? "no_answer"}`;
    for (const e of [wordOf(reason) ? `${base} (${reason})` : base, base]) {
      if (e.length <= 80 && HISTORY_ENTRY.test(e)) return e;
    }
    return null;
  };
  // The option text inside a candidate's description (fill-core quotes it as
  // a JSON string: `Open the group "Job Board"`) — the FIRST string: a place
  // may follow it (`Click the option "Other" (under "Job Board")`).
  const quotedText = (describe) => {
    const m = typeof describe === "string" ? /"(?:[^"\\]|\\.)*"/.exec(describe) : null;
    if (!m) return null;
    try {
      const text = JSON.parse(m[0]);
      return typeof text === "string" ? text : null;
    } catch {
      return null;
    }
  };
  // Shown beside the field in the panel, so it keeps the panel's copy rules:
  // two sentences, never an em dash joining them.
  // `how`: search_committed — the page picked a search's one hit on its own.
  const landedNote = (text, how) => {
    const who = how === "search_committed" ? "Searching picked" : "Companion clicked";
    return text ? `${who} "${text}". Check it.` : `${who} ${how === "search_committed" ? "a value" : "an option"}. Check it.`;
  };
  // A move that left a value the model did not choose as the answer: a group
  // that committed one, or a search whose Enter committed its one hit.
  const LANDS = new Set(["group_committed", "search_committed"]);
  const unstableNote = (text) => (text ? `Companion filled "${text}" twice and the page took it back both times. Check it.`
    : "Companion filled this twice and the page took it back both times. Check it.");
  const revertedNote = (text) => `Companion filled "${text}", then the page took it back. Check it.`;
  const stuckNote = (committed, how = "Searching") => {
    const text = [committed].flat().filter((v) => v != null && String(v).trim() !== "").join(", ");
    return text ? `${how} picked "${text}" and Companion couldn't take it back. Check it.`
      : `${how} picked a value and Companion couldn't take it back. Check it.`;
  };
  // The options that could be an answer: never a popup's placeholder row
  // ("Select One", which live Workday lists as an option) nor an empty or
  // dash-only one. The page drops them already; this holds for any list.
  const answerOptions = (opts) => (opts ?? []).filter((o) => o && !ns.isPlaceholderText(o.text));
  // Options a model may be shown: answers only, never a never-fill one, never under the reserved key.
  const usable = (opts) => answerOptions(opts).filter((o) => !o.policyBlocked && typeof o.text === "string"
    && typeof o.oid === "string" && o.oid.length >= 1 && o.oid.length <= 16 && o.oid !== "none");
  // Every answer the list offers is a never-fill one (a placeholder row does not count either way).
  const allBlocked = (opts) => answerOptions(opts).length > 0 && !usable(opts).length;

  // ---- a date written into ONE part of a date (iCIMS, live 2026-10-01: a
  // Year box was given "2026-06"). /map says a slot is a date (`format`
  // "date", the slot's); the field reader says a control holds one part
  // (`part`). A Year box gets "2026" of "2026-06", a Month box "06"; a Month
  // or Year LIST is chosen here by the part's own spellings, never by a model.
  // A part the fact lacks (a day; the month of a year-only fact) is no value.
  const PARTS = new Set(["year", "month", "day"]);
  const MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december"];
  const DATE_FACT = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/;
  // { part, value } for a date slot on a part control (value "": the fact
  // lacks it), else null: the value stays whole.
  const narrowed = (f, m) => {
    if (m?.route !== "slot" || m.format !== "date" || f.shape === "date" || !PARTS.has(f.part)) return null;
    const d = DATE_FACT.exec(String(m.value ?? "").trim());
    return { part: f.part, value: (d && { year: d[1], month: d[2], day: d[3] }[f.part]) || "" };
  };
  // The texts that state a part's value: month "06" is 6, 06, June or Jun.
  const spellings = (part, value) => {
    const n = Number(value);
    const name = part === "month" ? MONTH_NAMES[n - 1] ?? "" : "";
    return new Set([String(n), value, ...(name ? [name, name.slice(0, 3), ...(n === 9 ? ["sept"] : [])] : [])]);
  };
  // The ONE option stating the part ({ text, reason }), else an abstain.
  const partPick = (row, opts) => {
    const want = spellings(row.part, row.value);
    const hits = usable(opts).filter((o) => want.has(o.text.trim().toLowerCase().replace(/\.$/, "")));
    return hits.length === 1 ? { text: hits[0].text, reason: "matched" } : { abstained: true };
  };

  // ---- the run trace's pieces: pure, and value-free by what they read.
  // The recorder inside runFill notes a step per model call and per page action.
  const TRACE_STEPS = 40; // the schema's per-field cap: the first half and the last half are kept
  const TRACE_WORD = /^[a-z_]{1,40}$/;
  const TRACE_SLOT = /^[a-z_]+(\.[a-z0-9_]+)*$/;
  const MOVE_ID = /^(click:o\d+|search:value|search:word:\d|open|scroll|give_up)$/;
  const TRACE_MOVE_MAX = 40;
  const TRACE_ROUTES = new Set(["slot", "free_text", "low_stakes", "reasoned", "none", "blocked"]);
  const TRACE_REASONS = new Set(["matched", "closest", "assumed", "progress", "abstained"]);
  const TRACE_ENGINES = new Set(["jev", "fast"]);
  const TRACE_SECONDS = new Set(["asked", "decided"]);
  const TRACE_WAYS = new Set(["same", "opposite", "neither", "unsure"]);
  const unit = (x) => typeof x === "number" && x >= 0 && x <= 1;
  // What a model's trace may carry, each value checked as the schema checks it.
  const DECISION_CHECKS = {
    engine: (x) => TRACE_ENGINES.has(x), p: unit, floor: unit, second: (x) => TRACE_SECONDS.has(x), first_p: unit,
    first_same: (x) => typeof x === "boolean", chose_none: (x) => typeof x === "boolean",
  };
  // A page word is sent only when the schema's pattern holds (a lowercase
  // word cannot carry a typed value); anything else is null, never "".
  const traceWord = (s) => (typeof s === "string" && TRACE_WORD.test(s) ? s : null);
  const traceSlot = (s) => (typeof s === "string" && s.length <= 120 && TRACE_SLOT.test(s) ? s : null);
  const traceMove = (mid) => (typeof mid === "string" && mid.length <= TRACE_MOVE_MAX && MOVE_ID.test(mid) ? mid : null);
  const wholeMs = (ms) => Math.min(600000, Math.max(0, Math.round(Number(ms) || 0)));
  // The page's outcome (or act()'s own word) as the effect of an action; null
  // is no attempt at all: Stop (halted) and the page's cancel.
  const OUTCOME_EFFECT = {
    verified: "progress", partial: "progress", progressed: "progress", closed: "progress",
    unexpected: "unexpected", reverted: "reverted", unconfirmed: "unconfirmed",
    yours: "refused", blocked: "refused", unsupported: "refused", refused: "refused",
    timeout: "late", late: "late", halted: null, cancelled: null,
  };
  // REASON FIRST, with one exception. The first ignored gesture arrives as
  // outcome "unexpected" (a typed one as "reverted") with reason no_effect:
  // the wasted-action signal, whatever the outcome says. The SECOND kind
  // ignored ends the field and act() answers `refused`, which comes before
  // the reason. group_committed and search_committed are `unexpected` to the
  // page but a landed value to the loop: progress. `got`: the page's own
  // result when act() answered with a word of its own (refused, halted).
  const effectOf = (result, got) => {
    const page = got ?? result;
    if (result?.outcome === "refused") return "refused";
    if (page?.reason === "no_effect") return "no_effect";
    if (LANDS.has(page?.reason)) return "progress";
    const outcome = page?.outcome;
    return Object.hasOwn(OUTCOME_EFFECT, outcome) ? OUTCOME_EFFECT[outcome] : "error";
  };
  // An explore reports an error word, not an outcome. Those with a row of
  // their own: no_effect (the OUTRIGHT set's gesture), committed_while_exploring
  // (its other member that explore can raise), a refusal, stale, timeout and
  // cancelled. Any other error (no_popup, unsettled) opened nothing.
  const exploreEffect = (got) => {
    const error = got?.error;
    if (!error) return got?.options?.length ? "progress" : "no_effect";
    if (error === "cancelled") return null;
    if (Object.hasOwn(REFUSED, error)) return "refused";
    if (error === "committed_while_exploring") return "unexpected";
    if (error === "timeout") return "late";
    return error === "stale" ? "error" : "no_effect";
  };
  // A model's trace, copied by name and checked: engine, p, floor, second,
  // first_p, first_same, chose_none; a value that is absent or invalid is left out.
  const decisionOf = (t) => Object.fromEntries(Object.entries(DECISION_CHECKS)
    .filter(([k, ok]) => t?.[k] != null && ok(t[k])).map(([k]) => [k, t[k]]));

  async function runFill(deps, options = {}) {
    const { broadcast, api } = deps ?? {};
    for (const [name, dep] of [["broadcast", broadcast], ["api", api]]) {
      if (typeof dep !== "function") throw new TypeError(`fill-loop: missing dep ${name}`);
    }
    const cancelled = deps.cancelled ?? (() => false);
    const recipes = typeof deps.recipes?.get === "function" && typeof deps.recipes?.record === "function"
      ? deps.recipes : null;
    const L = { ...limits };
    const startedAt = new Date();
    const runDeadline = Date.now() + L.RUN_MS;
    const runId = newRunId();
    const timedOut = () => Date.now() >= runDeadline;
    const halt = () => cancelled() || timedOut();
    const tell = (update) => {
      try {
        deps.onProgress?.(update);
      } catch {
        // A progress hook never stops a fill.
      }
    };
    // `today`: the browser's date, so a date the applicant signs "today" is
    // theirs (the backend may run on UTC; it takes it within a day of its own).
    const now = new Date();
    const selector = {
      today: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`,
    };
    if (options.applicationId) selector.application_id = options.applicationId;
    else if (options.base) selector.base = String(options.base).slice(0, 200);
    const asked = { ...selector, source_hint: options.sourceHint ? String(options.sourceHint).slice(0, 60) : null };
    // fid -> { fid, field, frameId, status, attempts, route, slot, value, answer, lastOutcome,
    //   deadline, spent, started, recommits, failedMoves, ignored, wrote, wroteAs,
    //   recipeKeys, recipe, moves, contradicted, mismatch, round, steps }
    //
    // A ROW'S LIFE: new (observe) → open (work, when the loop starts on it)
    // → a final status (finish / done / unconfirmed / outOfTime), or retry
    // (fail: attempts + 1; or sweep: a verified value reverted, recommits = 1)
    // → open again next round, on the field's remaining clock. A retry left
    // at the end is reported cannot_operate — or unconfirmed when it is a
    // revert the engine never got back (tookBackUnretried). A row that is
    // re-committing and ends anywhere but a fill says the page took the value
    // back (finish → tookBack).
    const rows = new Map();
    let listed = []; // the latest inventory's fids, in page order
    // Page actions sent (a close aside) and commits an explore left: whether a field's work changed the page.
    let pageActions = 0;
    let aiFailure = null;
    let host = null;
    let round = 0; // the round the loop is in; a row's `round` is the last one that changed its status

    // ---- rows and clocks
    // Every status change stamps the round it happened in (finish, done and
    // unconfirmed all end here; so do the sweep's and tookBack's direct sets).
    const set = (fid, patch) => {
      const was = rows.get(fid)?.status;
      const row = { ...rows.get(fid), ...patch, ...(patch.status ? { round } : {}) };
      rows.set(fid, row);
      if (patch.status && patch.status !== was && FINAL.has(patch.status)) tell({ phase: "field", fid, status: patch.status });
      return row;
    };
    // A step on the field's path. Rows are copied by `set`, but `steps` is one
    // array shared by every copy, so a push is seen by all of them. Past the
    // cap the first half stays (how the field began) and the second half is a
    // ring of the latest (how it ended): a field that looped keeps both ends.
    const note = (fid, step) => {
      const steps = rows.get(fid)?.steps;
      if (!steps) return;
      if (steps.length >= TRACE_STEPS) steps.splice(TRACE_STEPS / 2, 1);
      steps.push(step);
    };
    // A model's answer on a field: its polarity when it read one, then the
    // decision. A call that failed or ran out of time (no `res`) is a bare
    // {op, ms}: slow failures show up, with nothing else to say.
    const noteAnswer = (fid, op, res, got, ms, extra) => {
      if (!res) return note(fid, { op, ms: wholeMs(ms) });
      if (!got) return undefined;
      const pol = got.polarity;
      if (TRACE_WAYS.has(pol?.way)) {
        note(fid, { op: "polarity", way: pol.way, engine: TRACE_ENGINES.has(pol.engine) ? pol.engine : null, p: unit(pol.p) ? pol.p : null });
      }
      return note(fid, { op, ms: wholeMs(ms), ...extra, ...decisionOf(got.trace) });
    };
    // Re-committing a value the engine wrote that the page took back.
    const recommitting = (row) => Boolean(row?.recommits && row.wrote && (row.status === "open" || row.status === "retry"));
    // The user must learn that the page took the value back — whatever else
    // stopped the re-commit (`why`: out of time, not committed, no answer).
    const tookBack = (f, why) => set(f.fid, {
      status: "unconfirmed", lastOutcome: why ?? "reverted", answer: revertedNote(rows.get(f.fid).wrote), wroteAs: null,
    });
    // Everything a field can end as, except a fill (and the user's own or
    // the policy's refusal), ends a re-commit as tookBack — unless the
    // re-commit itself left ANOTHER value on the page (LANDED: a search or a
    // keyboard open that picked one, a group that committed one), whose own
    // note names what the field holds now.
    const KEEPS = new Set([...DONE, "unconfirmed", "yours", "blocked", "already"]);
    const finish = (f, status, patch = {}) => (recommitting(rows.get(f.fid)) && !KEEPS.has(status)
      && !LANDED.has(patch.lastOutcome) ? tookBack(f, patch.lastOutcome) : set(f.fid, { status, ...patch }));
    const fail = (f, outcome) => set(f.fid, {
      status: "retry", attempts: (rows.get(f.fid).attempts ?? 0) + 1, lastOutcome: outcome ?? "no_answer",
    });
    // A value that landed but is not confirmed as the answer — a pick the page
    // shows over proof that did not move, one without an answer reason, or one
    // that reverted after its one re-commit (`unstable`): never filled, the
    // user's to check.
    const unconfirmed = (f, text, why = "unconfirmed") => finish(f, "unconfirmed", {
      answer: why === "unstable" ? unstableNote(text) : landedNote(text), lastOutcome: why, wrote: text ?? null, wroteAs: null,
    });
    const done = (f, reason, committed) => {
      const answer = Array.isArray(committed) ? committed.join(", ") : committed ?? null;
      if (!STATUS[reason]) return unconfirmed(f, answer); // never "verified" by default
      // Nothing, or a popup's placeholder, is never a filled answer — whatever the page said.
      if (!String(answer ?? "").trim() || ns.isPlaceholderText(answer)) return unconfirmed(f, answer || null);
      // `wroteAs`: what the engine made of it, kept so a re-render that makes
      // the field look "already answered" still reports the engine's own fill.
      return finish(f, STATUS[reason], { answer, lastOutcome: "verified", wrote: answer, wroteAs: STATUS[reason] });
    };
    // ONE budget per field, shared by everything that works on it — its pick,
    // its commit, its adaptive steps, a later round's retry and the sweep's one
    // re-commit. The clock runs only while the loop works on the field
    // (`started` … `rest`), and each start gets what the field has not already
    // spent: never a fresh FIELD_MS. So a re-commit runs on the field's
    // REMAINING time (not a fixed allowance), and a field that spent its budget
    // getting the first commit in is reported out of time, not written again.
    const work = (f, ms = L.FIELD_MS) => {
      const now = Date.now();
      return set(f.fid, { status: "open", started: now, deadline: now + Math.max(0, ms - (rows.get(f.fid)?.spent ?? 0)) });
    };
    const rest = (f) => {
      const row = rows.get(f.fid);
      if (row?.started) set(f.fid, { spent: (row.spent ?? 0) + (Date.now() - row.started), started: null });
    };
    const onFieldClock = async (f, ms, fn) => {
      const row = work(f, ms);
      try {
        return await fn(row);
      } finally {
        rest(f);
      }
    };
    const fieldLate = (f) => Date.now() >= (rows.get(f.fid)?.deadline ?? Infinity);
    // The kinds of gesture that changed nothing at all (`no_effect`, judged
    // on the page, which says which kinds it tried) since anything last did.
    // Two DIFFERENT kinds ignored — a press and the keyboard — and the widget
    // ignores synthetic input, which is all the engine has: `unsupported`.
    // The same press ignored twice is not that. Typing counts per VALUE: one
    // write (insertText and its setter fallback) is one gesture, and a box
    // that refuses a value (type=number given text, a mask) refuses it every
    // time — the same value twice never counts twice; such a box ends
    // cannot_operate after MAX_ATTEMPTS, as before. `typed`: the value or
    // query the operation typed. Returns nowUnsupported.
    const noteNoEffect = (f, reason, gestures, typed) => {
      const kinds = new Set(reason === "no_effect" ? rows.get(f.fid).ignored ?? [] : []);
      if (reason === "no_effect") {
        for (const k of gestures?.length ? gestures : ["unknown"]) kinds.add(k === "type" ? `type:${typed ?? ""}` : String(k));
      }
      set(f.fid, { ignored: [...kinds] });
      const nowUnsupported = kinds.size >= NO_EFFECT_KINDS;
      if (nowUnsupported) finish(f, "unsupported", { lastOutcome: "no_effect" });
      return nowUnsupported;
    };
    // The field's own clock ran out (a re-commit's too: finish says the page took the value back).
    const outOfTime = (f) => finish(f, "cannot_operate", { lastOutcome: "timeout" });
    // Stopped, out of run time, or out of field time: only the last is the field's own fault.
    const lateOrHalted = (f) => {
      if (!cancelled() && !timedOut() && fieldLate(f)) outOfTime(f);
    };

    // ---- the backend: every wait bounded, never past the field's or the run's clock
    const bounded = (call, deadline) => {
      const left = Math.min(deadline ?? Infinity, runDeadline) - Date.now();
      const byClock = left < L.API_MS; // the field's or the run's clock, not the call's own
      if (left <= 0) return Promise.reject(Object.assign(new Error("Out of time."), { status: 504, deadline: true }));
      let timer;
      const clock = new Promise((_, reject) => {
        timer = setTimeout(() => reject(Object.assign(new Error("The AI took too long."), {
          status: 504, deadline: byClock,
        })), Math.min(L.API_MS, left));
      });
      return Promise.race([Promise.resolve().then(call), clock]).finally(() => clearTimeout(timer));
    };
    // { res, ms }: res is null when the backend failed or ran out of time (a
    // clock running out is not an AI failure); ms is how long the call took.
    const post = async (path, body, deadline) => {
      const t0 = Date.now();
      try {
        return { res: await bounded(() => api(path, { method: "POST", body: JSON.stringify(body) }), deadline), ms: Date.now() - t0 };
      } catch (err) {
        if (!err?.deadline) aiFailure ??= err;
        return { res: null, ms: Date.now() - t0 };
      }
    };
    const question = (f) => String(f.question ?? "").slice(0, 300);
    // The routes /pick takes for a field no fact answers; any other is a slot's.
    const NO_SLOT_ROUTES = new Set(["low_stakes", "reasoned"]);
    const routeOf = (row) => (NO_SLOT_ROUTES.has(row.route) ? row.route : "slot");
    // Whether the adaptive step may take a field over: a popup or search, on a
    // route /step answers (the reasoning route is /pick's alone).
    // A date part's abstain is final: its list holds no option stating the part.
    const adapts = (f, row) => CAN_ADAPT.has(f.shape) && routeOf(row) !== "reasoned" && !row.part;
    const policyBlocks = (text) => Boolean(ns.isPolicyBlocked?.(text, { consentForms }));

    // ---- the page: one operation at a time, each awaited
    const results = (frames) => (frames ?? []).map((fr) => fr?.result).filter((r) => r !== undefined && r !== null);
    const rowsOf = (frames) => results(frames).flatMap((r) => (Array.isArray(r) ? r : []));
    const merged = (frames) => Object.assign({}, ...results(frames).filter((r) => typeof r === "object" && !Array.isArray(r)));
    // One action on one field. Outcomes beyond the page's own: halted (Stop or
    // the run's end), late (the field's clock), refused (recorded as final here).
    // `closing` (give_up) may still run out of time — it only closes a popup.
    // `overtime` (a set committing what it already picked) may run past the field's clock.
    // `seen.got`: the page's own result, for the trace when act() answers with a word of its own.
    const actUntraced = async (f, action, { closing = false, overtime = false } = {}, seen = {}) => {
      if (cancelled() || (!closing && timedOut())) return { outcome: "halted" };
      if (!closing && !overtime && fieldLate(f)) return { outcome: "late" };
      if (!closing) pageActions += 1;
      const [got] = rowsOf(await broadcast({ type: "fill_apply", actions: [{ fid: f.fid, fp: f.fp, ...action }] }))
        .filter((r) => r?.fid === f.fid);
      if (!got) return { outcome: "stale" }; // no frame owns the fid any more
      seen.got = got;
      if (got.outcome === "cancelled") return { outcome: "halted" };
      heard(f, action.op, got);
      if (REFUSED[got.outcome]) {
        finish(f, REFUSED[got.outcome], { lastOutcome: got.outcome });
        return { outcome: "refused" };
      }
      // Opening the list from the keyboard picked a value the page would not
      // give back: nothing more is tried; the user is told what it holds.
      if (got.reason === "committed_while_opening") {
        finish(f, "needs_answer", { lastOutcome: got.reason, answer: stuckNote(got.committed, "Opening the list") });
        return { outcome: "refused" };
      }
      // A close is the engine tidying up, not an attempt on the field.
      if (!closing && noteNoEffect(f, got.reason, got.gestures, action.value ?? action.term ?? action.text)) {
        return { outcome: "refused" };
      }
      return got;
    };
    // Every way out of actUntraced is one step on the field's path (Stop and a
    // closing give_up are not attempts, and note nothing).
    const act = async (f, action, opts = {}) => {
      const t0 = Date.now();
      const seen = {};
      const result = await actUntraced(f, action, opts, seen);
      const effect = opts.closing ? null : effectOf(result, seen.got);
      if (effect) {
        note(f.fid, { op: action.op, effect, word: traceWord(seen.got?.reason ?? seen.got?.outcome ?? result.outcome),
          ms: wholeMs(Date.now() - t0), ...(action.op === "move" ? { move: traceMove(action.mid) } : {}) });
      }
      return result;
    };
    // True when the action did not happen and there is nothing more to do now.
    const notDone = (f, out) => {
      if (out.outcome === "halted" || out.outcome === "refused") return true;
      if (out.outcome === "late") {
        outOfTime(f);
        return true;
      }
      return false;
    };
    const explore = async (f, term) => {
      if (halt() || fieldLate(f)) return null;
      // The field's remaining time rides along: the page's explore never runs past it.
      const left = (rows.get(f.fid)?.deadline ?? Infinity) - Date.now();
      const t0 = Date.now();
      const got = merged(await broadcast({
        type: "fill_explore", requests: [withOrder(f, {
          fid: f.fid, fp: f.fp, ...(term ? { term } : {}), ...(Number.isFinite(left) ? { ms: left } : {}),
        })],
      }))[f.fid];
      if (got) heard(f, "explore", got);
      const result = got ?? { options: [], complete: false, error: "stale" };
      // Only the option count and the error word: an explore's rows echo what a search typed.
      const effect = exploreEffect(result);
      if (effect) note(f.fid, { op: "explore", ms: wholeMs(Date.now() - t0), effect, word: traceWord(result.error) });
      return result;
    };
    // An explore that went wrong: true when it decided the field for now.
    // `term`: what the explore typed (a no_effect on typing is counted per value).
    const exploreRefused = (f, got, term) => {
      if (REFUSED[got.error]) {
        finish(f, REFUSED[got.error], { lastOutcome: got.error });
        return true;
      }
      if (got.error === "cancelled") return true;
      if (noteNoEffect(f, got.error, got.gestures, term)) return true;
      // Exploring picked a value (a one-hit search) and the page could not
      // take it back: nothing more is tried on the field; the user is told
      // what it holds now.
      if (got.error === "committed_while_exploring") {
        pageActions += 1; // it changed the page like any commit: a peek follows
        finish(f, "needs_answer", { lastOutcome: got.error, answer: stuckNote(got.committed) });
        return true;
      }
      if (got.error === "stale") {
        fail(f, "stale");
        return true;
      }
      return false;
    };

    // ---- recipes: a learned move order per widget family (see the header)
    // Looked up once per field (again only when its fingerprint changed): a
    // popup or search with the page's keys, never another shape.
    const lookUp = async (f) => {
      const row = rows.get(f.fid);
      if (row.recipeKeys !== undefined) return;
      const keys = recipes && CAN_ADAPT.has(f.shape) && f.recipe?.family && f.recipe?.site
        ? { family: String(f.recipe.family), site: String(f.recipe.site) } : null;
      let found = null;
      if (keys) {
        try {
          found = await bounded(() => recipes.get(keys), row.deadline);
        } catch {
          found = null; // a store that fails is no recipe, never a failed fill
        }
      }
      set(f.fid, { recipeKeys: keys, recipe: found?.key && found.variant ? found : null });
      // The order itself is a string of moves, not a move id: only that one was used.
      if (rows.get(f.fid).recipe) note(f.fid, { op: "recipe" });
    };
    // The field's recipe order on an explore or a commit, when it has one.
    const withOrder = (f, action) => {
      const variant = rows.get(f.fid)?.recipe?.variant;
      return variant ? { ...action, variant } : action;
    };
    // What the book may learn from a page operation: the moves a commit took
    // and whether the page kept them — verified is a candidate (the final
    // sweep decides), unconfirmed a contradiction — and a learned move the
    // control could not take (`mismatch`, from any operation). Under a recipe,
    // an operation that failed OUTRIGHT (its open committed a value, its list
    // never settled or never opened, the widget ignored it) is a contradiction
    // too, of the recipe tried only (no moves: its family is taught nothing).
    // A set whose items opened differently (`varied`) is no one move: nothing
    // to learn, and a contradiction under a recipe.
    const OUTRIGHT = new Set(["committed_while_opening", "committed_while_exploring", "unsettled", "no_popup", "no_effect"]);
    const heard = (f, op, got) => {
      const tried = Boolean(rows.get(f.fid).recipe);
      if (got.mismatch) set(f.fid, { mismatch: got.mismatch, moves: got.variant ?? null });
      // Only the operations that carry the order: an adaptive move carries none.
      const ordered = op === "explore" || op === "choose" || op === "set";
      if (tried && ordered && OUTRIGHT.has(op === "explore" ? got.error : got.reason)) set(f.fid, { contradicted: true });
      if (op !== "choose" && op !== "set") return;
      if (got.varied?.length) set(f.fid, { moves: null, ...(tried ? { contradicted: true } : {}) });
      else if (got.outcome === "verified" && got.variant) set(f.fid, { moves: got.variant });
      if (got.outcome === "unconfirmed") set(f.fid, { moves: got.variant ?? rows.get(f.fid).moves ?? null, contradicted: true });
    };
    // One field's lesson, once the final sweep has run. A mismatch or a
    // contradiction (an unconfirmed commit, a revert a sweep saw) was
    // observed, and is always recorded. Kept only when the commit's moves
    // verified, nothing ever reverted the value AND the final sweep
    // re-checked it and found it holding (`held`): a filled value that sweep
    // could not re-check is not kept — not reported reverted is not the same
    // as found holding.
    const KEPT = new Set(Object.values(STATUS));
    const lessonOf = (r) => {
      if (!r?.recipeKeys || (!r.recipe && !r.moves)) return null;
      const used = r.recipe?.key ?? null;
      const outcome = r.mismatch ? (used ? "mismatch" : null)
        : r.contradicted || r.recommits || (r.moves && r.status === "unconfirmed") ? "contradicted"
          : r.moves && KEPT.has(r.status) && held.has(r.fid) ? "kept" : null;
      return outcome && { recipe: r.recipeKeys, used, moves: r.moves ?? {}, outcome };
    };

    // ---- consent, for the page's policy
    let consentForms = false;
    if (typeof options.consentForms === "boolean") {
      consentForms = options.consentForms;
    } else {
      const query = selector.application_id ? `?application_id=${encodeURIComponent(selector.application_id)}`
        : selector.base ? `?base=${encodeURIComponent(selector.base)}` : "";
      try {
        consentForms = (await bounded(() => api(`/api/autofill/context${query}`)))?.eeo_consent?.consent_forms === true;
      } catch {
        consentForms = false;
      }
    }

    // ---- picking: { text, reason } | { abstained: true } | null (no answer)
    const pickAsk = (f, row, opts, complete, item) => {
      const offered = usable(opts);
      return {
        offered,
        field: {
          fid: f.fid, question: question(f), route: routeOf(row), slot: row.slot ?? null,
          ...(item !== undefined ? { item: String(item).slice(0, 300) } : {}),
          options: offered.slice(0, PICK_OPTIONS).map(({ oid, text }) => ({ oid, text: text.slice(0, 300) })),
          // Complete only when the model sees EVERY answer: none hidden by policy, none past the cap.
          complete: Boolean(complete) && offered.length === answerOptions(opts).length && offered.length <= PICK_OPTIONS,
        },
      };
    };
    // `where`: the picked option's category path, when explore read one — the
    // choose commits the option under it, never the same text elsewhere.
    const pickOf = (got, offered) => {
      if (!got) return null;
      const o = got.oids?.length && STATUS[got.reason] ? offered.find((x) => x.oid === got.oids[0]) : undefined;
      if (!o?.text) return { abstained: true };
      return { text: o.text, reason: got.reason, ...(typeof o.where === "string" ? { where: o.where } : {}) };
    };
    // The option /pick chose, as its 0-based place among those it was OFFERED
    // (never the page's own list, which may be longer), or null.
    const notePick = (f, res, offered, ms) => {
      const got = res?.picks?.[f.fid];
      const at = got?.oids?.length ? offered.slice(0, PICK_OPTIONS).findIndex((o) => o.oid === got.oids[0]) : -1;
      noteAnswer(f.fid, "pick", res, got, ms, {
        reason: TRACE_REASONS.has(got?.reason) ? got.reason : null, option: at >= 0 ? at : null,
      });
    };
    const pick = async (f, row, opts, complete, item) => {
      if (row.part) return partPick(row, opts);
      const { offered, field } = pickAsk(f, row, opts, complete, item);
      if (!offered.length || halt() || fieldLate(f)) return null;
      const { res, ms } = await post("/api/autofill/pick", { ...asked, fields: [field] }, rows.get(f.fid).deadline);
      notePick(f, res, offered, ms);
      return pickOf(res?.picks?.[f.fid], offered);
    };
    // The one item of a one-item list fact on a one-answer field (the slot is a
    // set, so /pick and /step need the item).
    // A text field takes a string fact, or the one item of a one-item list.
    const textOf = (f, row) => (typeof row.value === "string" ? row.value : itemOf(f, row)) || null;
    const itemOf = (f, row) => (Array.isArray(row.value) && !f.multi && row.value.length === 1 ? String(row.value[0]) : undefined);
    // Fields whose whole option list the inventory already read (native
    // select, radio, checkbox): no explore, so they are picked together, 40 a call.
    const pickedTogether = (f, row) => Boolean(f.options?.length && f.optionsComplete && usable(f.options).length)
      && (NO_SLOT_ROUTES.has(row.route) || (typeof row.value === "string" && row.value) || itemOf(f, row) !== undefined);
    const pickBatch = async (fields) => {
      const out = new Map();
      for (const f of fields) if (rows.get(f.fid).part) out.set(f.fid, partPick(rows.get(f.fid), f.options));
      const asks = fields.filter((f) => !rows.get(f.fid).part).map((f) => {
        const row = rows.get(f.fid);
        return [f, pickAsk(f, row, f.options, f.optionsComplete, itemOf(f, row))];
      });
      for (let i = 0; i < asks.length; i += CHUNK) {
        if (halt()) break;
        const part = asks.slice(i, i + CHUNK);
        const { res, ms } = await post("/api/autofill/pick", { ...asked, fields: part.map(([, a]) => a.field) });
        for (const [f, a] of part) {
          // One call served the chunk: each field is charged its even share.
          notePick(f, res, a.offered, ms / part.length);
          out.set(f.fid, pickOf(res?.picks?.[f.fid], a.offered));
        }
      }
      return out;
    };

    // ---- the adaptive step. Returns { outcome } — verified (+reason,
    // committed) | landed (+text) | gave_up | no_answer | exhausted | late |
    // stale (+why) | final (a refusal, recorded) | halted.
    const giveUp = async (f, outcome) => {
      if (!cancelled()) await act(f, { op: "move", mid: "give_up" }, { closing: true });
      return { outcome };
    };
    // Stopped: the panel's fill_cancel closes what the engine held. The run's
    // clock ran out: nobody else will, so give_up closes it.
    const halted = (f) => (cancelled() ? { outcome: "halted" } : giveUp(f, "halted"));
    // What a move acts on: the value it is for (a set's item — "search:value"
    // for one item is not the same move for the next), and what the state
    // SHOWS — its value, whether its popup is open, its options (a lazy list
    // that grew can scroll again), the moves on offer — never its version,
    // which the page mints afresh on every read. A move that failed from a
    // state that looks the same, for the same value, fails the same way.
    const stateKey = (state, value) => JSON.stringify([value ?? null, state.committed ?? null, Boolean(state.popupOpen),
      (state.options ?? []).length, (state.options ?? []).map((o) => o?.text),
      (state.candidates ?? []).map((c) => [c?.mid, c?.describe])]);
    const FAILED = new Set(["unexpected", "reverted"]);
    const MAX_REFUSALS = 2;
    const adapt = async (f, row, first, item) => {
      const value = item ?? (typeof row.value === "string" ? row.value : undefined);
      const history = first ? [first] : [];
      // A state + move pair that failed, for this field and this run: never
      // sent to the page again. The row keeps it across rounds and items.
      const failedMoves = rows.get(f.fid).failedMoves ?? new Set();
      set(f.fid, { failedMoves });
      let state = null; // kept (not re-read) when a proposed move was refused here: the page's state is untouched
      let refusals = 0; // proposals refused in a row as already failed
      for (let i = 0; i < L.MAX_STEPS; i += 1) {
        if (halt()) return halted(f);
        if (fieldLate(f)) return giveUp(f, "late");
        if (!state) {
          [state] = results(await broadcast({
            type: "fill_step_state", fid: f.fid, fp: f.fp, ...(value !== undefined ? { value } : {}),
          }));
        }
        if (!state) return { outcome: "stale", why: "stale" };
        if (state.error || !Array.isArray(state.candidates)) {
          if (REFUSED[state.error]) {
            finish(f, REFUSED[state.error], { lastOutcome: state.error });
            return { outcome: "final" };
          }
          if (state.error === "cancelled") return { outcome: "halted" };
          // The field changed under us (or the page could not read it): back to the inventory.
          return { outcome: "stale", why: wordOf(state.error) ?? "stale" };
        }
        // Nothing but give_up on offer: no model is asked.
        if (!state.candidates.some((c) => c?.mid && c.mid !== "give_up")) return giveUp(f, "gave_up");
        const { res, ms } = await post("/api/autofill/step", {
          ...asked, fid: f.fid, question: question(f), route: routeOf(row), slot: row.slot ?? null,
          ...(item !== undefined ? { item: String(item).slice(0, 300) } : {}),
          history: history.slice(-HISTORY_KEPT),
          candidates: state.candidates.slice(0, STEP_CANDIDATES),
          complete: Boolean(state.complete),
        }, rows.get(f.fid).deadline);
        const chosen = res?.mid && res.mid !== "give_up" && STEP_REASONS.has(res.reason)
          ? state.candidates.find((c) => c.mid === res.mid) : null;
        // The model's own word: a give_up it chose is as visible as a click.
        noteAnswer(f.fid, "step", res, res, ms, {
          move: traceMove(res?.mid), reason: TRACE_REASONS.has(res?.reason) ? res.reason : null,
        });
        if (halt()) return halted(f);
        if (fieldLate(f)) return giveUp(f, "late");
        if (!chosen) return giveUp(f, res ? "gave_up" : "no_answer");
        const tried = `${stateKey(state, value)}:${chosen.mid}`;
        if (failedMoves.has(tried)) {
          // Proposed again on the same state: not executed. The model hears so,
          // and chooses again from the same state — twice in a row, and the
          // step has nothing new to offer: it gives up.
          if ((refusals += 1) >= MAX_REFUSALS) return giveUp(f, "gave_up");
          const refused = historyEntry(chosen.mid, "already_failed");
          if (refused) history.push(refused);
          continue;
        }
        refusals = 0;
        const asProgress = res.reason === "progress" && chosen.mid.startsWith("click:");
        const out = await act(f, {
          op: "move", mid: chosen.mid, version: state.version, ...(asProgress ? { as: "progress" } : {}),
        });
        state = null; // a move consumes the state it was chosen from
        if (out.outcome === "halted") return halted(f);
        if (out.outcome === "refused") return { outcome: "final" };
        if (out.outcome === "late") return giveUp(f, "late");
        if (FAILED.has(out.outcome) && !LANDS.has(out.reason)) failedMoves.add(tried);
        const entry = historyEntry(chosen.mid, out.outcome, out.reason);
        if (entry) history.push(entry);
        if (out.outcome === "verified") return { outcome: "verified", reason: res.reason, committed: out.committed };
        if (out.outcome === "unconfirmed") {
          return { outcome: "unconfirmed", text: quotedText(chosen.describe) ?? ([out.committed].flat().filter(Boolean).join(", ") || null) };
        }
        if (out.outcome === "unexpected" && LANDS.has(out.reason)) {
          // A search's describe quotes the term typed, not the value it left.
          const left = [out.committed].flat().filter(Boolean).join(", ") || null;
          return { outcome: "landed", how: out.reason, text: out.reason === "search_committed" ? left : quotedText(chosen.describe) ?? left };
        }
        // progressed, stale, not_a_group, anything else: a fresh state, and step again.
      }
      return giveUp(f, "exhausted");
    };
    // An adaptive run's end, for a single-value field.
    const settle = (f, r) => {
      if (FINAL.has(rows.get(f.fid).status)) return; // refused while stepping
      if (r.outcome === "verified") done(f, r.reason, r.committed);
      else if (r.outcome === "unconfirmed") unconfirmed(f, r.text);
      else if (r.outcome === "landed") {
        finish(f, "needs_answer", { answer: landedNote(r.text, r.how), lastOutcome: r.how ?? "group_committed", wrote: r.text });
      }
      else if (r.outcome === "gave_up") finish(f, "needs_answer", { lastOutcome: "abstained" });
      else if (r.outcome === "no_answer") finish(f, "needs_answer", { lastOutcome: "no_answer" });
      else if (r.outcome === "exhausted") finish(f, "cannot_operate", { lastOutcome: "step_budget" });
      else if (r.outcome === "late") outOfTime(f);
      else if (r.outcome === "stale") fail(f, r.why);
    };

    // Whether a choose opens the view explore read, so an explored option's
    // category path (`where`) still names it there. A search box's choose
    // types `term ?? the picked text`: only a search explored with that same
    // term shows the same rows (its default list may group options under
    // headers its search results do not have). Any other shape opens its
    // list unfiltered, as explore did.
    const sameView = (f, term) => f.shape !== "search" || term !== undefined;

    // ---- one value
    const commitOne = async (f, row, opts, complete, term, item, prepicked) => {
      const picked = prepicked !== undefined ? prepicked : await pick(f, row, opts, complete, item);
      if (!picked) {
        if (halt() || fieldLate(f)) return lateOrHalted(f);
        return finish(f, "needs_answer", { lastOutcome: "no_answer" });
      }
      if (picked.abstained) {
        // An honest "no option states it" over a popup is where categories,
        // search boxes and "Not in list" live. A native list showed everything.
        if (adapts(f, row)) return settle(f, await adapt(f, row, historyEntry("choose", "abstained"), item));
        return finish(f, "needs_answer", { lastOutcome: "abstained" });
      }
      const out = await act(f, withOrder(f, {
        op: "choose", text: picked.text, ...(picked.where !== undefined && sameView(f, term) ? { where: picked.where } : {}),
        ...(f.shape === "search" ? { term: term ?? picked.text } : {}),
      }));
      if (notDone(f, out)) return undefined;
      if (out.outcome === "verified") return done(f, picked.reason, out.committed);
      if (out.outcome === "unconfirmed") return unconfirmed(f, picked.text);
      if (out.outcome === "unexpected" && adapts(f, row)) {
        return settle(f, await adapt(f, row, historyEntry("choose", "unexpected", out.reason), item));
      }
      return fail(f, out.reason ?? out.outcome);
    };

    // ---- a set: every source item picked on its own, coverage counted per item
    // `learnt`: the explore fillChoice already ran for the first item.
    const commitSet = async (f, row, opts, complete, noOptions, learnt) => {
      const all = [...new Set(row.value.map(String))];
      const worked = all.slice(0, L.MAX_ITEMS);
      const byPolicy = new Set(worked.filter(policyBlocks));
      const todo = worked.filter((item) => !byPolicy.has(item));
      const pairs = []; // [option text, source item, reason, its path when explore read one]
      const missed = new Map(); // source item -> the history entry the adaptive step starts from
      const late = []; // source items the field's clock ran out on
      if (noOptions) {
        for (const item of todo) missed.set(item, noOptions);
      } else {
        // One item at a time, so a Stop or the field's clock holds between
        // items. A native (or popup) list is picked per source item over the
        // full list, so every chosen option maps back to the item it stands for.
        for (const [i, item] of todo.entries()) {
          if (halt()) return undefined;
          if (fieldLate(f)) {
            late.push(...todo.slice(i));
            break;
          }
          let shown = opts;
          let whole = complete;
          if (f.shape === "search") {
            const got = learnt?.item === item ? learnt.got : await explore(f, item);
            if (!got) {
              if (halt()) return undefined;
              late.push(...todo.slice(i));
              break;
            }
            if (exploreRefused(f, got, item)) return undefined;
            // Radio rows: the widget takes ONE answer after all (nothing is committed yet).
            if (got.multi === false) {
              if (holdsOne(f, row, got)) return keepHeld(f, row);
              if (all.length > 1) return finish(f, "needs_answer", { lastOutcome: "set_for_one" });
              return commitOne(f, row, got.options ?? [], false, item, item);
            }
            if (allBlocked(got.options)) {
              byPolicy.add(item); // every option shown for it is a never-fill one
              continue;
            }
            if (!got.options?.length) {
              missed.set(item, historyEntry("search:value", "unexpected", got.error ?? "no_results"));
              continue;
            }
            shown = got.options;
            whole = false;
          }
          const p = await pick(f, row, shown, whole, item);
          if (!p && fieldLate(f)) {
            late.push(...todo.slice(i));
            break;
          }
          if (p?.text) pairs.push([p.text, item, p.reason, p.where]);
          else if (p?.abstained) missed.set(item, historyEntry("choose", "abstained"));
        }
      }
      if (halt()) return undefined;
      const covered = new Map(); // source item -> reason
      const landed = [];
      let landedHow = "group_committed"; // how the last landed value got there
      let committed = null;
      if (pairs.length) {
        const texts = [...new Set(pairs.map(([t]) => t))];
        const action = { op: "set", texts };
        // A search set types the item that found each option.
        if (f.shape === "search") action.terms = texts.map((t) => pairs.find(([x]) => x === t)[1]);
        // Each item's path, where explore read one (null: the text alone). A
        // set types the item it explored with, so the view is the one explore read.
        const wheres = texts.map((t) => pairs.find(([x]) => x === t)[3] ?? null);
        if (wheres.some((w) => typeof w === "string")) action.wheres = wheres;
        // What was picked is committed even when the clock ran out picking the rest.
        const out = await act(f, withOrder(f, action), { overtime: true });
        if (notDone(f, out)) return undefined;
        if (out.outcome !== "verified" && out.outcome !== "partial") return fail(f, out.reason ?? out.outcome);
        committed = out.committed ?? null;
        const missing = new Set(out.missing ?? []);
        const blocked = new Set(out.blocked ?? []);
        for (const [t, item, reason] of pairs) {
          if (blocked.has(t)) byPolicy.add(item);
          else if (missing.has(t)) missed.set(item, historyEntry("choose", "missing"));
          else covered.set(item, reason);
        }
      }
      // What the generic path missed, on a popup widget: the adaptive step, one item at a time.
      if (CAN_ADAPT.has(f.shape) && routeOf(row) === "slot") {
        const queue = [...missed].filter(([item]) => !late.includes(item));
        for (const [i, [item, first]] of queue.entries()) {
          if (halt()) return undefined;
          if (fieldLate(f)) {
            late.push(...queue.slice(i).map(([x]) => x));
            break;
          }
          const r = await adapt(f, row, first, item);
          if (FINAL.has(rows.get(f.fid).status) || r.outcome === "halted") return undefined;
          if (r.outcome === "verified" && STATUS[r.reason]) {
            covered.set(item, r.reason);
            committed = r.committed ?? committed;
          } else if (r.outcome === "verified" || r.outcome === "landed" || r.outcome === "unconfirmed") {
            landed.push(landedNote(r.text ?? ([r.committed].flat().filter(Boolean).join(", ") || null), r.how));
            landedHow = r.how ?? landedHow;
          } else if (r.outcome === "late") {
            late.push(...queue.slice(i).map(([x]) => x));
            break;
          } else if (r.outcome === "stale") {
            break;
          }
        }
      }
      if (cancelled() || timedOut()) return undefined;
      const n = all.length;
      const notes = [
        ...(byPolicy.size ? [`${byPolicy.size} left to you by policy`] : []),
        ...(late.length ? [`${late.length} ran out of time`] : []),
        ...new Set(landed),
      ];
      if (covered.size === n) return done(f, [...covered.values()].includes("closest") ? "closest" : "matched", committed);
      const lastOutcome = late.length ? "timeout" : landed.length ? landedHow : "missing";
      if (!covered.size) {
        if (byPolicy.size === n) return finish(f, "blocked", { lastOutcome: "blocked" });
        return finish(f, late.length ? "cannot_operate" : "needs_answer", {
          answer: notes.length ? notes.join(" · ") : null, lastOutcome,
        });
      }
      return finish(f, "partial", {
        answer: [`${covered.size} of ${n} added`, ...notes].join(" · "), lastOutcome: late.length ? "timeout" : "partial",
        wrote: [committed].flat().filter(Boolean).join(", ") || null,
      });
    };

    // A search box whose rows turned out to be radios (ONE answer) and that
    // already holds a value — the user's, or a parsed resume's — is left as
    // it stands, like any answered field: never overwritten. A value the
    // engine wrote for an earlier question (a leftover) is not an answer.
    const holdsOne = (f, row, got) => f.shape === "search" && got?.multi === false && !row.leftover && !f.invalid
      && [f.committed].flat().some((v) => v != null && String(v).trim() !== "");
    // What it holds is kept as it stands. If the ENGINE put it there (a
    // re-render forgot the rows that made the field "answered", so it was
    // explored again), it stays what the engine made of it — never `already`,
    // which is somebody else's answer.
    const keepHeld = (f, row) => (row.wroteAs && same(f.committed, row.wrote)
      ? finish(f, row.wroteAs, { lastOutcome: "verified" }) : finish(f, "already"));

    // ---- a choice field: explore when the list is not already whole, then pick and commit
    const fillChoice = async (f, row, prepicked) => {
      const { value } = row;
      if (row.route === "slot" && (value == null || value === "" || (Array.isArray(value) && !value.length))) {
        return finish(f, "needs_answer", { lastOutcome: "no_value" });
      }
      await lookUp(f);
      // A search widget says one answer or several only in the rows of an open
      // list (radios or checkboxes): a fact of several items on one whose
      // multiplicity is not known yet (`multi` null) explores its first item
      // before deciding. One known to take a single answer is not explored.
      let multi = Boolean(f.multi);
      let learnt = null;
      if (f.shape === "search" && f.multi == null && Array.isArray(value) && value.length > 1) {
        const first = String(value[0]);
        const got = await explore(f, first);
        if (!got) return lateOrHalted(f);
        if (exploreRefused(f, got, first)) return undefined;
        if (holdsOne(f, row, got)) return keepHeld(f, row);
        if (got.multi === true) {
          multi = true;
          learnt = { item: first, got };
        }
      }
      const isSet = Array.isArray(value) && multi;
      const item = itemOf(f, row);
      // A set fact on a one-answer field: no single item is THE answer — unless it holds just one.
      if (Array.isArray(value) && !isSet && item === undefined) return finish(f, "needs_answer", { lastOutcome: "set_for_one" });
      let opts = f.options ?? [];
      let complete = Boolean(f.optionsComplete);
      let term;
      let noOptions = null;
      if (!(isSet && f.shape === "search") && !(opts.length && complete)) {
        term = f.shape === "search" ? item ?? (typeof value === "string" ? value : undefined) : undefined;
        const got = await explore(f, term);
        if (!got) return lateOrHalted(f);
        if (exploreRefused(f, got, term)) return undefined;
        if (holdsOne(f, row, got)) return keepHeld(f, row);
        if (got.options?.length) {
          opts = got.options;
          complete = Boolean(got.complete);
        } else if (!opts.length) {
          noOptions = historyEntry(term ? "search:value" : "open", "unexpected", got.error ?? "empty_popup");
        }
      }
      if (allBlocked(opts)) return finish(f, "blocked", { lastOutcome: "blocked" });
      if (isSet) return commitSet(f, row, opts, complete, noOptions, learnt);
      if (noOptions && routeOf(row) === "reasoned") return finish(f, "needs_answer", { lastOutcome: "no_options" });
      if (noOptions) return settle(f, await adapt(f, row, noOptions, item));
      return commitOne(f, row, opts, complete, term, item, prepicked);
    };

    // The format a written value is compared in, decided by the FACT's slot,
    // never by what the value looks like: a page re-punctuates a phone number
    // and a salary ("$80,000" for 80000). /map says it (`format`, from the
    // slot, server-side — autofill_map.format_of is the one reading); the
    // loop takes only a format it knows, and never guesses one.
    const FORMATS = new Set(["phone", "money"]);
    // Why /map left a field the profile could answer (`why`, a known word
    // only), said in the report: never "no fact" when the profile has one.
    const WHY = { unclear_job: "Left for you: it isn't clear which of your jobs this entry is." };
    const fillText = async (f, value, format) => {
      // An empty write is no answer: refused here, never sent (and never retried).
      if (!String(value ?? "").trim()) return finish(f, "needs_answer", { lastOutcome: "no_value" });
      const out = await act(f, { op: "write", value, ...(format ? { format } : {}) });
      if (notDone(f, out)) return undefined;
      if (out.outcome === "verified") return done(f, "matched", out.committed);
      if (out.outcome === "unconfirmed") return unconfirmed(f, value);
      return fail(f, out.reason ?? out.outcome);
    };

    const answerProse = async (fields) => {
      const got = await ns.requestChoose(
        fields.map((f) => ({ qid: f.fid, label: question(f), kind: "textarea", options: [] })),
        {
          postChoose: (body) => bounded(() => api("/api/autofill/choose", { method: "POST", body: JSON.stringify(body) })),
          applicationId: selector.application_id,
        });
      if (got?.failure && !got.failure.deadline) aiFailure ??= got.failure;
      return got?.choices ?? {};
    };

    // ---- observe, map, sweep
    const observe = (frames) => {
      const now = (frames ?? []).flatMap((fr) => (fr?.result?.fields ?? []).map((f) => [fr.frameId, f]));
      const seen = new Set(now.map(([, f]) => f.fid));
      host ??= (frames.find((fr) => fr?.result?.fields?.length) ?? frames.find((fr) => fr?.result?.host))?.result?.host ?? null;
      listed = [];
      const open = [];
      for (const [frameId, f] of now) {
        const had = rows.get(f.fid);
        if (had?.field && had.field.fp !== f.fp) {
          // The same element now asks something else (relabelled, re-purposed):
          // nothing decided about the old question carries over. If it still
          // holds what the engine wrote for the old question, that is not an
          // answer to the new one: it is mapped again, and if nothing answers
          // it the leftover is named for the user to check.
          // Its steps start over with it: they were the old question's path.
          const mine = had.wrote && same(f.committed, had.wrote);
          rows.set(f.fid, { fid: f.fid, attempts: 0, status: "new", steps: [], ...(mine ? { leftover: had.wrote } : {}) });
        }
        if (!rows.has(f.fid)) {
          // A node re-inserted while the page was being listed comes back
          // under a NEW fid: it is the same field (same frame, same
          // fingerprint), so it keeps its mapping, attempts and, while it
          // still holds an answer, what the engine did to it.
          const old = [...rows.values()].find((r) => r.frameId === frameId && r.field?.fp === f.fp && !seen.has(r.fid));
          if (old) rows.delete(old.fid);
          const carried = !old ? "new"
            : DONE.has(old.status) ? (f.answered ? old.status : "retry")
              : old.status === "open" ? "retry" : old.status;
          rows.set(f.fid, { ...(old ?? { attempts: 0, steps: [] }), fid: f.fid, status: carried });
        }
        const row = set(f.fid, { field: f, frameId });
        listed.push(f.fid);
        if (f.policyBlocked) finish(f, "blocked", { lastOutcome: "blocked" });
        else if (f.touched) finish(f, "yours", { lastOutcome: "yours" });
        else if (f.kind === "unknown" || f.shape === "unknown" || !FID.test(f.fid)) {
          finish(f, "cannot_operate", { lastOutcome: "unsupported" });
        } else if (row.status === "new" && f.answered && !f.invalid && !row.leftover) finish(f, "already");
        else if (FINAL.has(row.status) && !(row.status === "verified" && f.invalid)) continue;
        else if ((row.attempts ?? 0) >= L.MAX_ATTEMPTS) finish(f, "cannot_operate");
        else open.push(f);
      }
      return open;
    };

    // The profile entry /sections placed a field's entry at (`order`, by what
    // the page's entries hold), with the section's kind: { profile_entry,
    // entry_kind } — profile_entry a number, or null (an entry the backend placed
    // nowhere, one past the order, every entry of a section whose order could
    // not be read or that is not the first of its kind) — for a field in a
    // section the page listed and the backend placed; else nothing, and /map
    // places by page order.
    const placement = (f) => {
      const frameId = rows.get(f.fid)?.frameId;
      const mine = entryOf(frameId, f.section);
      const placed = mine ? placements.get(keyOf(frameId, mine.family)) : undefined;
      if (!placed) return {};
      if (!placed.kind) return { profile_entry: null };
      const at = entryIndex(f.repeatIndex);
      return { profile_entry: placed.order && at < placed.order.length ? placed.order[at] : null, entry_kind: placed.kind };
    };
    const mapFields = async (open) => {
      const unmapped = open.filter((f) => !rows.get(f.fid).route);
      for (let i = 0; i < unmapped.length; i += CHUNK) {
        if (halt()) return;
        const part = unmapped.slice(i, i + CHUNK);
        const { res, ms } = await post("/api/autofill/map", {
          ...selector,
          fields: part.map((f) => ({
            fid: f.fid, question: question(f), section: f.section ? String(f.section).slice(0, 200) : null,
            repeat_index: entryIndex(f.repeatIndex), ...placement(f), shape: f.shape,
            multi: Boolean(f.multi), required: Boolean(f.required),
            options: usable(f.options).slice(0, MAP_OPTIONS).map((o) => o.text.slice(0, 300)),
          })),
        });
        for (const f of part) {
          const m = res?.fields?.[f.fid];
          const format = FORMATS.has(m?.format) ? m.format : undefined;
          const datePart = narrowed(f, m);
          if (m) {
            set(f.fid, { route: m.route, slot: m.slot ?? null, value: datePart ? datePart.value : m.value ?? null,
              format, part: datePart?.part ?? null, why: WHY[m.why] ? m.why : null });
            // The slot is a fact NAME, never its value; one call served the chunk.
            note(f.fid, {
              op: "map", ms: wholeMs(ms / part.length), route: TRACE_ROUTES.has(m.route) ? m.route : null,
              slot: traceSlot(m.slot), why: WHY[m.why] ? m.why : null, ...decisionOf(m.trace),
            });
          } else if (!res) {
            note(f.fid, { op: "map", ms: wholeMs(ms / part.length) }); // the call failed or timed out
          }
        }
      }
    };

    // A value the engine verified that no longer holds gets ONE re-commit per
    // run (on the field's remaining time: `work`); reverting again, it is
    // reported unstable — `unconfirmed`, never filled. The sweep's word about
    // any other field (the user's, a prefilled one) is not ours to act on.
    // `held`: the fids THIS sweep re-checked and found holding (the page's
    // `held` rows); `sweptFrames`: whether any frame answered it at all.
    let held = new Set();
    let sweptFrames = false;
    const sweep = async () => {
      held = new Set();
      sweptFrames = false;
      if (cancelled()) return 0;
      let reverted = 0;
      const frames = await broadcast({ type: "fill_sweep" });
      sweptFrames = results(frames).length > 0;
      for (const r of rowsOf(frames)) {
        if (r?.held === true && r.outcome === "verified") held.add(r.fid);
        const row = rows.get(r?.fid);
        if (!row || !DONE.has(row.status) || r.outcome === "verified" || r.outcome === "cancelled") continue;
        if (REFUSED[r.outcome]) {
          set(r.fid, { status: REFUSED[r.outcome], lastOutcome: r.outcome });
          continue;
        }
        note(r.fid, { op: "sweep", effect: "reverted", word: traceWord(r.outcome) }); // a revert caught, re-committed or not
        if ((row.recommits ?? 0) >= 1) {
          unconfirmed({ fid: r.fid }, row.wrote, "unstable");
          continue;
        }
        set(r.fid, { status: "retry", recommits: 1, lastOutcome: r.outcome ?? "reverted" });
        reverted += 1;
      }
      return reverted;
    };
    // Before calling the page done: a quiet period, then one more sweep; done
    // only if nothing reverted. `finalSwept`: the last call's sweep reached a
    // frame (the recipe book learns nothing from a run whose end was not
    // swept), and `held` is then what that sweep re-checked.
    // `deps.beforeSweep` (optional; the panel's resume attach): run ONCE, before
    // the first final sweep's quiet period, so that sweep re-reads what an ATS
    // parsing the upload wrote over verified fields. It may answer how many ms
    // the page needs to settle (a parse lands 1-3 s after the file row), which
    // lengthens that one quiet period, within the run's clock. Its failure is
    // its own.
    let beforeSweep = typeof deps.beforeSweep === "function" ? deps.beforeSweep : null;
    let finalSwept = false;
    const settledDone = async () => {
      finalSwept = false;
      if (halt()) return true;
      let quiet = L.QUIET_MS;
      if (beforeSweep) {
        const hook = beforeSweep;
        beforeSweep = null;
        try {
          const settle = Number(await hook());
          if (settle > quiet) quiet = settle;
        } catch {
          // The attach's loss, never the fill's.
        }
        if (halt()) return true;
      }
      if (quiet > 0) await wait(Math.min(quiet, runDeadline - Date.now()));
      if (halt()) return true;
      const clean = (await sweep()) === 0;
      finalSwept = sweptFrames && !halt();
      return clean;
    };
    const same = (committed, wrote) => {
      const norm = (x) => [x].flat().filter((v) => v != null && v !== "").join(", ").replace(/\s+/g, " ").trim().toLowerCase();
      return norm(committed) !== "" && norm(committed) === norm(wrote);
    };
    const snapshot = () => JSON.stringify([...rows.values()].map((r) => [r.fid, r.status, r.attempts]));

    // ---- a round's fields, and the order they are worked in
    // What each open field is: text (a fact to type), choice, or prose (a
    // free-text answer the model writes); one with nothing to fill it is
    // finished here.
    const routed = (open) => {
      const texts = [];
      const choices = [];
      const prose = [];
      for (const f of open) {
        const row = rows.get(f.fid);
        if (row.part && !row.value) {
          finish(f, "needs_answer", { lastOutcome: "no_date_part", answer: `Your profile has no ${row.part} for this date.` });
        } else if (row.route === "none" && row.why) {
          finish(f, "needs_answer", { lastOutcome: row.why, answer: WHY[row.why] });
        } else if (!row.route || row.route === "none") finish(f, "needs_answer", { lastOutcome: row.route ? "no_fact" : "not_mapped" });
        else if (row.route === "blocked") finish(f, "blocked", { lastOutcome: "blocked" });
        else if (row.route === "free_text") {
          if (f.kind === "text") prose.push(f);
          else finish(f, "needs_answer", { lastOutcome: "no_fact" });
        } else if (f.kind === "text") {
          if (row.route === "slot" && textOf(f, row)) texts.push(f);
          else finish(f, "needs_answer", { lastOutcome: "no_value" });
        } else choices.push(f);
      }
      return { texts, choices, prose };
    };
    // A LEAD decides which of its entry's fields exist: a choice whose MAPPED
    // SLOT is an entry's `.current` ("I currently work here") removes that
    // entry's To date a frame after it is ticked (notes §4). Leads go before
    // every text and date field, so nothing is written to a field about to go.
    // By the slot the map gave, never by label text.
    const leads = (f) => f.kind === "choice" && /\.current$/.test(rows.get(f.fid)?.slot ?? "");
    // Leads, then text (dates included), then the other choices; page order within each.
    const order = (fields) => [
      ...fields.filter(leads), ...fields.filter((f) => !leads(f) && f.kind === "text"),
      ...fields.filter((f) => !leads(f) && f.kind !== "text"),
    ];
    // Whether the page's fields came or went: the frames' fid sets only (a
    // peek reads no field), against the last inventory's. Asked after a
    // CHOICE that acted on the page — a tick, a pick, a step — because those
    // are what reveal and remove fields ("I currently work here", "Other,
    // please specify"); a typed value almost never does, and a peek per text
    // field would cost a page pass per field. Nobody answering says nothing.
    const reshaped = async () => {
      const got = results(await broadcast({ type: "fill_inventory", peek: true, consentForms, runId }))
        .filter((r) => Array.isArray(r?.fids));
      if (!got.length) return false;
      const now = new Set(got.flatMap((r) => r.fids));
      return now.size !== listed.length || listed.some((fid) => !now.has(fid));
    };
    // A fresh inventory before the next field. A field that went is dropped
    // from the round — never written after it went, and not reported (the
    // report lists the page as it is); one that came is mapped (the new ones
    // only) and joins the round in order. Fields already worked this round
    // wait for the next — one re-rendered under a new fid too — and a new
    // prose field (its answers are asked once per round).
    // A field is known across a re-render by its frame and fingerprint. Two
    // fields sharing a fingerprint are told apart only by their ordinal, so
    // when one of them goes the other may take its ordinal and wait a round
    // as though worked: deferred, never lost.
    const sameField = (f) => `${rows.get(f.fid)?.frameId}\n${f.fp}`;
    const wasWorked = (worked, f) => worked.has(f.fid) || worked.has(sameField(f));
    const reobserve = async (worked, queue) => {
      const frames = await broadcast({ type: "fill_inventory", consentForms, runId });
      if (!(frames ?? []).some((fr) => fr?.result !== undefined)) return queue;
      const open = observe(frames).filter((f) => !wasWorked(worked, f));
      await mapFields(open);
      const { texts, choices } = routed(open);
      return order([...texts, ...choices]);
    };

    // ---- one fact, one entry. Within one repeating section the page listed
    // (`fill_sections`: "Websites 1", "Websites 2"), a fact is written into ONE
    // entry: /map maps each entry's fields on their own, and a fact with no
    // entry number (personal.website) can be handed to two entries' fields. The
    // first entry to claim it keeps it; another entry's field for it is left
    // for the user, never written. Nor is a TEXT field given a fact with no
    // entry number that another entry's text field already HOLDS (the user's,
    // a parsed resume's). Entry-numbered facts (experience.0 / experience.1)
    // are different facts whatever their values: two jobs may share a title.
    // A numbered title the page did not list as a section ("Question 2",
    // "Step 2") is no entry at all: the rule does not apply there.
    // A URL compares without its scheme, a leading `www.`, its host's case, a
    // default port, a trailing slash and a #fragment: "Example.dev/" holds
    // "https://www.example.dev:443/#top" (treating them as different would
    // write the duplicate).
    const URLISH = /^(?:https?:\/\/)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?::(\d+))?(\/[^\s#]*)?(?:#\S*)?$/i;
    const asUrl = (v) => [v].flat().map((x) => {
      const m = URLISH.exec(String(x ?? "").trim());
      if (!m) return x;
      const port = m[2] && m[2] !== "80" && m[2] !== "443" ? `:${m[2]}` : "";
      return `${m[1].toLowerCase()}${port}${(m[3] ?? "").replace(/\/+$/, "")}`;
    });
    // ONE key for a section, everywhere: its frame and its heading, lowercased
    // (a field's entry title "Work Experience 2" names it by its base).
    const keyOf = (frameId, heading) => `${frameId}\n${String(heading).toLowerCase()}`;
    const sectionKey = (s) => keyOf(s.frameId, s.heading);
    const listedSections = new Set(); // keyOf() of every section fill_sections returned
    const entryOf = (frameId, section) => {
      const r = repeatOf(section);
      return r && listedSections.has(keyOf(frameId, r.base)) ? { family: r.base.toLowerCase(), n: r.n } : null;
    };
    const claims = new Map(); // `${frame}\n${section}\n${slot}` -> the entry that has it
    // True (and the field finished as needs_answer) when its fact belongs to
    // another entry; otherwise the fact is claimed for this field's entry.
    const leftForAnotherEntry = (f) => {
      const row = rows.get(f.fid);
      const mine = entryOf(row?.frameId, f.section);
      if (!mine || row.route !== "slot" || !row.slot) return false;
      const key = `${row.frameId}\n${mine.family}\n${row.slot}`;
      const claimed = claims.get(key);
      const held = f.kind === "text" && !/\.\d+\./.test(row.slot) && listed.some((fid) => {
        const other = rows.get(fid);
        const theirs = entryOf(other?.frameId, other?.field?.section);
        return fid !== f.fid && other.frameId === row.frameId && theirs?.family === mine.family && theirs.n !== mine.n
          && other.field.kind === "text" && other.field.answered && same(asUrl(other.field.committed), asUrl(row.value));
      });
      if ((claimed !== undefined && claimed !== mine.n) || held) {
        finish(f, "needs_answer", { lastOutcome: "in_another_entry", answer: "Already filled in another entry." });
        return true;
      }
      claims.set(key, mine.n);
      return false;
    };

    // ---- repeating sections: Add the entries the profile can fill (see the header)
    // A section is known by its frame and heading — not its sid, which the page
    // mints per element, so a section re-rendered under a new sid is the same
    // section: its plan (kind and `wanted`) is asked ONCE per run (a failed or
    // hung ask is recorded as nothing to add, never asked again), a failed
    // press is never repeated, and the report has one row for it.
    const plans = new Map(); // sectionKey -> { kind, wanted, reason, order }
    // sectionKey -> { kind, order }: the profile entry each entry holds or is
    // given (/sections `order`; null: place nothing there). Decided once per
    // section. Two sections read as one job, school, language or website kind (a
    // misread "Volunteer Experience") are both left alone (`ambiguous_kind`);
    // otherwise a later section of a kind already placed is placed nowhere.
    // { kind: null, order: null }: the section is LEFT ALONE — nothing written
    // there, nothing added, and the report says so (`unplaced`) — when its
    // order cannot be read, when its entry titles do not run 1..N in page
    // order (the backend places entries by their place on the page, the loop
    // finds a field's entry by its title's number: "1, 3" would give an empty
    // entry the next one's job), when it is a job, school, language or website section
    // the response gave no order, or when it has no placement at all (/sections
    // failed or hung, the heading read as none) and an entry held data. With
    // no placement and every entry empty, page order is safe and stands.
    const placements = new Map();
    const heldAtStart = new Map(); // sectionKey -> any entry held data when first seen
    const placedKinds = new Set();
    const kindHeading = new Map(); // kind -> the heading of the first section that spent it
    // The backend's words for why a section added nothing; `held_out_of_order`
    // is the earlier name of held_twice.
    const REASON_OF = {
      held_twice: "held_twice", held_out_of_order: "held_twice", held_unmatched: "held_unmatched",
      ambiguous_kind: "ambiguous_kind",
    };
    const orderOk = (order) => Array.isArray(order) && order.length <= MAX_ENTRIES
      && order.every((x) => x === null || (Number.isInteger(x) && x >= 0 && x <= MAX_ENTRY_INDEX));
    const numberedInStep = (s) => Array.isArray(s.numbers) && s.numbers.length === s.entries
      && s.numbers.every((n, i) => n === i + 1);
    const sectionLog = new Map(); // sectionKey -> { heading, kind, wanted, entries, added, outcome, reason }
    const NOTHING = { kind: "none", wanted: 0, reason: null, order: undefined };
    const sectionOk = (s) => typeof s?.sid === "string" && FID.test(s.sid) && typeof s.heading === "string"
      && s.heading.trim() !== "" && Number.isInteger(s.entries) && s.entries >= 0 && s.entries <= MAX_ENTRIES;
    const readSections = async () => {
      const seen = (await broadcast({ type: "fill_sections" }) ?? []).flatMap((fr) => (
        Array.isArray(fr?.result) ? fr.result.filter(sectionOk).map((s) => ({ ...s, frameId: fr.frameId })) : []));
      for (const s of seen) {
        const key = sectionKey(s);
        listedSections.add(key);
        // Whether any entry held data when the section was first seen.
        if (!heldAtStart.has(key)) heldAtStart.set(key, Array.isArray(s.filled) && s.filled.some(Boolean));
      }
      return seen;
    };
    const planSections = async (seen) => {
      const ask = [...new Map(seen.filter((s) => !plans.has(sectionKey(s))).map((s) => [sectionKey(s), s])).values()]
        .slice(0, MAX_SECTIONS);
      if (!ask.length || halt()) return;
      const { res } = await post("/api/autofill/sections", {
        ...selector,
        // `held`: what each entry already holds, for the LOCAL backend to
        // match entries to profile entries (it never reaches a model).
        sections: ask.map((s) => ({
          sid: s.sid, heading: s.heading.slice(0, 200), entries: s.entries,
          filled: (Array.isArray(s.filled) ? s.filled : []).slice(0, MAX_ENTRIES).map(Boolean),
          held: (Array.isArray(s.held) ? s.held : []).slice(0, MAX_ENTRIES).map((vs) => (Array.isArray(vs) ? vs : [])
            .slice(0, MAX_HELD).map((v) => String(v).slice(0, HELD_CHARS))),
        })),
      });
      for (const s of ask) {
        const p = res?.sections?.[s.sid];
        const ok = SECTION_KINDS.has(p?.kind) && Number.isInteger(p.wanted) && p.wanted >= 0;
        // `order`: undefined when the backend placed nothing; null when it
        // sent one that cannot be read (the section is left alone — page
        // order is what could repeat a job the page shows).
        plans.set(sectionKey(s), ok ? {
          kind: p.kind, wanted: Math.min(p.wanted, MAX_ENTRIES), reason: REASON_OF[p.reason] ?? null,
          order: p.order == null ? undefined : orderOk(p.order) ? p.order : null,
        } : NOTHING);
      }
    };
    // What one press did, as the report's word: `added` only when the page's
    // entry count grew; no frame answering is `stale` (decided afresh).
    const pressOutcome = (got, entries) => {
      if (!got) return "stale";
      if (got.outcome === "added") return Number.isInteger(got.entries) && got.entries > entries ? "added" : "not_added";
      return wordOf(got.outcome) ?? "stale";
    };
    // Returns whether any entry was added. ONE section per kind: a second
    // section the model gives the same kind gets nothing (a job, school or
    // language kind: neither does the first), so a kind's entries are never
    // doubled.
    const addEntries = async () => {
      const seen = await readSections();
      if (!seen.length) return false;
      await planSections(seen);
      // Two sections of one job, school, language or website kind (a "Volunteer
      // Experience" misread above the real Work Experience): which one is
      // misread cannot be told, so NEITHER is placed or grows — both are left
      // to the user (`ambiguous_kind`), as is one that appears after its kind
      // was placed in an earlier round (what was done there stands).
      const earlier = new Set(placedKinds);
      const count = new Map();
      const headings = new Map(); // kind -> the headings read as it now, in page order
      for (const s of new Map(seen.map((x) => [sectionKey(x), x])).values()) {
        const kind = plans.get(sectionKey(s))?.kind;
        if (!PLACED_KINDS.has(kind)) continue;
        count.set(kind, (count.get(kind) ?? 0) + 1);
        headings.set(kind, [...(headings.get(kind) ?? []), s.heading]);
      }
      // The other section read as this one's kind, when one is known.
      const otherOf = (s, kind) => (headings.get(kind) ?? []).find((h) => h !== s.heading)
        ?? (kindHeading.get(kind) !== s.heading ? kindHeading.get(kind) : undefined);
      for (const s of seen) {
        const key = sectionKey(s);
        const plan = plans.get(key);
        if (placements.has(key)) continue;
        if (plan && PLACED_KINDS.has(plan.kind)
          && (plan.reason === "ambiguous_kind" || count.get(plan.kind) > 1 || earlier.has(plan.kind))) {
          const other = otherOf(s, plan.kind);
          placedKinds.add(plan.kind);
          if (!kindHeading.has(plan.kind)) kindHeading.set(plan.kind, s.heading);
          placements.set(key, { kind: null, order: null });
          sectionLog.set(key, { heading: s.heading, kind: plan.kind, wanted: s.entries,
            entries: s.entries, added: 0, outcome: null, reason: "ambiguous_kind", ...(other ? { other } : {}) });
          continue;
        }
        const placed = Boolean(plan) && PLACED_KINDS.has(plan.kind) && plan.order !== undefined;
        const first = placed && !placedKinds.has(plan.kind);
        if (placed) placedKinds.add(plan.kind);
        if (placed && first) kindHeading.set(plan.kind, s.heading);
        const unreadable = placed && (plan.order === null || !numberedInStep(s));
        // A job, school, language or website section with no order is never page order,
        // held data or not (an Add by page order could pair a new entry with a
        // profile entry missing a required fact); any other unplaced section
        // is, while every entry is empty.
        const noOrder = !placed && Boolean(plan) && PLACED_KINDS.has(plan.kind);
        const unplacedHeld = !placed && (!plan || plan.kind === "none") && heldAtStart.get(key);
        if (noOrder) placedKinds.add(plan.kind);
        if (noOrder && !kindHeading.has(plan.kind)) kindHeading.set(plan.kind, s.heading);
        if (unreadable || noOrder || unplacedHeld) {
          placements.set(key, { kind: null, order: null });
          sectionLog.set(key, { heading: s.heading, kind: plan?.kind ?? "none", wanted: s.entries,
            entries: s.entries, added: 0, outcome: null, reason: "unplaced" });
        } else if (placed) {
          placements.set(key, { kind: plan.kind, order: first ? plan.order : null });
        }
      }
      let added = false;
      const kinds = new Set();
      for (const s of seen) {
        const plan = plans.get(sectionKey(s));
        if (!plan || plan.kind === "none" || kinds.has(plan.kind)) continue;
        // Only a kind's placed first section adds. One left alone, or placed
        // nowhere as a second of its kind, adds nothing — and a left-alone
        // first section still spends its kind, so a second section read as
        // the same kind never adds entries whose fields go nowhere.
        const placedHere = placements.get(sectionKey(s));
        if (placedHere && (placedHere.kind === null || placedHere.order === null)) {
          kinds.add(plan.kind);
          continue;
        }
        kinds.add(plan.kind);
        const key = sectionKey(s);
        const log = sectionLog.get(key)
          ?? { heading: s.heading, kind: plan.kind, wanted: plan.wanted, added: 0, outcome: null, reason: plan.reason };
        sectionLog.set(key, { ...log, entries: s.entries });
        // A press that did not add (or failed) is never pressed again this run;
        // one refused as `stale` (the view changed) is decided afresh.
        if (log.outcome && log.outcome !== "added" && log.outcome !== "stale") continue;
        let entries = s.entries;
        while (entries < plan.wanted) {
          if (halt()) return added;
          const [got] = results(await broadcast({ type: "fill_add", sid: s.sid, heading: s.heading, entries }))
            .filter((r) => r?.sid === s.sid);
          const outcome = pressOutcome(got, entries);
          const row = sectionLog.get(key);
          if (outcome !== "added") {
            sectionLog.set(key, { ...row, outcome });
            break;
          }
          sectionLog.set(key, { ...row, entries: got.entries, added: row.added + (got.entries - entries), outcome });
          entries = got.entries;
          added = true;
        }
      }
      return added;
    };

    let settled = false;
    while (round < L.MAX_ROUNDS) {
      if (halt()) break;
      round += 1;
      const before = snapshot();
      const frames = await broadcast({ type: "fill_inventory", consentForms, runId });
      if (!(frames ?? []).some((fr) => fr?.result !== undefined)) {
        // The first time, nobody was ever asked: say so. Later, the page went
        // away mid-run: keep what was done.
        if (round === 1) throw ns.guidedRun.shown(ns.guidedRun.NO_FRAME_REACHED);
        break;
      }
      let open = observe(frames);
      if (halt()) break;
      // Entries the profile can fill are added before anything is mapped; a
      // full inventory then lists their fields, mapped in this same round.
      if (await addEntries()) {
        if (halt()) break;
        const again = await broadcast({ type: "fill_inventory", consentForms, runId });
        if ((again ?? []).some((fr) => fr?.result !== undefined)) open = observe(again);
      }
      if (!open.length) {
        if ((settled = await settledDone())) break;
        continue;
      }
      await mapFields(open);
      if (halt()) break;

      const { texts, choices, prose } = routed(open);

      // Model calls run beside the page work; page actions stay one at a time.
      let answers = null;
      const asking = prose.length ? answerProse(prose).then((got) => { answers = got; }) : null;
      let proseWritten = !prose.length;
      // Prose is written as soon as its answers are in, between other fields.
      // A prose field no longer on the page (gone, or re-rendered under a new
      // fid by a commit) is skipped: its replacement is answered next round.
      const writeProse = async () => {
        if (proseWritten || !answers || halt()) return;
        proseWritten = true;
        const onPage = new Set(listed);
        for (const f of prose) {
          if (halt()) break;
          if (!onPage.has(f.fid)) continue;
          const choice = answers[f.fid];
          if (!(choice?.answer && choice.reason === "matched")) {
            finish(f, "needs_answer", { lastOutcome: "abstained" });
            continue;
          }
          await onFieldClock(f, L.FIELD_MS, () => fillText(f, choice.answer));
        }
      };
      // Picks made ahead, while the texts are written, in two calls: the
      // leads' (awaited before the first lead) and the rest's. A pick answers
      // the question it was asked for: a field whose fingerprint changed since
      // picks again.
      const ahead = (fields) => pickBatch(fields.filter((f) => pickedTogether(f, rows.get(f.fid))));
      const picking = { lead: ahead(choices.filter(leads)), rest: ahead(choices.filter((f) => !leads(f))) };
      const askedFp = new Map(choices.map((f) => [f.fid, f.fp]));
      const picked = {};
      // One choice field, and whether its work changed the page.
      const workChoice = async (f) => {
        const which = leads(f) ? "lead" : "rest";
        picked[which] ??= await picking[which];
        const given = picked[which].has(f.fid) && askedFp.get(f.fid) === f.fp ? picked[which].get(f.fid) : undefined;
        const row = rows.get(f.fid);
        const items = Array.isArray(row.value) ? Math.min(new Set(row.value).size, L.MAX_ITEMS) : 1;
        const before = pageActions;
        await onFieldClock(f, L.FIELD_MS + L.ITEM_MS * Math.max(0, items - 1), (working) => fillChoice(f, working, given));
        return pageActions !== before;
      };
      let queue = order([...texts, ...choices]);
      const worked = new Set();
      while (queue.length) {
        if (halt()) break;
        const f = queue.shift();
        worked.add(f.fid).add(sameField(f));
        if (leftForAnotherEntry(f)) continue;
        if (f.kind === "text") {
          await onFieldClock(f, L.FIELD_MS, (row) => fillText(f, textOf(f, row), row.format));
          await writeProse();
          continue;
        }
        await writeProse();
        // A choice that changed the page may have added or removed fields.
        if ((await workChoice(f)) && !halt() && (await reshaped())) queue = await reobserve(worked, queue);
      }
      if (asking && !proseWritten && !halt()) {
        await asking;
        await writeProse();
      }
      if (!halt()) await sweep();
      tell({ phase: "round", round });
      if (snapshot() === before && (settled = await settledDone())) break;
    }
    // Out of rounds with the last one still changing things: the final sweep
    // still runs, and a reversion it finds is reported, not hidden.
    if (!settled) await settledDone();
    // The book learns from the fields on the page, after the final sweep only
    // (`finalSwept` already says it ran unhalted). The write gets an allowance
    // of its own past the run's clock, so a run that ends at RUN_MS keeps them.
    if (recipes && finalSwept && !cancelled()) {
      const lessons = listed.map((fid) => lessonOf(rows.get(fid))).filter(Boolean);
      if (lessons.length) {
        let timer;
        try {
          await Promise.race([Promise.resolve().then(() => recipes.record(lessons)),
            new Promise((resolve) => { timer = setTimeout(resolve, L.API_MS); })]);
        } catch {
          // The book's loss, never the fill's.
        } finally {
          clearTimeout(timer);
        }
      }
    }

    const stopped = cancelled();
    const over = timedOut();
    // A revert the engine never got to re-commit (rounds, Stop or clock ran out).
    const tookBackUnretried = (r) => Boolean(r.recommits && r.wrote && r.status === "retry");
    const fields = listed.map((fid) => {
      const r = rows.get(fid);
      return {
        fid,
        frameId: r.frameId,
        question: r.field?.question ?? "",
        section: r.field?.section ?? "",
        required: Boolean(r.field?.required),
        shape: r.field?.shape,
        // Reverted and never re-committed (out of rounds, stopped, out of
        // time): the page took back a value the engine wrote. Said so.
        status: FINAL.has(r.status) ? r.status : tookBackUnretried(r) ? "unconfirmed"
          : r.status === "retry" && !stopped && !over ? "cannot_operate" : "needs_answer",
        answer: tookBackUnretried(r) && !FINAL.has(r.status) ? revertedNote(r.wrote) : r.answer ?? (r.leftover && !DONE.has(r.status)
          ? `Companion wrote "${r.leftover}" here for an earlier question. Check it.` : null),
        route: r.route ?? null,
        slot: r.slot ?? null,
        // Left open when the run's clock ran out: the panel can say so.
        lastOutcome: over && !FINAL.has(r.status) ? "timeout" : r.lastOutcome ?? null,
      };
    });
    // Per section of a profile kind: how many entries were added (value-free).
    // `reason` held_unmatched: an entry on the page holds something the
    // profile does not have, so the section was left alone; held_twice:
    // two hold the same one, so none was added.
    // `other` (ambiguous_kind only): the heading of the other section read as the same kind.
    const sections = [...sectionLog.values()].map(({ heading, kind, wanted, entries, added, outcome, reason, other }) => ({
      heading, kind, wanted, entries, added, outcome, reason: reason ?? null, ...(other ? { other } : {}),
    }));
    const report = { runId, fields, host, aiFailure, stopped, timedOut: over, sections, rounds: round };
    return { ...report, trace: buildRunTrace(report, rows, { startedAt, endedAt: new Date() }) };
  }

  // ---- telemetry: one observation per reported field, and never a value.
  // The contract is app/schemas/autofill_telemetry.py (action "loop_fill").
  // `answer` is what landed on the page (or a note naming it): it never leaves.
  const TELEMETRY_KIND = { text: "text", date: "text", select: "select", group: "radio", search: "combobox", popup: "combobox" };
  const TELEMETRY_OUTCOME = {
    verified: "verified", closest: "closest_filled", assumed: "assumed_filled", partial: "partial",
    already: "prefilled", blocked: "blocked", yours: "user_edited", unconfirmed: "unconfirmed",
    needs_answer: "needs_answer", cannot_operate: "cannot_operate", unsupported: "unsupported",
  };
  // A needs_answer row a value landed on without being chosen as the answer
  // (a group click that committed one, a search or a keyboard open that
  // picked one the page would not give back):
  // the user's to check, sent as filled_unverified.
  const LANDED = new Set(["group_committed", "search_committed", "committed_while_exploring", "committed_while_opening"]);
  const MAX_OBSERVATIONS = 200;
  // A label that holds the value written (a reader that took the value into
  // the question, a leftover note's quoted text) is sent blank: the label is
  // the one free-text key, so it must not become a way for a value to leave.
  // Whole words, any case: "No" is not in "Phone number".
  // The strings a value could hide behind: each value itself and the text
  // quoted inside it (a note's `Searching picked "X"`).
  const denyKeys = (values) => values.flat(2).filter((v) => typeof v === "string" || typeof v === "number")
    .flatMap((v) => {
      const s = String(v).trim();
      return s ? [s, ...[...s.matchAll(/"([^"]+)"/g)].map((m) => m[1].trim()).filter(Boolean)] : [];
    });
  // ONE pattern for a list of keys, compiled once: a key as a whole word, any case.
  const denyRegex = (keys) => (keys.length ? new RegExp(
    `(^|[^\\p{L}\\p{N}])(?:${keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})($|[^\\p{L}\\p{N}])`, "iu") : null);
  const holdsValue = (label, answer) => denyRegex(denyKeys([answer]))?.test(label) ?? false;
  const buildLoopObservations = (report) => (report?.fields ?? []).flatMap((r) => {
    const outcome = r.status === "needs_answer" && LANDED.has(r.lastOutcome) ? "filled_unverified"
      : TELEMETRY_OUTCOME[r.status];
    if (!outcome) return [];
    const question = String(r.question ?? "");
    return [{
      label: holdsValue(question, r.answer) ? "" : question.slice(0, 160),
      kind: TELEMETRY_KIND[r.shape] ?? "text",
      host: String(report.host ?? "").slice(0, 255),
      outcome,
      rule_id: r.slot ? `slot:${r.slot}` : r.route ? `route:${r.route}` : null,
    }];
  }).slice(0, MAX_OBSERVATIONS);

  // ---- the run trace: what the backend stores (POST /api/autofill/runs,
  // app/schemas/autofill_trace.py). ONE field the schema rejects loses the whole
  // run, so every string is checked against its pattern here, and the trace is
  // built from NAMED sources only: never a spread of a row, which holds
  // `ignored` ("type:<typed value>"), `field.help` and the explore results.
  // THE RULE: the trace records which page option was chosen and the page's own
  // option texts; it never holds a typed or profile string in a free-text slot.
  // The slots the schema cannot check are `label` and `section`, and they are
  // blanked RUN-WIDE: by any row's answer, value, write or leftover, and by any
  // row's `field.committed` (the page's current value: a deny key, never
  // emitted). A sibling's key counts only from a text, date, search or popup
  // field when it is 2+ characters, or from any field when it is 4+, so a
  // "Yes" or "No" on a select never blanks the labels that say it and a typed
  // "2" never blanks "Experience 2"; a row's own keys always count.
  const MAX_RUN_FIELDS = 200;
  const TRACE_FIELD_OPTIONS = 30;
  const TRACE_TEXT = 200;
  const TRACE_SHAPES = new Set(["text", "date", "select", "group", "search", "popup"]);
  const TYPED_SHAPES = new Set(["text", "date", "search", "popup"]);
  const MIN_TYPED_SIBLING_KEY = 2;
  const MIN_SIBLING_KEY = 4;
  const TRACE_HOST = /^[a-z0-9.-]{1,253}(:\d{1,5})?$/;
  const TRACE_FAMILY = /^f:[0-9a-z]{1,24}$/;
  const TRACE_SOURCE = /^[a-z-]+$/;
  const MAX_TRACE_ROUNDS = 10;
  // A key that is the row's own passive option (a country select answered
  // "United States" would blank "authorized to work in the United States?"
  // everywhere; the option texts are recorded anyway) or a lone checkbox's
  // yes/no word (its oids are yes and no) says nothing a label could leak.
  const BOOLEAN_WORDS = new Set(["yes", "no", "true", "false", "on", "off"]);
  const isLoneCheckbox = (f) => f?.shape === "group" && f.options?.length === 2 && f.options[0]?.oid === "yes"
    && f.options[1]?.oid === "no";
  const plainKey = (row) => {
    const own = new Set((row.field?.options ?? []).map((o) => String(o?.text ?? "").trim().toLowerCase()));
    const lone = isLoneCheckbox(row.field);
    return (key) => own.has(key.trim().toLowerCase()) || (lone && BOOLEAN_WORDS.has(key.trim().toLowerCase()));
  };
  const rowKeys = (row) => {
    const plain = plainKey(row);
    return denyKeys([row.answer, row.value, row.wrote, row.leftover, row.field?.committed]).filter((key) => !plain(key));
  };
  const siblingKeys = (row) => rowKeys(row).filter((k) => k.length >= (TYPED_SHAPES.has(row.field?.shape)
    ? MIN_TYPED_SIBLING_KEY : MIN_SIBLING_KEY));
  const traceField = (status, row, others) => {
    const f = row.field ?? {};
    const own = denyRegex(rowKeys(row));
    const clipped = (text) => String(text).slice(0, TRACE_TEXT);
    const shown = (text) => (others?.test(text) || own?.test(text) ? "" : clipped(text));
    const options = Array.isArray(f.options) ? f.options : null;
    return {
      fid: row.fid,
      label: shown(f.question ?? ""),
      label_source: typeof f.source === "string" && TRACE_SOURCE.test(f.source) ? f.source : null,
      shape: TRACE_SHAPES.has(f.shape) ? f.shape : "unknown",
      section: f.section ? shown(f.section) : null,
      required: Boolean(f.required),
      // The inventory's passive list only (a static list, read before anything
      // was typed): an explore's rows echo what a search typed.
      options: options && options.slice(0, TRACE_FIELD_OPTIONS).map((o) => clipped(o?.text ?? "")),
      option_count: options?.length ?? 0,
      ...(TRACE_FAMILY.test(f.recipe?.family) ? { family: f.recipe.family } : {}),
      steps: row.steps ?? [],
      outcome: status,
      round: Math.min(row.round ?? 0, MAX_TRACE_ROUNDS),
    };
  };
  const runTrace = (report, rows, meta) => {
    const host = String(report.host ?? "").toLowerCase();
    if (!TRACE_HOST.test(host)) return null;
    const others = denyRegex([...new Set([...rows.values()].flatMap(siblingKeys))]);
    return {
      run_id: String(report.runId).toLowerCase(),
      host,
      started_at: meta.startedAt.toISOString(),
      ended_at: meta.endedAt.toISOString(),
      halted: report.stopped ? "stopped" : report.timedOut ? "timeout" : null,
      rounds: Math.min(report.rounds ?? 0, MAX_TRACE_ROUNDS),
      fields: report.fields.filter((r) => FID.test(r.fid) && rows.has(r.fid)).slice(0, MAX_RUN_FIELDS)
        .map((r) => traceField(r.status, rows.get(r.fid), others)),
    };
  };
  // null when the page's host cannot be said in the schema's pattern (no frame
  // ever named one: such a run listed no field worth keeping), or when
  // anything throws. The warning is fixed text: an error could echo a value.
  const buildRunTrace = (report, rows, meta) => {
    try {
      return runTrace(report, rows, meta);
    } catch {
      console.warn("[maestro-cs] the run trace could not be built");
      return null;
    }
  };

  // ---- the report's repeating sections, as the panel says them: one line per
  // section still short of what the profile can fill (a press that added
  // nothing, Stop, the clock), where the section was left alone because an
  // entry on the page holds something the profile does not have, or where
  // none was added because two hold the same one. Empty when there is
  // nothing for the user to add.
  const sectionLines = (report) => (report?.sections ?? []).flatMap((s) => {
    if (s.reason === "unplaced") {
      return [`${s.heading}: the items on the page couldn't be matched to your profile, so this section was left for you.`];
    }
    if (s.reason === "held_unmatched") {
      return [`${s.heading}: the items on the page don't match your profile, so this section was left for you.`];
    }
    if (s.reason === "held_twice") {
      return [`${s.heading}: the items on the page don't match your profile, so none were added.`];
    }
    if (s.reason === "ambiguous_kind") {
      return [s.other
        ? `${s.heading}: this section looks like the same kind of list as "${s.other}", so it was left for you.`
        : `${s.heading}: another section on this page looks like the same kind of list, so this section was left for you.`];
    }
    if (!(s.entries < s.wanted)) return [];
    const needed = s.wanted - (s.entries - s.added); // what the section was short of before the run
    return [`${s.heading}: ${s.added} of ${needed} added. Add the rest yourself.`];
  });

  ns.fillLoop = { runFill, sourceHintOf, limits, buildLoopObservations, buildRunTrace, effectOf, exploreEffect, sectionLines };
})();
