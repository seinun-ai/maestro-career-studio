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
 * - Policy-blocked options are never offered to /pick or /map; every set, search
 *   or native, is picked one source item at a time (`item`).
 * - When the generic path is surprised (an unexpected commit, no options, an
 *   honest "no option states it" over a popup), /step picks the next move from
 *   the moves the page's code listed. A click is sent `as: "progress"` only when
 *   /step called it progress (a group). A move that progressed (a group or an
 *   unmarked category opened), went stale, or was refused as not_a_group
 *   re-takes the state and steps again. A group click that committed a value
 *   (group_committed) is left for the user, named — never "filled". History is
 *   built only from move ids and outcomes (`mid -> outcome (reason)`), last 8.
 * - Never stall: every backend wait is bounded (API_MS, and never past the
 *   field's or the run's clock); each field has ONE clock shared by its pick,
 *   commit and adaptive steps; the run has a clock; rounds, attempts, steps and
 *   items are capped. A late answer is ignored. Before finishing, a tail sweep
 *   gives a late reversion the chance to show, and it is retried.
 * - Nothing is guessed when the AI cannot be reached (`aiFailure`).
 * - Stop: `cancelled()` is checked before every page action; the panel also
 *   sends `fill_cancel`, which cancels the page operation in flight.
 *
 * Final statuses: verified | closest | assumed | already | blocked | yours |
 *                 partial | needs_answer | cannot_operate
 *
 * WHAT THIS FILE PUBLISHES: ns.fillLoop = { runFill, sourceHintOf, limits }.
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
    TAIL_MS: 800,
  };
  // The backend's limits (app/schemas/autofill_fill.py).
  const CHUNK = 40;
  const MAP_OPTIONS = 30;
  const PICK_OPTIONS = 250;
  const STEP_CANDIDATES = 60;
  const HISTORY_KEPT = 8;
  const FID = /^[A-Za-z0-9_-]{1,64}$/;
  const HISTORY_ENTRY = /^(click:o\d+|search:value|search:word:\d|open|scroll|close|give_up|choose) -> [a-z_]+( \([a-z_]+\))?$/;
  const FINAL = new Set(["verified", "closest", "assumed", "already", "blocked", "yours", "partial", "needs_answer", "cannot_operate"]);
  // What the engine itself committed: the only rows a sweep may reopen.
  const DONE = new Set(["verified", "closest", "assumed", "partial"]);
  const STATUS = { matched: "verified", closest: "closest", assumed: "assumed" };
  const REFUSED = { yours: "yours", blocked: "blocked", unsupported: "cannot_operate" };
  const CAN_ADAPT = new Set(["popup", "search"]);

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
  const landedNote = (text) => (text ? `Companion clicked "${text}" — check it` : "Companion clicked an option — check it");
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
    else if (options.base) selector.base = options.base;
    const asked = { ...selector, source_hint: options.sourceHint ? String(options.sourceHint).slice(0, 60) : null };
    const rows = new Map(); // fid -> { fid, field, frameId, status, attempts, route, slot, value, answer, lastOutcome, deadline }
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
    const done = (f, reason, committed) => finish(f, STATUS[reason] ?? "verified", {
      answer: Array.isArray(committed) ? committed.join(", ") : committed ?? null, lastOutcome: "verified",
    });
    // One clock per field, started when the loop starts on it.
    const work = (f, ms = L.FIELD_MS) => set(f.fid, { status: "open", deadline: Date.now() + ms });
    const fieldLate = (f) => Date.now() >= (rows.get(f.fid)?.deadline ?? Infinity);
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
    const act = async (f, action, { closing = false } = {}) => {
      if (cancelled() || (!closing && timedOut())) return { outcome: "halted" };
      if (!closing && fieldLate(f)) return { outcome: "late" };
      const [got] = rowsOf(await broadcast({ type: "fill_apply", actions: [{ fid: f.fid, fp: f.fp, ...action }] }))
        .filter((r) => r?.fid === f.fid);
      if (!got) return { outcome: "stale" }; // no frame owns the fid any more
      if (got.outcome === "cancelled") return { outcome: "halted" };
      if (REFUSED[got.outcome]) {
        finish(f, REFUSED[got.outcome], { lastOutcome: got.outcome });
        return { outcome: "refused" };
      }
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
    const pick = async (f, row, opts, complete, item) => {
      const offered = usable(opts);
      if (!offered.length || halt() || fieldLate(f)) return null;
      const res = await post("/api/autofill/pick", {
        ...asked,
        fields: [{
          fid: f.fid, question: question(f), route: routeOf(row), slot: row.slot ?? null,
          ...(item !== undefined ? { item: String(item).slice(0, 300) } : {}),
          options: offered.slice(0, PICK_OPTIONS).map(({ oid, text }) => ({ oid, text: text.slice(0, 300) })),
          // Complete only when the model sees EVERY option: none hidden by policy, none past the cap.
          complete: Boolean(complete) && offered.length === (opts ?? []).length && offered.length <= PICK_OPTIONS,
        }],
      }, rows.get(f.fid).deadline);
      const got = res?.picks?.[f.fid];
      if (!got) return null;
      const text = got.oids?.length ? offered.find((o) => o.oid === got.oids[0])?.text : undefined;
      return text ? { text, reason: got.reason } : { abstained: true };
    };

    // ---- the adaptive step. Returns { outcome } — verified (+reason,
    // committed) | landed (+text) | gave_up | no_answer | exhausted | late |
    // stale (+why) | final (a refusal, recorded) | halted.
    const giveUp = async (f, outcome) => {
      if (!cancelled()) await act(f, { op: "move", mid: "give_up" }, { closing: true });
      return { outcome };
    };
    const adapt = async (f, row, first, item) => {
      const value = item ?? (typeof row.value === "string" ? row.value : undefined);
      const history = first ? [first] : [];
      for (let i = 0; i < L.MAX_STEPS; i += 1) {
        if (halt()) return { outcome: "halted" };
        if (fieldLate(f)) return giveUp(f, "late");
        const [state] = results(await broadcast({
          type: "fill_step_state", fid: f.fid, fp: f.fp, ...(value !== undefined ? { value } : {}),
        }));
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
        if (halt()) return { outcome: "halted" };
        if (fieldLate(f)) return giveUp(f, "late");
        const chosen = res?.mid && res.mid !== "give_up" ? state.candidates.find((c) => c.mid === res.mid) : null;
        if (!chosen) return giveUp(f, res ? "gave_up" : "no_answer");
        const asProgress = res.reason === "progress" && chosen.mid.startsWith("click:");
        const out = await act(f, {
          op: "move", mid: chosen.mid, version: state.version, ...(asProgress ? { as: "progress" } : {}),
        });
        if (out.outcome === "halted") return { outcome: "halted" };
        if (out.outcome === "refused") return { outcome: "final" };
        if (out.outcome === "late") return giveUp(f, "late");
        const entry = historyEntry(chosen.mid, out.outcome, out.reason);
        if (entry) history.push(entry);
        if (out.outcome === "verified") return { outcome: "verified", reason: res.reason, committed: out.committed };
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
      else if (r.outcome === "landed") finish(f, "needs_answer", { answer: landedNote(r.text), lastOutcome: "group_committed" });
      else if (r.outcome === "gave_up") finish(f, "needs_answer", { lastOutcome: "abstained" });
      else if (r.outcome === "no_answer") finish(f, "needs_answer", { lastOutcome: "no_answer" });
      else if (r.outcome === "exhausted") finish(f, "cannot_operate", { lastOutcome: "step_budget" });
      else if (r.outcome === "late") finish(f, "cannot_operate", { lastOutcome: "timeout" });
      else if (r.outcome === "stale") fail(f, r.why);
    };

    // ---- one value
    const commitOne = async (f, row, opts, complete, term) => {
      const picked = await pick(f, row, opts, complete);
      if (!picked) {
        if (halt() || fieldLate(f)) return lateOrHalted(f);
        return finish(f, "needs_answer", { lastOutcome: "no_answer" });
      }
      if (picked.abstained) {
        // An honest "no option states it" over a popup is where categories,
        // search boxes and "Not in list" live. A native list showed everything.
        if (CAN_ADAPT.has(f.shape)) return settle(f, await adapt(f, row, historyEntry("choose", "abstained")));
        return finish(f, "needs_answer", { lastOutcome: "abstained" });
      }
      const out = await act(f, { op: "choose", text: picked.text, ...(f.shape === "search" ? { term: term ?? picked.text } : {}) });
      if (notDone(f, out)) return undefined;
      if (out.outcome === "verified") return done(f, picked.reason, out.committed);
      if (out.outcome === "unexpected" && CAN_ADAPT.has(f.shape)) {
        return settle(f, await adapt(f, row, historyEntry("choose", "unexpected", out.reason)));
      }
      return fail(f, out.reason ?? out.outcome);
    };

    // ---- a set: every source item picked on its own, coverage counted per item
    const commitSet = async (f, row, opts, complete, noOptions) => {
      const all = row.value.map(String);
      const worked = all.slice(0, L.MAX_ITEMS);
      const byPolicy = new Set(worked.filter(policyBlocks));
      const pairs = []; // [option text, source item, reason]
      const missed = new Map(); // source item -> the history entry the adaptive step starts from
      if (f.shape === "search") {
        for (const item of worked) {
          if (byPolicy.has(item)) continue;
          const got = await explore(f, item);
          if (!got) return lateOrHalted(f);
          if (exploreRefused(f, got)) return undefined;
          if (got.options?.length && !usable(got.options).length) {
            byPolicy.add(item); // every option shown for it is a never-fill one
            continue;
          }
          if (!got.options?.length) {
            missed.set(item, historyEntry("search:value", "unexpected", got.error ?? "no_results"));
            continue;
          }
          const p = await pick(f, row, got.options, false, item);
          if (p?.text) pairs.push([p.text, item, p.reason]);
          else if (p?.abstained) missed.set(item, historyEntry("choose", "abstained"));
        }
      } else if (noOptions) {
        for (const item of worked) if (!byPolicy.has(item)) missed.set(item, noOptions);
      } else {
        // Native (and popup) lists: one pick per source item over the full
        // list, so every chosen option maps back to the item it stands for.
        const got = await Promise.all(worked.filter((item) => !byPolicy.has(item))
          .map(async (item) => [item, await pick(f, row, opts, complete, item)]));
        for (const [item, p] of got) {
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
        const out = await act(f, action);
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
        for (const [item, first] of missed) {
          if (halt() || fieldLate(f)) break;
          const r = await adapt(f, row, first, item);
          if (FINAL.has(rows.get(f.fid).status) || r.outcome === "halted") return undefined;
          if (r.outcome === "verified") {
            covered.set(item, r.reason);
            committed = r.committed ?? committed;
          } else if (r.outcome === "landed") {
            landed.push(r.text);
          } else if (r.outcome === "late" || r.outcome === "stale") {
            break;
          }
        }
      }
      if (cancelled() || timedOut()) return undefined;
      const n = all.length;
      const notes = [
        ...(byPolicy.size ? [`${byPolicy.size} left to you by policy`] : []),
        ...landed.map(landedNote),
      ];
      if (covered.size === n) return done(f, [...covered.values()].includes("closest") ? "closest" : "matched", committed);
      if (!covered.size) {
        if (byPolicy.size === n) return finish(f, "blocked", { lastOutcome: "blocked" });
        return finish(f, "needs_answer", {
          answer: notes.length ? notes.join(" · ") : null, lastOutcome: landed.length ? "group_committed" : "missing",
        });
      }
      return finish(f, "partial", { answer: [`${covered.size} of ${n} added`, ...notes].join(" · "), lastOutcome: "partial" });
    };

    // ---- a choice field: explore when the list is not already whole, then pick and commit
    const fillChoice = async (f, row) => {
      const { value } = row;
      if (row.route === "slot" && (value == null || value === "" || (Array.isArray(value) && !value.length))) {
        return finish(f, "needs_answer", { lastOutcome: "no_value" });
      }
      const isSet = Array.isArray(value) && Boolean(f.multi);
      // A set fact on a one-answer field: no single item is THE answer.
      if (Array.isArray(value) && !isSet) return finish(f, "needs_answer", { lastOutcome: "set_for_one" });
      let opts = f.options ?? [];
      let complete = Boolean(f.optionsComplete);
      let term;
      let noOptions = null;
      if (!(isSet && f.shape === "search") && !(opts.length && complete)) {
        term = f.shape === "search" && typeof value === "string" ? value : undefined;
        const got = await explore(f, term);
        if (!got) return lateOrHalted(f);
        if (exploreRefused(f, got)) return undefined;
        if (got.options?.length) {
          opts = got.options;
          complete = Boolean(got.complete);
        } else if (!opts.length) {
          noOptions = historyEntry(term ? "search:value" : "open", "unexpected", got.error ?? "empty_popup");
        }
      }
      if (opts.length && !usable(opts).length) return finish(f, "blocked", { lastOutcome: "blocked" });
      if (isSet) return commitSet(f, row, opts, complete, noOptions);
      if (noOptions) return settle(f, await adapt(f, row, noOptions));
      return commitOne(f, row, opts, complete, term);
    };

    const fillText = async (f, value, format) => {
      const out = await act(f, { op: "write", value, ...(format ? { format } : {}) });
      if (notDone(f, out)) return undefined;
      if (out.outcome === "verified") return done(f, "matched", out.committed);
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
        } else if (row.status === "new" && f.answered && !f.invalid) finish(f, "already");
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

    // A value the engine verified that no longer holds is retried; the sweep's
    // word about any other field (the user's, a prefilled one) is not ours to act on.
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
        set(r.fid, { status: "retry", attempts: (row.attempts ?? 0) + 1, lastOutcome: r.outcome ?? "reverted" });
        reverted += 1;
      }
      return reverted;
    };
    // Before calling the page done: wait, sweep once more; done only if nothing reverted.
    const settledDone = async () => {
      if (halt()) return true;
      if (L.TAIL_MS > 0) await wait(Math.min(L.TAIL_MS, runDeadline - Date.now()));
      if (halt()) return true;
      return (await sweep()) === 0;
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
          if (row.route === "slot" && typeof row.value === "string" && row.value) texts.push(f);
          else finish(f, "needs_answer", { lastOutcome: "no_value" });
        } else choices.push(f);
      }

      const proseAnswers = prose.length ? answerProse(prose) : null;
      for (const f of texts) {
        if (halt()) break;
        const row = work(f);
        await fillText(f, row.value, /phone/i.test(row.slot ?? "") ? "phone" : undefined);
      }
      for (const f of choices) {
        if (halt()) break;
        const row = rows.get(f.fid);
        const items = Array.isArray(row.value) ? Math.min(row.value.length, L.MAX_ITEMS) : 1;
        await fillChoice(f, work(f, L.FIELD_MS + L.ITEM_MS * Math.max(0, items - 1)));
      }
      if (proseAnswers && !halt()) {
        const answers = await proseAnswers;
        for (const f of prose) {
          if (halt()) break;
          const choice = answers[f.fid];
          if (!(choice?.answer && choice.reason === "matched")) {
            finish(f, "needs_answer", { lastOutcome: "abstained" });
            continue;
          }
          work(f);
          await fillText(f, choice.answer);
        }
      }
      if (!halt()) await sweep();
      tell({ phase: "round", round });
      if (snapshot() === before && (settled = await settledDone())) break;
    }
    // Out of rounds with the last one still changing things: the tail sweep
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
        answer: r.answer ?? null,
        route: r.route ?? null,
        slot: r.slot ?? null,
        lastOutcome: r.lastOutcome ?? null,
      };
    });
    return { runId, fields, host, aiFailure, stopped, timedOut: over };
  }

  ns.fillLoop = { runFill, sourceHintOf, limits };
})();
