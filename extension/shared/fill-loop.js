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
 * - Policy-blocked options are never offered to /pick or /map. Every set, search
 *   or native, is picked one source item at a time (`item`); single-answer
 *   fields whose whole list the inventory read are picked together, 40 a call.
 *   Only matched / closest / assumed (and /step's progress) count as answers.
 * - A field whose fingerprint changed under the same fid is a new question:
 *   mapped again, nothing carried over.
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
 *   (`failedMoves`), and two page operations in a row that changed nothing at
 *   all (`no_effect`) make the field `unsupported`.
 * - Never stall: every backend wait is bounded (API_MS, and never past the
 *   field's or the run's clock); the run has a clock; rounds, attempts, steps
 *   and items are capped. A late answer is ignored. Before finishing, a quiet
 *   period (QUIET_MS) and a final sweep give a late reversion the chance to
 *   show: a field the engine wrote that reverted gets ONE re-commit per run,
 *   and a second reversion reports it `unconfirmed` (unstable).
 * - Exploring can commit (a search that finds one hit picks it): the page
 *   takes that back; one it could not take back leaves the field to the user,
 *   named (committed_while_exploring).
 * - Nothing is guessed when the AI cannot be reached (`aiFailure`).
 * - Stop: `cancelled()` is checked before every page action; the panel also
 *   sends `fill_cancel`, which cancels the page operation in flight.
 *
 * THE OUTCOME VOCABULARIES, and where each one ends
 *   page outcome   verified | partial | unexpected (+reason) | reverted | stale |
 *     (fill-ops)   unconfirmed (it shows, the page's proof did not move) |
 *                  progressed | closed | yours | blocked | unsupported |
 *                  cancelled | timeout; reason `no_effect` when no gesture
 *                  changed the evidence, the open popups or the value
 *                  → read by act(); never leaves this file as a status.
 *   act()          the page's outcome, or halted (Stop / run clock) | late
 *                  (field clock) | refused (yours/blocked/unsupported, or a
 *                  second no_effect in a row — already recorded as the row's
 *                  final status) | stale (no frame owns it)
 *                  → the caller turns it into a row status (notDone, settle).
 *   adapt()        verified (+reason) | landed (group_committed) |
 *                  unconfirmed | gave_up | no_answer | exhausted | late |
 *                  stale | final | halted
 *                  → settle() (one value) or commitSet (one item).
 *   row status     new | open | retry while working; the final ones below.
 *                  `lastOutcome` keeps the word that decided it.
 *   report status  verified | closest | assumed | already | blocked | yours |
 *                  partial | unconfirmed (a value that shows but was never
 *                  confirmed, or reverted twice: `unstable`) | needs_answer |
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
 * buildLoopObservations }.
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
  const NO_EFFECT_LIMIT = 2; // page operations in a row that changed nothing: the widget ignores the engine

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
  // a JSON string: `Open the group "Job Board"`).
  const quotedText = (describe) => {
    const at = typeof describe === "string" ? describe.indexOf('"') : -1;
    if (at < 0) return null;
    try {
      const text = JSON.parse(describe.slice(at));
      return typeof text === "string" ? text : null;
    } catch {
      return null;
    }
  };
  // Shown beside the field in the panel, so it keeps the panel's copy rules:
  // two sentences, never an em dash joining them.
  const landedNote = (text) => (text ? `Companion clicked "${text}". Check it.` : "Companion clicked an option. Check it.");
  const unstableNote = (text) => (text ? `Companion filled "${text}" twice and the page took it back both times. Check it.`
    : "Companion filled this twice and the page took it back both times. Check it.");
  const stuckNote = (committed) => {
    const text = [committed].flat().filter((v) => v != null && String(v).trim() !== "").join(", ");
    return text ? `Searching picked "${text}" and Companion couldn't take it back. Check it.`
      : "Searching picked a value and Companion couldn't take it back. Check it.";
  };
  // Options a model may be shown: never a never-fill one, never under the reserved key.
  const usable = (opts) => (opts ?? []).filter((o) => o && !o.policyBlocked && typeof o.text === "string"
    && typeof o.oid === "string" && o.oid.length >= 1 && o.oid.length <= 16 && o.oid !== "none");

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
    const selector = {};
    if (options.applicationId) selector.application_id = options.applicationId;
    else if (options.base) selector.base = String(options.base).slice(0, 200);
    const asked = { ...selector, source_hint: options.sourceHint ? String(options.sourceHint).slice(0, 60) : null };
    // fid -> { fid, field, frameId, status, attempts, route, slot, value, answer, lastOutcome,
    //   deadline, spent, started, recommits, failedMoves, noEffect, wrote, wroteAs }
    const rows = new Map();
    let listed = []; // the latest inventory's fids, in page order
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
    const finish = (f, status, patch = {}) => set(f.fid, { status, ...patch });
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
      if (!STATUS[reason]) return unconfirmed(f, answer, reason === "unstable" ? reason : undefined); // never "verified" by default
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
      return set(f.fid, { status: "open", started: now, deadline: now + Math.max(0, ms - (rows.get(f.fid).spent ?? 0)) });
    };
    const rest = (f) => {
      const row = rows.get(f.fid);
      if (row?.started) set(f.fid, { spent: (row.spent ?? 0) + (Date.now() - row.started), started: null });
    };
    const worked = async (f, ms, fn) => {
      const row = work(f, ms);
      try {
        return await fn(row);
      } finally {
        rest(f);
      }
    };
    const fieldLate = (f) => Date.now() >= (rows.get(f.fid)?.deadline ?? Infinity);
    // Two page operations in a row that changed nothing at all (`no_effect`,
    // judged on the page): the widget ignores synthetic input, and the engine
    // has no other kind. True when that just made the field `unsupported`.
    // Anything else the page did resets the count.
    const ignoredBy = (f, reason) => {
      const n = reason === "no_effect" ? (rows.get(f.fid).noEffect ?? 0) + 1 : 0;
      set(f.fid, { noEffect: n });
      if (n < NO_EFFECT_LIMIT) return false;
      finish(f, "unsupported", { lastOutcome: "no_effect" });
      return true;
    };
    // Stopped, out of run time, or out of field time: only the last is the field's own fault.
    const lateOrHalted = (f) => {
      if (!cancelled() && !timedOut() && fieldLate(f)) finish(f, "cannot_operate", { lastOutcome: "timeout" });
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
      const [got] = rowsOf(await broadcast({ type: "fill_apply", actions: [{ fid: f.fid, fp: f.fp, ...action }] }))
        .filter((r) => r?.fid === f.fid);
      if (!got) return { outcome: "stale" }; // no frame owns the fid any more
      if (got.outcome === "cancelled") return { outcome: "halted" };
      if (REFUSED[got.outcome]) {
        finish(f, REFUSED[got.outcome], { lastOutcome: got.outcome });
        return { outcome: "refused" };
      }
      // A close is the engine tidying up, not an attempt on the field.
      if (!closing && ignoredBy(f, got.reason)) return { outcome: "refused" };
      return got;
    };
    // True when the action did not happen and there is nothing more to do now.
    const notDone = (f, out) => {
      if (out.outcome === "halted" || out.outcome === "refused") return true;
      if (out.outcome === "late") {
        finish(f, "cannot_operate", { lastOutcome: "timeout" });
        return true;
      }
      return false;
    };
    const explore = async (f, term) => {
      if (halt() || fieldLate(f)) return null;
      const got = merged(await broadcast({
        type: "fill_explore", requests: [{ fid: f.fid, fp: f.fp, ...(term ? { term } : {}) }],
      }))[f.fid];
      return got ?? { options: [], complete: false, error: "stale" };
    };
    // An explore that went wrong: true when it decided the field for now.
    const exploreRefused = (f, got) => {
      if (REFUSED[got.error]) {
        finish(f, REFUSED[got.error], { lastOutcome: got.error });
        return true;
      }
      if (got.error === "cancelled") return true;
      if (ignoredBy(f, got.error)) return true;
      // Exploring picked a value (a one-hit search) and the page could not
      // take it back: nothing more is tried on the field; the user is told
      // what it holds now.
      if (got.error === "committed_while_exploring") {
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
          // Complete only when the model sees EVERY option: none hidden by policy, none past the cap.
          complete: Boolean(complete) && offered.length === (opts ?? []).length && offered.length <= PICK_OPTIONS,
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
    // What a state SHOWS — its value, whether its popup is open, the moves on
    // offer — never its version, which the page mints afresh on every read: a
    // move that failed from a state that looks the same fails the same way.
    const stateKey = (state) => JSON.stringify([state.committed ?? null, Boolean(state.popupOpen),
      (state.candidates ?? []).map((c) => [c?.mid, c?.describe])]);
    const FAILED = new Set(["unexpected", "reverted"]);
    const adapt = async (f, row, first, item) => {
      const value = item ?? (typeof row.value === "string" ? row.value : undefined);
      const history = first ? [first] : [];
      // A state + move pair that failed, for this field and this run: never
      // sent to the page again. The row keeps it across rounds and items.
      const failedMoves = rows.get(f.fid).failedMoves ?? new Set();
      set(f.fid, { failedMoves });
      let state = null; // kept (not re-read) when a proposed move was refused here: the page's state is untouched
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
        const tried = `${stateKey(state)}:${chosen.mid}`;
        if (failedMoves.has(tried)) {
          // Proposed again on the same state: not executed. The model hears so,
          // and chooses again from the same state.
          const refused = historyEntry(chosen.mid, "already_failed");
          if (refused) history.push(refused);
          continue;
        }
        const asProgress = res.reason === "progress" && chosen.mid.startsWith("click:");
        const out = await act(f, {
          op: "move", mid: chosen.mid, version: state.version, ...(asProgress ? { as: "progress" } : {}),
        });
        state = null; // a move consumes the state it was chosen from
        if (out.outcome === "halted") return halted(f);
        if (out.outcome === "refused") return { outcome: "final" };
        if (out.outcome === "late") return giveUp(f, "late");
        if (FAILED.has(out.outcome) && out.reason !== "group_committed") failedMoves.add(tried);
        const entry = historyEntry(chosen.mid, out.outcome, out.reason);
        if (entry) history.push(entry);
        if (out.outcome === "verified") return { outcome: "verified", reason: res.reason, committed: out.committed };
        if (out.outcome === "unconfirmed") {
          return { outcome: "unconfirmed", text: quotedText(chosen.describe) ?? ([out.committed].flat().filter(Boolean).join(", ") || null) };
        }
        if (out.outcome === "unexpected" && out.reason === "group_committed") {
          return { outcome: "landed", text: quotedText(chosen.describe) ?? ([out.committed].flat().filter(Boolean).join(", ") || null) };
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
        finish(f, "needs_answer", { answer: landedNote(r.text), lastOutcome: "group_committed", wrote: r.text });
      }
      else if (r.outcome === "gave_up") finish(f, "needs_answer", { lastOutcome: "abstained" });
      else if (r.outcome === "no_answer") finish(f, "needs_answer", { lastOutcome: "no_answer" });
      else if (r.outcome === "exhausted") finish(f, "cannot_operate", { lastOutcome: "step_budget" });
      else if (r.outcome === "late") finish(f, "cannot_operate", { lastOutcome: "timeout" });
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
            if (exploreRefused(f, got)) return undefined;
            // Radio rows: the widget takes ONE answer after all (nothing is committed yet).
            if (got.multi === false) {
              if (holdsOne(f, row, got)) return keepHeld(f, row);
              if (all.length > 1) return finish(f, "needs_answer", { lastOutcome: "set_for_one" });
              return commitOne(f, row, got.options ?? [], false, item, item);
            }
            if (got.options?.length && !usable(got.options).length) {
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
            landed.push(r.text ?? ([r.committed].flat().filter(Boolean).join(", ") || null));
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
        ...[...new Set(landed)].map(landedNote),
      ];
      if (covered.size === n) return done(f, [...covered.values()].includes("closest") ? "closest" : "matched", committed);
      const lastOutcome = late.length ? "timeout" : landed.length ? "group_committed" : "missing";
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
      // list (radios or checkboxes): a fact of several items on one not known
      // to take several explores its first item before deciding.
      let multi = Boolean(f.multi);
      let learnt = null;
      if (f.shape === "search" && !multi && Array.isArray(value) && value.length > 1) {
        const first = String(value[0]);
        const got = await explore(f, first);
        if (!got) return lateOrHalted(f);
        if (exploreRefused(f, got)) return undefined;
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
        if (exploreRefused(f, got)) return undefined;
        if (holdsOne(f, row, got)) return keepHeld(f, row);
        if (got.options?.length) {
          opts = got.options;
          complete = Boolean(got.complete);
        } else if (!opts.length) {
          noOptions = historyEntry(term ? "search:value" : "open", "unexpected", got.error ?? "empty_popup");
        }
      }
      if (opts.length && !usable(opts).length) return finish(f, "blocked", { lastOutcome: "blocked" });
      if (isSet) return commitSet(f, row, opts, complete, noOptions, learnt);
      if (noOptions) return settle(f, await adapt(f, row, noOptions, item));
      return commitOne(f, row, opts, complete, term, item, prepicked);
    };

    // The format a written value is compared in, decided by the FACT's slot,
    // never by what the value looks like: a page re-punctuates a phone number
    // and a salary ("$80,000" for 80000).
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

    const mapFields = async (open) => {
      const unmapped = open.filter((f) => !rows.get(f.fid).route);
      for (let i = 0; i < unmapped.length; i += CHUNK) {
        if (halt()) return;
        const part = unmapped.slice(i, i + CHUNK);
        const res = await post("/api/autofill/map", {
          ...selector,
          fields: part.map((f) => ({
            fid: f.fid, question: question(f), section: f.section ? String(f.section).slice(0, 200) : null,
            repeat_index: Math.min(Math.max(Number(f.repeatIndex) || 0, 0), 20), shape: f.shape,
            multi: Boolean(f.multi), required: Boolean(f.required),
            options: usable(f.options).slice(0, MAP_OPTIONS).map((o) => o.text.slice(0, 300)),
          })),
        });
        for (const f of part) {
          const m = res?.fields?.[f.fid];
          if (m) set(f.fid, { route: m.route, slot: m.slot ?? null, value: m.value ?? null });
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
          done({ fid: r.fid }, "unstable", row.wrote);
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
      const open = observe(frames);
      if (halt()) break;
      if (!open.length) {
        if ((settled = await settledDone())) break;
        continue;
      }
      await mapFields(open);
      if (halt()) break;

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

      // Model calls run beside the page work; page actions stay one at a time.
      let answers = null;
      const asking = prose.length ? answerProse(prose).then((got) => { answers = got; }) : null;
      let proseWritten = !prose.length;
      // Prose is written as soon as its answers are in, between other fields.
      const writeProse = async () => {
        if (proseWritten || !answers || halt()) return;
        proseWritten = true;
        for (const f of prose) {
          if (halt()) break;
          const choice = answers[f.fid];
          if (!(choice?.answer && choice.reason === "matched")) {
            finish(f, "needs_answer", { lastOutcome: "abstained" });
            continue;
          }
          await worked(f, L.FIELD_MS, () => fillText(f, choice.answer));
        }
      };
      const prepicking = pickBatch(choices.filter((f) => pickedTogether(f, rows.get(f.fid))));
      for (const f of texts) {
        if (halt()) break;
        await worked(f, L.FIELD_MS, (row) => fillText(f, textOf(f, row), formatOf(row.slot)));
        await writeProse();
      }
      const prepicked = await prepicking;
      for (const f of choices) {
        if (halt()) break;
        await writeProse();
        const row = rows.get(f.fid);
        const items = Array.isArray(row.value) ? Math.min(new Set(row.value).size, L.MAX_ITEMS) : 1;
        await worked(f, L.FIELD_MS + L.ITEM_MS * Math.max(0, items - 1),
          (working) => fillChoice(f, working, prepicked.has(f.fid) ? prepicked.get(f.fid) : undefined));
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
    const fields = listed.map((fid) => {
      const r = rows.get(fid);
      return {
        fid,
        frameId: r.frameId,
        question: r.field?.question ?? "",
        section: r.field?.section ?? "",
        required: Boolean(r.field?.required),
        shape: r.field?.shape,
        status: FINAL.has(r.status) ? r.status
          : r.status === "retry" && !stopped && !over ? "cannot_operate" : "needs_answer",
        answer: r.answer ?? (r.leftover && !DONE.has(r.status)
          ? `Companion wrote "${r.leftover}" here for an earlier question. Check it.` : null),
        route: r.route ?? null,
        slot: r.slot ?? null,
        // Left open when the run's clock ran out: the panel can say so.
        lastOutcome: over && !FINAL.has(r.status) ? "timeout" : r.lastOutcome ?? null,
      };
    });
    return { runId, fields, host, aiFailure, stopped, timedOut: over };
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
  // (a group click that committed one, a search that picked while exploring):
  // the user's to check, sent as filled_unverified.
  const LANDED = new Set(["group_committed", "committed_while_exploring"]);
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

  ns.fillLoop = { runFill, sourceHintOf, limits, buildLoopObservations };
})();
