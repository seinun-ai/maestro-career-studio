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
 *   per field (`entry_slot`, with the section's `entry_kind`; null places
 *   nothing there), so an empty entry before a pre-filled one is never given
 *   the job the page already shows. Only the first section of a kind is
 *   placed, and an order that cannot be read places nothing — never page
 *   order. One holding data keeps it (`already`).
 *   Each press is a deliberate write, not a trial: once per wanted entry,
 *   counted only when the page's entry count grew; a press that did not grow
 *   it is not pressed again this run. A full inventory follows the adds, so
 *   the new entries' fields are mapped in the same round. The report's
 *   `sections` says what was added, by kind — value-free. The backend leaves
 *   a section whose entry holds something the profile does not have to the
 *   user (`reason` held_unmatched: nothing placed, nothing added), and adds
 *   nothing when two entries hold the same one (held_out_of_order). Within a
 *   section, one fact is written into ONE entry (`in_another_entry`).
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
 * WHAT THIS FILE PUBLISHES: ns.fillLoop = { runFill, sourceHintOf, limits,
 * buildLoopObservations, sectionLines }.
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

  async function runFill(deps, options = {}) {
    const { broadcast, api } = deps ?? {};
    for (const [name, dep] of [["broadcast", broadcast], ["api", api]]) {
      if (typeof dep !== "function") throw new TypeError(`fill-loop: missing dep ${name}`);
    }
    const cancelled = deps.cancelled ?? (() => false);
    const L = { ...limits };
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
    //   deadline, spent, started, recommits, failedMoves, ignored, wrote, wroteAs }
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

    // ---- rows and clocks
    const set = (fid, patch) => {
      const was = rows.get(fid)?.status;
      const row = { ...rows.get(fid), ...patch };
      rows.set(fid, row);
      if (patch.status && patch.status !== was && FINAL.has(patch.status)) tell({ phase: "field", fid, status: patch.status });
      return row;
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
    // null when the backend failed or ran out of time; a clock running out is not an AI failure.
    const post = async (path, body, deadline) => {
      try {
        return await bounded(() => api(path, { method: "POST", body: JSON.stringify(body) }), deadline);
      } catch (err) {
        if (!err?.deadline) aiFailure ??= err;
        return null;
      }
    };
    const question = (f) => String(f.question ?? "").slice(0, 300);
    const routeOf = (row) => (row.route === "low_stakes" ? "low_stakes" : "slot");
    const policyBlocks = (text) => Boolean(ns.isPolicyBlocked?.(text, { consentForms }));

    // ---- the page: one operation at a time, each awaited
    const results = (frames) => (frames ?? []).map((fr) => fr?.result).filter((r) => r !== undefined && r !== null);
    const rowsOf = (frames) => results(frames).flatMap((r) => (Array.isArray(r) ? r : []));
    const merged = (frames) => Object.assign({}, ...results(frames).filter((r) => typeof r === "object" && !Array.isArray(r)));
    // One action on one field. Outcomes beyond the page's own: halted (Stop or
    // the run's end), late (the field's clock), refused (recorded as final here).
    // `closing` (give_up) may still run out of time — it only closes a popup.
    // `overtime` (a set committing what it already picked) may run past the field's clock.
    const act = async (f, action, { closing = false, overtime = false } = {}) => {
      if (cancelled() || (!closing && timedOut())) return { outcome: "halted" };
      if (!closing && !overtime && fieldLate(f)) return { outcome: "late" };
      if (!closing) pageActions += 1;
      const [got] = rowsOf(await broadcast({ type: "fill_apply", actions: [{ fid: f.fid, fp: f.fp, ...action }] }))
        .filter((r) => r?.fid === f.fid);
      if (!got) return { outcome: "stale" }; // no frame owns the fid any more
      if (got.outcome === "cancelled") return { outcome: "halted" };
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
      const got = merged(await broadcast({
        type: "fill_explore", requests: [{ fid: f.fid, fp: f.fp, ...(term ? { term } : {}), ...(Number.isFinite(left) ? { ms: left } : {}) }],
      }))[f.fid];
      return got ?? { options: [], complete: false, error: "stale" };
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
    const pickOf = (got, offered) => {
      if (!got) return null;
      const text = got.oids?.length && STATUS[got.reason] ? offered.find((o) => o.oid === got.oids[0])?.text : undefined;
      return text ? { text, reason: got.reason } : { abstained: true };
    };
    const pick = async (f, row, opts, complete, item) => {
      const { offered, field } = pickAsk(f, row, opts, complete, item);
      if (!offered.length || halt() || fieldLate(f)) return null;
      const res = await post("/api/autofill/pick", { ...asked, fields: [field] }, rows.get(f.fid).deadline);
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
      && (row.route === "low_stakes" || (typeof row.value === "string" && row.value) || itemOf(f, row) !== undefined);
    const pickBatch = async (fields) => {
      const out = new Map();
      const asks = fields.map((f) => {
        const row = rows.get(f.fid);
        return [f, pickAsk(f, row, f.options, f.optionsComplete, itemOf(f, row))];
      });
      for (let i = 0; i < asks.length; i += CHUNK) {
        if (halt()) break;
        const part = asks.slice(i, i + CHUNK);
        const res = await post("/api/autofill/pick", { ...asked, fields: part.map(([, a]) => a.field) });
        for (const [f, a] of part) out.set(f.fid, pickOf(res?.picks?.[f.fid], a.offered));
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
        const res = await post("/api/autofill/step", {
          ...asked, fid: f.fid, question: question(f), route: routeOf(row), slot: row.slot ?? null,
          ...(item !== undefined ? { item: String(item).slice(0, 300) } : {}),
          history: history.slice(-HISTORY_KEPT),
          candidates: state.candidates.slice(0, STEP_CANDIDATES),
          complete: Boolean(state.complete),
        }, rows.get(f.fid).deadline);
        if (halt()) return halted(f);
        if (fieldLate(f)) return giveUp(f, "late");
        const chosen = res?.mid && res.mid !== "give_up" && STEP_REASONS.has(res.reason)
          ? state.candidates.find((c) => c.mid === res.mid) : null;
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
        if (CAN_ADAPT.has(f.shape)) return settle(f, await adapt(f, row, historyEntry("choose", "abstained"), item));
        return finish(f, "needs_answer", { lastOutcome: "abstained" });
      }
      const out = await act(f, { op: "choose", text: picked.text, ...(f.shape === "search" ? { term: term ?? picked.text } : {}) });
      if (notDone(f, out)) return undefined;
      if (out.outcome === "verified") return done(f, picked.reason, out.committed);
      if (out.outcome === "unconfirmed") return unconfirmed(f, picked.text);
      if (out.outcome === "unexpected" && CAN_ADAPT.has(f.shape)) {
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
      const pairs = []; // [option text, source item, reason]
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
          if (p?.text) pairs.push([p.text, item, p.reason]);
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
        // What was picked is committed even when the clock ran out picking the rest.
        const out = await act(f, action, { overtime: true });
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
      if (noOptions) return settle(f, await adapt(f, row, noOptions, item));
      return commitOne(f, row, opts, complete, term, item, prepicked);
    };

    // The format a written value is compared in, decided by the FACT's slot,
    // never by what the value looks like: a page re-punctuates a phone number
    // and a salary ("$80,000" for 80000). /map says it (`format`, from the
    // slot, server-side); this reading of the slot name is only the fallback
    // for a response that does not.
    const FORMATS = new Set(["phone", "money"]);
    const formatOf = (slot) => {
      if (/phone/i.test(slot ?? "")) return "phone";
      if (/(^|[._])(desired_)?(salary|compensation|pay)([._]|$)/i.test(slot ?? "")) return "money";
      return undefined;
    };
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
          const mine = had.wrote && same(f.committed, had.wrote);
          rows.set(f.fid, { fid: f.fid, attempts: 0, status: "new", ...(mine ? { leftover: had.wrote } : {}) });
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
          rows.set(f.fid, { ...(old ?? { attempts: 0 }), fid: f.fid, status: carried });
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
    // the page's entries hold), with the section's kind: { entry_slot,
    // entry_kind } — entry_slot a number, or null (an entry the backend placed
    // nowhere, one past the order, every entry of a section whose order could
    // not be read or that is not the first of its kind) — for a field in a
    // section the page listed and the backend placed; else nothing, and /map
    // places by page order.
    const placement = (f) => {
      const frameId = rows.get(f.fid)?.frameId;
      const mine = entryOf(frameId, f.section);
      const placed = mine ? placements.get(`${frameId}\n${mine.family}`) : undefined;
      if (!placed) return {};
      const at = Math.min(Math.max(Number(f.repeatIndex) || 0, 0), 20);
      return { entry_slot: placed.order && at < placed.order.length ? placed.order[at] : null, entry_kind: placed.kind };
    };
    const mapFields = async (open) => {
      const unmapped = open.filter((f) => !rows.get(f.fid).route);
      for (let i = 0; i < unmapped.length; i += CHUNK) {
        if (halt()) return;
        const part = unmapped.slice(i, i + CHUNK);
        const res = await post("/api/autofill/map", {
          ...selector,
          fields: part.map((f) => ({
            fid: f.fid, question: question(f), section: f.section ? String(f.section).slice(0, 200) : null,
            repeat_index: Math.min(Math.max(Number(f.repeatIndex) || 0, 0), 20), ...placement(f), shape: f.shape,
            multi: Boolean(f.multi), required: Boolean(f.required),
            options: usable(f.options).slice(0, MAP_OPTIONS).map((o) => o.text.slice(0, 300)),
          })),
        });
        for (const f of part) {
          const m = res?.fields?.[f.fid];
          // The write format is the backend's (decided by the slot); an older
          // response that does not say gets the loop's own reading of the slot.
          const format = m && "format" in m ? (FORMATS.has(m.format) ? m.format : undefined) : formatOf(m?.slot);
          if (m) set(f.fid, { route: m.route, slot: m.slot ?? null, value: m.value ?? null, format });
        }
      }
    };

    // A value the engine verified that no longer holds gets ONE re-commit per
    // run (on the field's remaining time: `work`); reverting again, it is
    // reported unstable — `unconfirmed`, never filled. The sweep's word about
    // any other field (the user's, a prefilled one) is not ours to act on.
    const sweep = async () => {
      if (cancelled()) return 0;
      let reverted = 0;
      for (const r of rowsOf(await broadcast({ type: "fill_sweep" }))) {
        const row = rows.get(r?.fid);
        if (!row || !DONE.has(row.status) || r.outcome === "verified" || r.outcome === "cancelled") continue;
        if (REFUSED[r.outcome]) {
          set(r.fid, { status: REFUSED[r.outcome], lastOutcome: r.outcome });
          continue;
        }
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
    // only if nothing reverted.
    const settledDone = async () => {
      if (halt()) return true;
      if (L.QUIET_MS > 0) await wait(Math.min(L.QUIET_MS, runDeadline - Date.now()));
      if (halt()) return true;
      return (await sweep()) === 0;
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
        if (!row.route || row.route === "none") finish(f, "needs_answer", { lastOutcome: row.route ? "no_fact" : "not_mapped" });
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
    const listedSections = new Set(); // `${frameId}\n${heading, lowercased}` fill_sections returned
    const entryOf = (frameId, section) => {
      const r = repeatOf(section);
      return r && listedSections.has(`${frameId}\n${r.base.toLowerCase()}`) ? { family: r.base.toLowerCase(), n: r.n } : null;
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
    const plans = new Map(); // key -> { kind, wanted, reason, order }
    // `${frameId}\n${heading, lowercased}` -> { kind, order }: the profile entry each
    // entry holds or is given (/sections `order`; null: place nothing there).
    // Decided once per section; only the FIRST section of a kind, in page
    // order, keeps its order (a second one read as the same kind — a misread
    // "Volunteer Experience" — would be given job #1 again).
    const placements = new Map();
    const placedKinds = new Set();
    const PLACED_KINDS = new Set(["experience", "education"]);
    const REASONS = new Set(["held_out_of_order", "held_unmatched"]);
    const ENTRY_SLOT_MAX = 20;
    const orderOk = (order) => Array.isArray(order) && order.length <= MAX_ENTRIES
      && order.every((x) => x === null || (Number.isInteger(x) && x >= 0 && x <= ENTRY_SLOT_MAX));
    const sectionLog = new Map(); // key -> { heading, kind, wanted, entries, added, outcome, reason }
    const sectionKey = (s) => `${s.frameId}\n${s.heading}`;
    const NOTHING = { kind: "none", wanted: 0, reason: null, order: undefined };
    const sectionOk = (s) => typeof s?.sid === "string" && FID.test(s.sid) && typeof s.heading === "string"
      && s.heading.trim() !== "" && Number.isInteger(s.entries) && s.entries >= 0 && s.entries <= MAX_ENTRIES;
    const readSections = async () => {
      const seen = (await broadcast({ type: "fill_sections" }) ?? []).flatMap((fr) => (
        Array.isArray(fr?.result) ? fr.result.filter(sectionOk).map((s) => ({ ...s, frameId: fr.frameId })) : []));
      for (const s of seen) listedSections.add(`${s.frameId}\n${s.heading.toLowerCase()}`);
      return seen;
    };
    const planSections = async (seen) => {
      const ask = [...new Map(seen.filter((s) => !plans.has(sectionKey(s))).map((s) => [sectionKey(s), s])).values()]
        .slice(0, MAX_SECTIONS);
      if (!ask.length || halt()) return;
      const res = await post("/api/autofill/sections", {
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
        // `order`: undefined when the backend placed nothing (page order
        // stands); null when it sent one that cannot be read (place nothing —
        // page order is what could repeat a job the page shows).
        plans.set(sectionKey(s), ok ? {
          kind: p.kind, wanted: Math.min(p.wanted, MAX_ENTRIES), reason: REASONS.has(p.reason) ? p.reason : null,
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
    // section the model gives the same kind gets nothing, so a kind's entries
    // are never doubled.
    const addEntries = async () => {
      const seen = await readSections();
      if (!seen.length) return false;
      await planSections(seen);
      for (const s of seen) {
        const plan = plans.get(sectionKey(s));
        const key = `${s.frameId}\n${s.heading.toLowerCase()}`;
        if (!plan || !PLACED_KINDS.has(plan.kind) || plan.order === undefined || placements.has(key)) continue;
        const first = !placedKinds.has(plan.kind);
        placedKinds.add(plan.kind);
        placements.set(key, { kind: plan.kind, order: first ? plan.order : null });
      }
      let added = false;
      const kinds = new Set();
      for (const s of seen) {
        const plan = plans.get(sectionKey(s));
        if (!plan || plan.kind === "none" || kinds.has(plan.kind)) continue;
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
    for (let round = 1; round <= L.MAX_ROUNDS; round += 1) {
      if (halt()) break;
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
    // profile does not have, so the section was left alone; held_out_of_order:
    // two hold the same one, so none was added.
    const sections = [...sectionLog.values()].map(({ heading, kind, wanted, entries, added, outcome, reason }) => ({
      heading, kind, wanted, entries, added, outcome, reason: reason ?? null,
    }));
    return { runId, fields, host, aiFailure, stopped, timedOut: over, sections };
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
  const holdsValue = (label, answer) => {
    const values = [answer, ...[...String(answer ?? "").matchAll(/"([^"]+)"/g)].map((m) => m[1])]
      .map((v) => String(v ?? "").trim()).filter(Boolean);
    return values.some((v) => new RegExp(`(^|[^\\p{L}\\p{N}])${v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^\\p{L}\\p{N}])`, "iu").test(label));
  };
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

  // ---- the report's repeating sections, as the panel says them: one line per
  // section still short of what the profile can fill (a press that added
  // nothing, Stop, the clock), where the section was left alone because an
  // entry on the page holds something the profile does not have, or where
  // none was added because two hold the same one. Empty when there is
  // nothing for the user to add.
  const sectionLines = (report) => (report?.sections ?? []).flatMap((s) => {
    if (s.reason === "held_unmatched") {
      return [`${s.heading}: the items on the page don't match your profile, so this section was left for you.`];
    }
    if (s.reason === "held_out_of_order") {
      return [`${s.heading}: the items on the page don't match your profile, so none were added.`];
    }
    if (!(s.entries < s.wanted)) return [];
    const needed = s.wanted - (s.entries - s.added); // what the section was short of before the run
    return [`${s.heading}: ${s.added} of ${needed} added. Add the rest yourself.`];
  });

  ns.fillLoop = { runFill, sourceHintOf, limits, buildLoopObservations, sectionLines };
})();
